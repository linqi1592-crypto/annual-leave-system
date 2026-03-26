# v1.5 飞书 API 限流保护报告

**日期**: 2026-03-26  
**执行者**: 犀甲  
**版本**: v1.5 高并发优化

---

## 问题背景

500人规模下，飞书 API 调用可能触发限流：
```
500人同时查询 → 500次API请求 → 飞书封禁10分钟 → 系统不可用
```

---

## 实现方案

### 1. 令牌桶限流器 (rate_limiter.py)

**原理**:
```
每秒产生 8 个令牌 → 桶容量 20 → 消耗令牌才能调用 API
令牌不足 → 等待或拒绝
```

**不同接口的限流策略**:
| 接口类型 | QPS | 说明 |
|----------|-----|------|
| bitable_records | 8 | 多维表格查询（最严格） |
| user_info | 5 | 用户信息（低频） |
| auth | 3 | 认证（低频） |

---

### 2. 使用方式

**方式1: 装饰器**
```python
from rate_limiter import rate_limited

@rate_limited("bitable_records", tokens=1)
def get_employee_records():
    return feishu_client.get_records()
```

**方式2: 直接检查**
```python
if not feishu_limiter.acquire("bitable_records"):
    return "系统繁忙，请稍后重试"
```

**方式3: 带缓存的客户端**
```python
from rate_limiter import CachedFeishuClient

cached_client = CachedFeishuClient(feishu_client, cache)
records = cached_client.get_employee_records()  # 自动限流+缓存
```

---

### 3. 保护效果

| 场景 | 无保护 | 有限流 |
|------|--------|--------|
| 500人同时查询 | API被封 | 排队处理，8次/秒 |
| 年终清算导出 | API被封 | 缓存优先，API兜底 |
| 突发流量 | 服务不可用 | 降级到缓存数据 |

---

### 4. 监控指标

```python
# 获取限流统计
stats = feishu_limiter.get_stats()

{
    "total_requests": 1000,
    "allowed_requests": 950,
    "blocked_requests": 50,
    "block_rate": 5.0
}
```

---

## 提交记录

```
commit 1e0ddf4: feat: v1.5 飞书API限流保护
```

**文件**:
- `backend/rate_limiter.py` (新)
- `backend/feishu_client.py` (修改)

---

## 部署注意

无需配置，默认启用：
```python
# 调整限流阈值（如需）
feishu_limiter.limiters["bitable_records"].rate = 10  # 10 QPS
```

500人规模下，**必须启用此功能**！
