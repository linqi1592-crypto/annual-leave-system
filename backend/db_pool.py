"""
数据库连接池 - v1.5 解决 SQLite 并发问题
使用连接池管理，避免 database locked
"""

import sqlite3
import threading
import queue
import time
from typing import Optional
import logging

logger = logging.getLogger(__name__)


class ConnectionPool:
    """SQLite 连接池"""
    
    def __init__(
        self,
        db_path: str,
        pool_size: int = 5,
        timeout: int = 30
    ):
        self.db_path = db_path
        self.pool_size = pool_size
        self.timeout = timeout
        
        self._pool = queue.Queue(maxsize=pool_size)
        self._lock = threading.Lock()
        self._initialized = False
        
        # 初始化连接池
        self._init_pool()
    
    def _init_pool(self):
        """初始化连接池"""
        with self._lock:
            if self._initialized:
                return
            
            for _ in range(self.pool_size):
                conn = self._create_connection()
                self._pool.put(conn)
            
            self._initialized = True
            logger.info(f"数据库连接池初始化完成: size={self.pool_size}")
    
    def _create_connection(self) -> sqlite3.Connection:
        """创建新连接"""
        conn = sqlite3.connect(
            self.db_path,
            check_same_thread=False,  # 允许跨线程使用
            timeout=self.timeout,      # 等待锁的超时时间
            isolation_level=None       # 自动提交模式，减少锁持有时间
        )
        # 启用 WAL 模式，提高并发性能
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        return conn
    
    def get_connection(self, timeout: float = None) -> sqlite3.Connection:
        """
        获取连接
        
        Args:
            timeout: 等待连接的超时时间（秒）
        
        Returns:
            数据库连接
        """
        try:
            conn = self._pool.get(timeout=timeout or self.timeout)
            
            # 检查连接是否有效
            try:
                conn.execute("SELECT 1")
            except sqlite3.Error:
                # 连接失效，创建新连接
                logger.warning("数据库连接失效，重新创建")
                conn = self._create_connection()
            
            return conn
        except queue.Empty:
            raise RuntimeError(f"获取数据库连接超时（{self.timeout}秒），连接池已满")
    
    def release_connection(self, conn: sqlite3.Connection):
        """释放连接回连接池"""
        if conn:
            try:
                # 回滚未提交的事务
                conn.rollback()
                self._pool.put(conn)
            except Exception as e:
                logger.error(f"释放连接失败: {e}")
                try:
                    conn.close()
                except:
                    pass
    
    def close_all(self):
        """关闭所有连接"""
        with self._lock:
            while not self._pool.empty():
                try:
                    conn = self._pool.get_nowait()
                    conn.close()
                except:
                    pass
            self._initialized = False


class PooledDB:
    """支持连接池的数据库操作类"""
    
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls, db_path: str = None, pool_size: int = 5):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._init(db_path, pool_size)
        return cls._instance
    
    def _init(self, db_path: str, pool_size: int):
        """初始化"""
        self.db_path = db_path or "data/leave_adjustments.db"
        self.pool = ConnectionPool(self.db_path, pool_size=pool_size)
    
    def execute(
        self,
        sql: str,
        parameters: tuple = None,
        fetch: bool = False,
        fetch_one: bool = False
    ):
        """
        执行 SQL
        
        Args:
            sql: SQL 语句
            parameters: 参数
            fetch: 是否获取结果
            fetch_one: 是否只获取一条
        
        Returns:
            执行结果或查询数据
        """
        conn = None
        try:
            conn = self.pool.get_connection()
            
            # 设置行工厂
            conn.row_factory = sqlite3.Row
            
            cursor = conn.cursor()
            
            if parameters:
                cursor.execute(sql, parameters)
            else:
                cursor.execute(sql)
            
            result = None
            if fetch:
                if fetch_one:
                    row = cursor.fetchone()
                    result = dict(row) if row else None
                else:
                    rows = cursor.fetchall()
                    result = [dict(row) for row in rows]
            else:
                conn.commit()
                result = cursor.lastrowid
            
            cursor.close()
            return result
            
        except sqlite3.OperationalError as e:
            if "database is locked" in str(e):
                logger.error(f"数据库被锁定，可能是并发冲突: {e}")
                # 可以在这里实现重试逻辑
                raise RuntimeError("系统繁忙，请稍后重试") from e
            raise
        finally:
            if conn:
                self.pool.release_connection(conn)
    
    def execute_many(self, sql: str, parameters_list: list):
        """批量执行"""
        conn = None
        try:
            conn = self.pool.get_connection()
            cursor = conn.cursor()
            cursor.executemany(sql, parameters_list)
            conn.commit()
            cursor.close()
        finally:
            if conn:
                self.pool.release_connection(conn)
    
    def transaction(self):
        """事务上下文管理器"""
        return TransactionContext(self.pool)


class TransactionContext:
    """事务上下文管理器"""
    
    def __init__(self, pool: ConnectionPool):
        self.pool = pool
        self.conn = None
    
    def __enter__(self):
        self.conn = self.pool.get_connection()
        return self.conn
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type:
            # 发生异常，回滚
            self.conn.rollback()
        else:
            # 正常提交
            self.conn.commit()
        
        self.pool.release_connection(self.conn)


# ==================== 使用示例 ====================

if __name__ == "__main__":
    # 测试连接池
    db = PooledDB("test.db", pool_size=3)
    
    # 创建表
    db.execute("""
        CREATE TABLE IF NOT EXISTS test (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT
        )
    """)
    
    # 插入数据
    db.execute("INSERT INTO test (name) VALUES (?)", ("张三",))
    
    # 查询数据
    result = db.execute("SELECT * FROM test", fetch=True)
    print(f"查询结果: {result}")
    
    # 使用事务
    with db.transaction() as conn:
        cursor = conn.cursor()
        cursor.execute("INSERT INTO test (name) VALUES (?)", ("李四",))
        cursor.execute("INSERT INTO test (name) VALUES (?)", ("王五",))
        cursor.close()
    
    print("✓ 连接池测试通过")
