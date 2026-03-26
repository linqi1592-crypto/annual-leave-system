"""
缓存模块 - v1.4 性能优化
支持 TTL（过期时间）、内存缓存、可选 Redis
"""

import time
import threading
from typing import Any, Optional, Callable
from functools import wraps
import hashlib
import json


class MemoryCache:
    """内存缓存 - 带 TTL 支持"""
    
    def __init__(self):
        self._cache = {}
        self._lock = threading.RLock()
    
    def _generate_key(self, prefix: str, *args, **kwargs) -> str:
        """生成缓存 key"""
        key_data = json.dumps({
            'prefix': prefix,
            'args': args,
            'kwargs': kwargs
        }, sort_keys=True)
        return f"{prefix}:{hashlib.md5(key_data.encode()).hexdigest()}"
    
    def get(self, key: str) -> Optional[Any]:
        """获取缓存值"""
        with self._lock:
            if key not in self._cache:
                return None
            
            value, expire_time = self._cache[key]
            
            # 检查是否过期
            if expire_time and time.time() > expire_time:
                del self._cache[key]
                return None
            
            return value
    
    def set(self, key: str, value: Any, ttl: int = 3600):
        """
        设置缓存值
        
        Args:
            key: 缓存键
            value: 缓存值
            ttl: 过期时间（秒），默认1小时
        """
        with self._lock:
            expire_time = time.time() + ttl if ttl > 0 else None
            self._cache[key] = (value, expire_time)
    
    def delete(self, key: str):
        """删除缓存"""
        with self._lock:
            self._cache.pop(key, None)
    
    def clear(self, prefix: str = None):
        """清空缓存"""
        with self._lock:
            if prefix:
                keys_to_delete = [k for k in self._cache.keys() if k.startswith(prefix)]
                for key in keys_to_delete:
                    del self._cache[key]
            else:
                self._cache.clear()
    
    def stats(self) -> dict:
        """获取缓存统计"""
        with self._lock:
            total = len(self._cache)
            expired = sum(1 for _, expire in self._cache.values() 
                         if expire and time.time() > expire)
            return {
                'total_keys': total,
                'expired_keys': expired,
                'valid_keys': total - expired
            }


# 全局缓存实例 - 支持 Redis 或内存
import os

_cache_type = os.getenv('CACHE_TYPE', 'memory')
if _cache_type == 'redis':
    try:
        from redis_cache import RedisCache
        cache = RedisCache()
        print("✓ 使用 Redis 缓存")
    except Exception as e:
        print(f"✗ Redis 连接失败，回退到内存缓存: {e}")
        cache = MemoryCache()
else:
    cache = MemoryCache()
    print("✓ 使用内存缓存")


def cached(prefix: str, ttl: int = 3600, key_func: Callable = None):
    """
    缓存装饰器
    
    Args:
        prefix: 缓存前缀
        ttl: 过期时间（秒）
        key_func: 自定义 key 生成函数
    
    Example:
        @cached('leave_balance', ttl=1800)
        def calculate_leave_balance(employee_id, year):
            # 耗时计算...
            return result
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            # 生成缓存 key
            if key_func:
                cache_key = key_func(*args, **kwargs)
            else:
                cache_key = cache._generate_key(prefix, *args, **kwargs)
            
            # 尝试从缓存获取
            cached_value = cache.get(cache_key)
            if cached_value is not None:
                return cached_value
            
            # 执行函数
            result = func(*args, **kwargs)
            
            # 存入缓存
            cache.set(cache_key, result, ttl)
            
            return result
        
        # 添加清除缓存的方法
        wrapper.cache_clear = lambda: cache.clear(prefix)
        
        return wrapper
    return decorator


def invalidate_cache(prefix: str, *args, **kwargs):
    """使指定缓存失效"""
    key = cache._generate_key(prefix, *args, **kwargs)
    cache.delete(key)


def clear_cache(prefix: str = None):
    """清空缓存"""
    cache.clear(prefix)


# ==================== 业务层缓存封装 ====================

class LeaveCache:
    """年假查询专用缓存"""
    
    # 缓存 TTL 配置（秒）
    TTL = {
        'leave_balance': 1800,      # 年假余额：30分钟
        'leave_history': 600,       # 请假明细：10分钟
        'leave_rules': 3600,        # 计算规则：1小时
        'employees': 300,           # 员工列表：5分钟
        'adjustments': 300,         # 调整记录：5分钟
        'export_data': 600,         # 导出数据：10分钟
    }
    
    @classmethod
    def get_balance_key(cls, employee_id: str, year: int) -> str:
        """年假余额缓存 key"""
        return f"balance:{employee_id}:{year}"
    
    @classmethod
    def get_history_key(cls, employee_id: str, year: int) -> str:
        """请假明细缓存 key"""
        return f"history:{employee_id}:{year}"
    
    @classmethod
    def get_rules_key(cls, employee_id: str) -> str:
        """计算规则缓存 key"""
        return f"rules:{employee_id}"
    
    @classmethod
    def get_employees_key(cls) -> str:
        """员工列表缓存 key"""
        return "employees:all"
    
    @classmethod
    def invalidate_balance(cls, employee_id: str, year: int):
        """使年假余额缓存失效（调整记录后调用）"""
        key = cls.get_balance_key(employee_id, year)
        cache.delete(key)
    
    @classmethod
    def invalidate_balance_by_name(cls, employee_name: str, year: int):
        """使年假余额缓存失效（通过员工姓名，用于调整记录后）"""
        # 使用姓名作为 key 的一部分（简化处理）
        key = f"balance:name:{employee_name}:{year}"
        cache.delete(key)
        # 同时清除该员工所有年份的余额缓存
        cache.clear(f"balance:")
    
    @classmethod
    def invalidate_employee(cls, employee_id: str):
        """使员工相关缓存失效"""
        current_year = 2026  # 可以从配置获取
        cls.invalidate_balance(employee_id, current_year)
        cls.invalidate_balance(employee_id, current_year - 1)
        cache.delete(cls.get_history_key(employee_id, current_year))
    
    @classmethod
    def get_stats(cls) -> dict:
        """获取缓存统计"""
        return cache.stats()


# ==================== 使用示例 ====================

if __name__ == "__main__":
    # 测试缓存
    print("测试缓存模块...")
    
    # 测试基础缓存
    cache.set("test_key", "test_value", ttl=2)
    assert cache.get("test_key") == "test_value"
    print("✓ 基础缓存")
    
    # 测试过期
    time.sleep(3)
    assert cache.get("test_key") is None
    print("✓ TTL 过期")
    
    # 测试装饰器
    @cached('test', ttl=5)
    def expensive_function(x, y):
        time.sleep(0.1)
        return x + y
    
    start = time.time()
    result1 = expensive_function(1, 2)
    time1 = time.time() - start
    
    start = time.time()
    result2 = expensive_function(1, 2)  # 从缓存获取
    time2 = time.time() - start
    
    assert result1 == result2 == 3
    assert time2 < time1 / 2  # 缓存应该快很多
    print(f"✓ 缓存装饰器 (首次: {time1:.3f}s, 缓存: {time2:.3f}s)")
    
    # 测试统计
    stats = cache.stats()
    print(f"✓ 缓存统计: {stats}")
    
    print("\n所有测试通过!")
