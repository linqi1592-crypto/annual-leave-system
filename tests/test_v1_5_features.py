"""
年假查询系统 v1.5 全面测试套件
测试工程师: Ada
日期: 2026-03-26
覆盖: 连接池、Redis、日志监控、API集成
"""

import pytest
import threading
import time
import os
import tempfile
import json
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, MagicMock

# 设置测试环境
os.environ['CACHE_TYPE'] = 'memory'  # 测试使用内存缓存
os.environ['JWT_SECRET_KEY'] = 'test-secret-key-for-testing-only'

from backend.db_pool import ConnectionPool, PooledDB
from backend.cache import MemoryCache, LeaveCache
from backend.redis_cache import create_cache


# ==================== 1. 连接池测试 ====================

class TestConnectionPool:
    """SQLite 连接池测试 - 解决并发写问题"""
    
    def setup_method(self):
        self.db_fd, self.db_path = tempfile.mkstemp(suffix='.db')
        self.pool = ConnectionPool(self.db_path, pool_size=3)
    
    def teardown_method(self):
        self.pool.close_all()
        os.close(self.db_fd)
        os.unlink(self.db_path)
    
    def test_pool_initialization(self):
        """TC-POOL-001: 连接池初始化"""
        assert self.pool.pool_size == 3
        assert self.pool._initialized == True
    
    def test_get_and_release_connection(self):
        """TC-POOL-002: 获取和释放连接"""
        conn = self.pool.get_connection()
        assert conn is not None
        
        # 测试连接有效性
        cursor = conn.execute("SELECT 1")
        result = cursor.fetchone()
        assert result[0] == 1
        
        self.pool.release_connection(conn)
    
    def test_connection_reuse(self):
        """TC-POOL-003: 连接复用"""
        conn1 = self.pool.get_connection()
        self.pool.release_connection(conn1)
        
        conn2 = self.pool.get_connection()
        # conn2 应该是复用的 conn1
        assert conn2 is not None
        self.pool.release_connection(conn2)
    
    def test_concurrent_access(self):
        """TC-POOL-004: 并发访问测试 - 关键！"""
        results = []
        errors = []
        
        def worker(thread_id):
            try:
                conn = self.pool.get_connection(timeout=5)
                # 创建表
                conn.execute(f"CREATE TABLE IF NOT EXISTS test_{thread_id} (id INTEGER)")
                conn.execute(f"INSERT INTO test_{thread_id} VALUES (?)", (thread_id,))
                conn.commit()
                self.pool.release_connection(conn)
                results.append(thread_id)
            except Exception as e:
                errors.append((thread_id, str(e)))
        
        # 启动5个线程并发操作
        threads = [threading.Thread(target=worker, args=(i,)) for i in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)
        
        assert len(errors) == 0, f"并发错误: {errors}"
        assert len(results) == 5
    
    def test_pool_exhaustion(self):
        """TC-POOL-005: 连接池耗尽处理"""
        # 占满所有连接
        conns = []
        for _ in range(3):
            conns.append(self.pool.get_connection())
        
        # 再获取应该超时
        with pytest.raises(RuntimeError) as exc_info:
            self.pool.get_connection(timeout=1)
        
        assert "超时" in str(exc_info.value)
        
        # 释放后重新获取
        for conn in conns:
            self.pool.release_connection(conn)
        
        conn = self.pool.get_connection()
        assert conn is not None
        self.pool.release_connection(conn)
    
    def test_wal_mode_enabled(self):
        """TC-POOL-006: WAL 模式已启用"""
        conn = self.pool.get_connection()
        cursor = conn.execute("PRAGMA journal_mode")
        mode = cursor.fetchone()[0]
        self.pool.release_connection(conn)
        
        assert mode.lower() == 'wal', f"WAL 模式未启用，当前: {mode}"


class TestPooledDB:
    """PooledDB 操作类测试"""
    
    def setup_method(self):
        self.db_fd, self.db_path = tempfile.mkstemp(suffix='.db')
        self.db = PooledDB(self.db_path, pool_size=3)
    
    def teardown_method(self):
        self.db.pool.close_all()
        os.close(self.db_fd)
        os.unlink(self.db_path)
    
    def test_execute_and_fetch(self):
        """TC-DB-001: 执行和查询"""
        # 创建表
        self.db.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT)")
        
        # 插入数据
        row_id = self.db.execute("INSERT INTO users (name) VALUES (?)", ("张三",))
        assert row_id is not None
        
        # 查询数据
        result = self.db.execute("SELECT * FROM users WHERE name = ?", ("张三",), fetch=True, fetch_one=True)
        assert result is not None
        assert result['name'] == '张三'
    
    def test_transaction_rollback(self):
        """TC-DB-002: 事务回滚"""
        self.db.execute("CREATE TABLE test (id INTEGER)")
        
        try:
            with self.db.transaction() as conn:
                cursor = conn.cursor()
                cursor.execute("INSERT INTO test VALUES (1)")
                cursor.execute("INSERT INTO test VALUES (2)")
                # 抛出异常，触发回滚
                raise ValueError("测试回滚")
        except ValueError:
            pass
        
        # 验证数据未插入
        result = self.db.execute("SELECT COUNT(*) as count FROM test", fetch=True, fetch_one=True)
        assert result['count'] == 0
    
    def test_concurrent_writes(self):
        """TC-DB-003: 并发写入测试 - 模拟年终清算场景"""
        self.db.execute("CREATE TABLE adjustments (id INTEGER PRIMARY KEY, amount REAL)")
        
        errors = []
        
        def create_adjustment(thread_id):
            try:
                for i in range(3):
                    self.db.execute(
                        "INSERT INTO adjustments (amount) VALUES (?)",
                        (float(thread_id * 10 + i),)
                    )
                    time.sleep(0.01)  # 模拟处理时间
            except Exception as e:
                errors.append((thread_id, str(e)))
        
        # 5个线程同时写入（模拟多个HR同时调整）
        threads = [threading.Thread(target=create_adjustment, args=(i,)) for i in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        
        assert len(errors) == 0, f"并发写入错误: {errors}"
        
        # 验证数据完整性
        result = self.db.execute("SELECT COUNT(*) as count FROM adjustments", fetch=True, fetch_one=True)
        assert result['count'] == 15  # 5线程 × 3条


# ==================== 2. Redis 缓存测试 ====================

class TestRedisCache:
    """Redis 缓存测试"""
    
    @pytest.fixture
    def redis_cache(self):
        """Redis 缓存实例"""
        try:
            cache = create_cache('redis')
            if hasattr(cache, '_client'):
                cache.clear()
            yield cache
            if hasattr(cache, '_client'):
                cache.clear()
        except Exception as e:
            pytest.skip(f"Redis 不可用: {e}")
    
    def test_redis_set_and_get(self, redis_cache):
        """TC-REDIS-001: 基本读写"""
        redis_cache.set("test_key", {"name": "张三", "age": 30}, ttl=60)
        value = redis_cache.get("test_key")
        
        assert value == {"name": "张三", "age": 30}
    
    def test_redis_ttl_expiration(self, redis_cache):
        """TC-REDIS-002: TTL 过期"""
        redis_cache.set("expire_key", "value", ttl=1)
        
        # 立即获取
        value1 = redis_cache.get("expire_key")
        assert value1 == "value"
        
        # 等待过期
        time.sleep(2)
        value2 = redis_cache.get("expire_key")
        assert value2 is None
    
    def test_redis_clear_with_pattern(self, redis_cache):
        """TC-REDIS-003: 通配符清除"""
        redis_cache.set("user:1", "data1")
        redis_cache.set("user:2", "data2")
        redis_cache.set("order:1", "order1")
        
        redis_cache.clear("user")
        
        assert redis_cache.get("user:1") is None
        assert redis_cache.get("user:2") is None
        assert redis_cache.get("order:1") == "order1"
    
    def test_redis_stats(self, redis_cache):
        """TC-REDIS-004: 统计信息"""
        redis_cache.set("key1", "value1")
        redis_cache.set("key2", "value2")
        
        stats = redis_cache.stats()
        assert stats['type'] == 'redis'
        assert stats['connected'] == True
        assert stats['prefix_keys'] >= 2


# ==================== 3. 日志监控测试 ====================

class TestLogger:
    """日志监控测试"""
    
    def setup_method(self):
        self.log_dir = tempfile.mkdtemp()
        from backend.logger import setup_logging
        setup_logging(
            log_level="DEBUG",
            log_dir=self.log_dir,
            enable_file=True,
            enable_console=False,
            enable_json=True
        )
    
    def teardown_method(self):
        import shutil
        shutil.rmtree(self.log_dir, ignore_errors=True)
    
    def test_structured_log_output(self):
        """TC-LOG-001: 结构化日志输出"""
        from backend.logger import logger
        
        logger.info("测试消息", extra={'event': 'test', 'user_id': 'user_001'})
        
        # 读取日志文件
        log_file = os.path.join(self.log_dir, "app.log")
        with open(log_file, 'r') as f:
            lines = f.readlines()
            assert len(lines) > 0
            
            log_entry = json.loads(lines[0])
            assert log_entry['level'] == 'info'
            assert log_entry['message'] == '测试消息'
            assert log_entry['event'] == 'test'
            assert log_entry['user_id'] == 'user_001'
    
    def test_api_call_logging(self):
        """TC-LOG-002: API 调用日志"""
        from backend.logger import logger
        
        logger.api_call(
            endpoint="/api/leave/balance",
            user_id="user_001",
            duration_ms=50,
            success=True
        )
        
        log_file = os.path.join(self.log_dir, "api.log")
        with open(log_file, 'r') as f:
            lines = f.readlines()
            log_entry = json.loads(lines[0])
            assert log_entry['event'] == 'api_call'
            assert log_entry['endpoint'] == '/api/leave/balance'
    
    def test_cache_access_logging(self):
        """TC-LOG-003: 缓存访问日志"""
        from backend.logger import logger
        
        logger.cache_access(
            key="balance:user_001:2026",
            hit=True,
            duration_ms=2
        )
        
        log_file = os.path.join(self.log_dir, "app.log")
        with open(log_file, 'r') as f:
            lines = f.readlines()
            log_entry = json.loads(lines[0])
            assert log_entry['event'] == 'cache_access'
            assert log_entry['cache_hit'] == True


# ==================== 4. 集成测试 ====================

class TestIntegration:
    """集成测试 - 验证完整流程"""
    
    def test_full_flow_with_cache_and_pool(self):
        """TC-INT-001: 缓存+连接池完整流程"""
        # 这是一个模拟的完整流程测试
        
        # 1. 初始化连接池
        db_fd, db_path = tempfile.mkstemp(suffix='.db')
        db = PooledDB(db_path, pool_size=3)
        
        # 2. 初始化缓存
        cache = MemoryCache()
        
        # 3. 模拟 API 调用
        employee_id = "emp_001"
        year = 2026
        cache_key = f"balance:{employee_id}:{year}"
        
        # 4. 第一次查询（无缓存）
        cached = cache.get(cache_key)
        assert cached is None
        
        # 模拟数据库查询
        db.execute("CREATE TABLE test (id TEXT, balance REAL)")
        db.execute("INSERT INTO test VALUES (?, ?)", (employee_id, 10.5))
        result = db.execute("SELECT * FROM test WHERE id = ?", (employee_id,), fetch=True, fetch_one=True)
        
        # 存入缓存
        cache.set(cache_key, result, ttl=1800)
        
        # 5. 第二次查询（有缓存）
        cached = cache.get(cache_key)
        assert cached is not None
        assert cached['balance'] == 10.5
        
        # 清理
        db.pool.close_all()
        os.close(db_fd)
        os.unlink(db_path)
    
    def test_concurrent_api_simulation(self):
        """TC-INT-002: 并发 API 调用模拟"""
        db_fd, db_path = tempfile.mkstemp(suffix='.db')
        db = PooledDB(db_path, pool_size=5)
        cache = MemoryCache()
        
        # 初始化数据
        db.execute("CREATE TABLE adjustments (employee TEXT, amount REAL)")
        
        results = []
        errors = []
        
        def api_call(thread_id):
            try:
                # 模拟 API 处理流程
                cache_key = f"adjustments:{thread_id}"
                
                # 检查缓存
                cached = cache.get(cache_key)
                if cached is None:
                    # 查询数据库
                    db.execute("INSERT INTO adjustments VALUES (?, ?)", (f"emp_{thread_id}", float(thread_id)))
                    # 更新缓存
                    cache.set(cache_key, {"thread_id": thread_id}, ttl=60)
                
                results.append(thread_id)
            except Exception as e:
                errors.append((thread_id, str(e)))
        
        # 10个线程并发
        threads = [threading.Thread(target=api_call, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        
        assert len(errors) == 0, f"并发错误: {errors}"
        assert len(results) == 10
        
        # 验证数据
        count = db.execute("SELECT COUNT(*) as c FROM adjustments", fetch=True, fetch_one=True)
        assert count['c'] == 10
        
        # 清理
        db.pool.close_all()
        os.close(db_fd)
        os.unlink(db_path)


# ==================== 测试运行入口 ====================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
