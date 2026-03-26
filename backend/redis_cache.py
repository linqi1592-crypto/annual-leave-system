"""
Redis 缓存后端 - v1.5 多实例部署支持
"""

import json
import pickle
from typing import Any, Optional
from datetime import datetime
import os

try:
    import redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False


class RedisCache:
    """Redis 缓存后端 - 支持多实例共享缓存"""
    
    def __init__(self, redis_url: str = None, prefix: str = "leave:"):
        if not REDIS_AVAILABLE:
            raise ImportError("Redis 未安装，请运行: pip install redis")
        
        self.redis_url = redis_url or os.getenv('REDIS_URL', 'redis://localhost:6379/0')
        self.prefix = prefix
        self._client = None
        self._connect()
    
    def _connect(self):
        """连接 Redis"""
        try:
            self._client = redis.from_url(
                self.redis_url,
                decode_responses=False,  # 使用二进制序列化
                socket_connect_timeout=5,
                socket_timeout=5,
                health_check_interval=30
            )
            # 测试连接
            self._client.ping()
        except Exception as e:
            raise ConnectionError(f"Redis 连接失败: {e}")
    
    def _make_key(self, key: str) -> str:
        """生成带前缀的 key"""
        return f"{self.prefix}{key}"
    
    def _serialize(self, value: Any) -> bytes:
        """序列化值"""
        return pickle.dumps(value)
    
    def _deserialize(self, data: bytes) -> Any:
        """反序列化值"""
        if data is None:
            return None
        return pickle.loads(data)
    
    def get(self, key: str) -> Optional[Any]:
        """获取缓存值"""
        try:
            data = self._client.get(self._make_key(key))
            return self._deserialize(data)
        except Exception as e:
            print(f"Redis get error: {e}")
            return None
    
    def set(self, key: str, value: Any, ttl: int = 3600):
        """设置缓存值"""
        try:
            serialized = self._serialize(value)
            self._client.setex(
                self._make_key(key),
                ttl,
                serialized
            )
        except Exception as e:
            print(f"Redis set error: {e}")
    
    def delete(self, key: str):
        """删除缓存"""
        try:
            self._client.delete(self._make_key(key))
        except Exception as e:
            print(f"Redis delete error: {e}")
    
    def clear(self, pattern: str = None):
        """清空缓存（支持通配符）"""
        try:
            if pattern:
                # 使用通配符删除
                full_pattern = self._make_key(pattern + "*")
                keys = self._client.keys(full_pattern)
                if keys:
                    self._client.delete(*keys)
            else:
                # 删除所有带前缀的 key
                keys = self._client.keys(self._make_key("*"))
                if keys:
                    self._client.delete(*keys)
        except Exception as e:
            print(f"Redis clear error: {e}")
    
    def stats(self) -> dict:
        """获取 Redis 统计"""
        try:
            info = self._client.info()
            db_size = self._client.dbsize()
            
            # 计算带前缀的 key 数量
            prefix_keys = len(self._client.keys(self._make_key("*")))
            
            return {
                "type": "redis",
                "connected": True,
                "total_keys": db_size,
                "prefix_keys": prefix_keys,
                "used_memory": info.get("used_memory_human", "N/A"),
                "uptime": info.get("uptime_in_seconds", 0),
                "version": info.get("redis_version", "N/A")
            }
        except Exception as e:
            return {
                "type": "redis",
                "connected": False,
                "error": str(e)
            }
    
    def health_check(self) -> bool:
        """健康检查"""
        try:
            return self._client.ping()
        except:
            return False


# 工厂函数 - 根据配置创建缓存实例
def create_cache(cache_type: str = None, **kwargs):
    """
    创建缓存实例
    
    Args:
        cache_type: 'memory' 或 'redis'，默认从环境变量读取
        **kwargs: 额外配置参数
    
    Returns:
        Cache 实例
    """
    cache_type = cache_type or os.getenv('CACHE_TYPE', 'memory')
    
    if cache_type == 'redis':
        if not REDIS_AVAILABLE:
            print("警告: Redis 未安装，回退到内存缓存")
            from cache import MemoryCache
            return MemoryCache()
        
        redis_url = kwargs.get('redis_url') or os.getenv('REDIS_URL')
        prefix = kwargs.get('prefix', 'leave:')
        return RedisCache(redis_url=redis_url, prefix=prefix)
    
    else:
        # 内存缓存
        from cache import MemoryCache
        return MemoryCache()


# ==================== 使用示例 ====================

if __name__ == "__main__":
    # 测试 Redis 缓存
    print("测试 Redis 缓存...")
    
    try:
        cache = create_cache('redis')
        
        # 测试基本操作
        cache.set("test_key", {"name": "张三", "age": 30}, ttl=60)
        value = cache.get("test_key")
        print(f"✓ 读写测试: {value}")
        
        # 测试过期
        import time
        time.sleep(2)
        value = cache.get("test_key")
        print(f"✓ 未过期: {value is not None}")
        
        # 测试统计
        stats = cache.stats()
        print(f"✓ 统计信息: {stats}")
        
        # 清理
        cache.clear()
        print("✓ 清理完成")
        
        print("\nRedis 测试通过!")
        
    except Exception as e:
        print(f"✗ Redis 测试失败: {e}")
        print("请确保 Redis 服务已启动: redis-server")
