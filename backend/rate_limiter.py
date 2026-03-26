"""
飞书 API 限流保护模块 - v1.5 高并发优化
令牌桶算法 + 多级缓存策略
"""

import time
import threading
import functools
from typing import Optional, Callable, Any
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class RateLimitStrategy(Enum):
    """限流策略"""
    BLOCK = "block"           # 阻塞等待
    FAIL = "fail"             # 立即失败
    CACHE_ONLY = "cache_only" # 只返回缓存


class TokenBucket:
    """令牌桶限流器 - 线程安全"""
    
    def __init__(
        self,
        rate: float = 10.0,      # 每秒产生令牌数
        capacity: int = 20,      # 桶容量
        strategy: RateLimitStrategy = RateLimitStrategy.BLOCK
    ):
        self.rate = rate
        self.capacity = capacity
        self.tokens = capacity
        self.last_update = time.time()
        self.lock = threading.RLock()
        self.strategy = strategy
        self.block_timeout = 5.0  # 最大阻塞等待时间
    
    def _add_tokens(self):
        """补充令牌"""
        now = time.time()
        elapsed = now - self.last_update
        new_tokens = elapsed * self.rate
        
        self.tokens = min(self.capacity, self.tokens + new_tokens)
        self.last_update = now
    
    def acquire(self, tokens: int = 1, timeout: float = None) -> bool:
        """
        获取令牌
        
        Args:
            tokens: 需要的令牌数
            timeout: 等待超时时间
        
        Returns:
            是否成功获取令牌
        """
        timeout = timeout or self.block_timeout
        start_time = time.time()
        
        while True:
            with self.lock:
                self._add_tokens()
                
                if self.tokens >= tokens:
                    self.tokens -= tokens
                    return True
                
                # 根据策略处理
                if self.strategy == RateLimitStrategy.FAIL:
                    return False
                
                if self.strategy == RateLimitStrategy.CACHE_ONLY:
                    return False
                
                # BLOCK 策略：计算需要等待的时间
                tokens_needed = tokens - self.tokens
                wait_time = tokens_needed / self.rate
                
                # 检查是否超时
                if time.time() - start_time + wait_time > timeout:
                    return False
            
            # 释放锁后等待
            time.sleep(min(wait_time, 0.1))
    
    def get_status(self) -> dict:
        """获取限流器状态"""
        with self.lock:
            self._add_tokens()
            return {
                "tokens": self.tokens,
                "capacity": self.capacity,
                "rate": self.rate,
                "utilization": (self.capacity - self.tokens) / self.capacity
            }


class FeishuRateLimiter:
    """飞书 API 专用限流器"""
    
    # 飞书 API 限制（保守设置）
    DEFAULT_QPS = 8  # 每秒最多8次（飞书限制10-20）
    
    def __init__(self):
        # 不同接口的限流器
        self.limiters = {
            # 员工信息查询 - 低频，可以宽松
            "user_info": TokenBucket(rate=5, capacity=10),
            
            # 多维表格查询 - 高频，严格限制
            "bitable_records": TokenBucket(rate=self.DEFAULT_QPS, capacity=20),
            
            # 免登认证 - 低频
            "auth": TokenBucket(rate=3, capacity=5),
            
            # 通用接口
            "default": TokenBucket(rate=self.DEFAULT_QPS, capacity=20)
        }
        
        # 统计信息
        self.stats = {
            "total_requests": 0,
            "allowed_requests": 0,
            "blocked_requests": 0,
            "cache_hits": 0
        }
        self.stats_lock = threading.Lock()
    
    def acquire(self, api_type: str = "default", tokens: int = 1) -> bool:
        """
        获取调用许可
        
        Args:
            api_type: API 类型
            tokens: 消耗令牌数（复杂接口消耗更多）
        
        Returns:
            是否允许调用
        """
        limiter = self.limiters.get(api_type, self.limiters["default"])
        
        with self.stats_lock:
            self.stats["total_requests"] += 1
        
        if limiter.acquire(tokens):
            with self.stats_lock:
                self.stats["allowed_requests"] += 1
            return True
        else:
            with self.stats_lock:
                self.stats["blocked_requests"] += 1
            logger.warning(f"飞书API限流触发: type={api_type}, tokens={tokens}")
            return False
    
    def get_wait_time(self, api_type: str = "default") -> float:
        """获取预计等待时间"""
        limiter = self.limiters.get(api_type, self.limiters["default"])
        
        with limiter.lock:
            limiter._add_tokens()
            if limiter.tokens >= 1:
                return 0.0
            return (1 - limiter.tokens) / limiter.rate
    
    def get_stats(self) -> dict:
        """获取限流统计"""
        with self.stats_lock:
            total = self.stats["total_requests"]
            allowed = self.stats["allowed_requests"]
            
            return {
                **self.stats,
                "block_rate": (self.stats["blocked_requests"] / total * 100) if total > 0 else 0,
                "limiter_status": {
                    name: limiter.get_status()
                    for name, limiter in self.limiters.items()
                }
            }


# 全局限流器实例
feishu_limiter = FeishuRateLimiter()


def rate_limited(api_type: str = "default", tokens: int = 1, fallback: Callable = None):
    """
    限流装饰器
    
    Args:
        api_type: API 类型
        tokens: 消耗令牌数
        fallback: 限流时的回退函数
    
    Example:
        @rate_limited("bitable_records", tokens=1)
        def get_employee_records():
            return feishu_client.get_records()
        
        @rate_limited("bitable_records", fallback=get_cached_records)
        def get_employee_records():
            return feishu_client.get_records()
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            if feishu_limiter.acquire(api_type, tokens):
                return func(*args, **kwargs)
            else:
                # 触发限流
                if fallback:
                    logger.info(f"API限流，使用回退策略: {func.__name__}")
                    return fallback(*args, **kwargs)
                else:
                    raise RuntimeError(
                        f"飞书API调用过于频繁，请稍后重试。"
                        f"预计等待: {feishu_limiter.get_wait_time(api_type):.1f}秒"
                    )
        return wrapper
    return decorator


class CachedFeishuClient:
    """带限流和缓存的飞书客户端包装器"""
    
    def __init__(self, feishu_client, cache, limiter=None):
        self.client = feishu_client
        self.cache = cache
        self.limiter = limiter or feishu_limiter
    
    def get_employee_records(self, force_refresh: bool = False):
        """获取员工列表 - 带限流和缓存"""
        cache_key = "feishu:employees:all"
        
        # 1. 检查缓存
        if not force_refresh:
            cached = self.cache.get(cache_key)
            if cached:
                logger.debug("员工列表缓存命中")
                return cached
        
        # 2. 限流检查
        if not self.limiter.acquire("bitable_records", tokens=2):
            # 限流时强制使用缓存
            cached = self.cache.get(cache_key)
            if cached:
                logger.warning("API限流，使用过期缓存")
                return cached
            raise RuntimeError("系统繁忙，请稍后重试")
        
        # 3. 调用API
        try:
            records = self.client.get_employee_records()
            # 缓存30分钟
            self.cache.set(cache_key, records, ttl=1800)
            return records
        except Exception as e:
            logger.error(f"获取员工列表失败: {e}")
            # 尝试使用缓存（即使过期）
            cached = self.cache.get(cache_key)
            if cached:
                logger.warning("API失败，使用过期缓存")
                return cached
            raise
    
    def get_leave_records(self, employee_name: str, year: int = None, force_refresh: bool = False):
        """获取请假记录 - 带限流和缓存"""
        cache_key = f"feishu:leave:{employee_name}:{year or 'all'}"
        
        # 检查缓存
        if not force_refresh:
            cached = self.cache.get(cache_key)
            if cached:
                return cached
        
        # 限流检查
        if not self.limiter.acquire("bitable_records", tokens=1):
            cached = self.cache.get(cache_key)
            if cached:
                return cached
            raise RuntimeError("系统繁忙，请稍后重试")
        
        # 调用API
        records = self.client.get_leave_records(employee_name)
        # 缓存10分钟
        self.cache.set(cache_key, records, ttl=600)
        return records
    
    def get_user_info(self, user_access_token: str):
        """获取用户信息 - 带限流"""
        if not self.limiter.acquire("user_info", tokens=1):
            raise RuntimeError("系统繁忙，请稍后重试")
        
        return self.client.get_user_info(user_access_token)


# ==================== 使用示例 ====================

if __name__ == "__main__":
    print("测试飞书API限流器...")
    
    limiter = FeishuRateLimiter()
    
    # 测试正常获取
    print("\n1. 测试正常获取令牌...")
    for i in range(5):
        success = limiter.acquire("bitable_records")
        print(f"   请求{i+1}: {'✓' if success else '✗'}")
        time.sleep(0.05)
    
    # 测试限流触发
    print("\n2. 测试限流触发...")
    burst_requests = 0
    for i in range(30):
        if limiter.acquire("bitable_records"):
            burst_requests += 1
    
    print(f"   突发30次请求，成功{burst_requests}次")
    
    # 测试等待后恢复
    print("\n3. 测试令牌恢复...")
    time.sleep(1)  # 等待1秒，应该恢复8个令牌
    recovered = 0
    for i in range(10):
        if limiter.acquire("bitable_records"):
            recovered += 1
    
    print(f"   等待1秒后，成功{recovered}次（预期~8次）")
    
    # 查看统计
    print("\n4. 限流统计...")
    stats = limiter.get_stats()
    print(f"   总请求: {stats['total_requests']}")
    print(f"   允许: {stats['allowed_requests']}")
    print(f"   限制: {stats['blocked_requests']}")
    print(f"   限制率: {stats['block_rate']:.1f}%")
    
    print("\n✓ 限流器测试完成")
