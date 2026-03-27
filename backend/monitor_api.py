"""
日志监控 API - v1.5
提供日志查询、统计、告警配置接口
"""

import os
import json
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from fastapi import APIRouter, HTTPException, Query, Depends
from pydantic import BaseModel

from auth import require_hr, User
from logger import logger

monitor_router = APIRouter()


# ==================== 数据模型 ====================

class LogEntry(BaseModel):
    """日志条目"""
    timestamp: str
    level: str
    message: str
    event: Optional[str] = None
    user_id: Optional[str] = None
    duration_ms: Optional[int] = None


class LogStats(BaseModel):
    """日志统计"""
    total_logs: int
    error_count: int
    warning_count: int
    api_calls: int
    avg_response_time: float
    error_rate: float


class AlertRule(BaseModel):
    """告警规则"""
    name: str
    condition: str  # 如: "error_rate > 5%"
    webhook: str
    enabled: bool = True


# ==================== API 路由 ====================

@monitor_router.get("/api/admin/logs")
def query_logs(
    level: Optional[str] = Query(None, description="日志级别: debug/info/warning/error"),
    event: Optional[str] = Query(None, description="事件类型"),
    user_id: Optional[str] = Query(None, description="用户ID"),
    start_time: Optional[str] = Query(None, description="开始时间 ISO格式"),
    end_time: Optional[str] = Query(None, description="结束时间 ISO格式"),
    limit: int = Query(100, ge=1, le=1000, description="返回条数"),
    current_user: User = Depends(require_hr)
):
    """
    查询日志 - HR 权限
    
    支持按级别、事件类型、用户、时间范围筛选
    """
    try:
        logger.info(f"HR查询日志: user={current_user.name}, level={level}, event={event}")
        
        # 读取日志文件
        log_file = "logs/app.log"
        if not os.path.exists(log_file):
            return {"code": 0, "data": [], "total": 0}
        
        logs = []
        with open(log_file, 'r', encoding='utf-8') as f:
            for line in f:
                try:
                    entry = json.loads(line.strip())
                    
                    # 过滤条件
                    if level and entry.get('level') != level.lower():
                        continue
                    if event and entry.get('event') != event:
                        continue
                    if user_id and entry.get('user_id') != user_id:
                        continue
                    
                    # 时间范围过滤
                    if start_time or end_time:
                        entry_time = datetime.fromisoformat(entry['timestamp'].replace('Z', '+00:00'))
                        if start_time:
                            start = datetime.fromisoformat(start_time.replace('Z', '+00:00'))
                            if entry_time < start:
                                continue
                        if end_time:
                            end = datetime.fromisoformat(end_time.replace('Z', '+00:00'))
                            if entry_time > end:
                                continue
                    
                    logs.append(entry)
                except:
                    continue
        
        # 按时间倒序，限制条数
        logs.reverse()
        total = len(logs)
        logs = logs[:limit]
        
        return {
            "code": 0,
            "data": logs,
            "total": total,
            "limit": limit
        }
        
    except Exception as e:
        logger.error(f"查询日志失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@monitor_router.get("/api/admin/logs/stats")
def get_log_stats(
    hours: int = Query(24, ge=1, le=168, description="统计最近N小时"),
    current_user: User = Depends(require_hr)
) -> Dict:
    """
    获取日志统计 - HR 权限
    
    返回最近N小时的日志统计信息
    """
    try:
        logger.info(f"HR查看日志统计: user={current_user.name}, hours={hours}")
        
        log_file = "logs/app.log"
        if not os.path.exists(log_file):
            return {
                "code": 0,
                "data": {
                    "total_logs": 0,
                    "error_count": 0,
                    "warning_count": 0,
                    "api_calls": 0,
                    "avg_response_time": 0,
                    "error_rate": 0
                }
            }
        
        # 计算时间范围
        end_time = datetime.utcnow()
        start_time = end_time - timedelta(hours=hours)
        
        stats = {
            "total_logs": 0,
            "error_count": 0,
            "warning_count": 0,
            "api_calls": 0,
            "api_durations": [],
            "cache_hits": 0,
            "cache_misses": 0
        }
        
        with open(log_file, 'r', encoding='utf-8') as f:
            for line in f:
                try:
                    entry = json.loads(line.strip())
                    entry_time = datetime.fromisoformat(entry['timestamp'].replace('Z', '+00:00'))
                    
                    # 时间范围过滤
                    if entry_time < start_time:
                        continue
                    
                    stats["total_logs"] += 1
                    
                    # 级别统计
                    level = entry.get('level', '').lower()
                    if level == 'error':
                        stats["error_count"] += 1
                    elif level == 'warning':
                        stats["warning_count"] += 1
                    
                    # API 调用统计
                    if entry.get('event') == 'api_call':
                        stats["api_calls"] += 1
                        if entry.get('duration_ms'):
                            stats["api_durations"].append(entry['duration_ms'])
                    
                    # 缓存统计
                    if entry.get('event') == 'cache_access':
                        if entry.get('cache_hit'):
                            stats["cache_hits"] += 1
                        else:
                            stats["cache_misses"] += 1
                            
                except:
                    continue
        
        # 计算平均值
        avg_duration = sum(stats["api_durations"]) / len(stats["api_durations"]) if stats["api_durations"] else 0
        error_rate = (stats["error_count"] / stats["total_logs"] * 100) if stats["total_logs"] > 0 else 0
        
        # 缓存命中率
        total_cache = stats["cache_hits"] + stats["cache_misses"]
        cache_hit_rate = (stats["cache_hits"] / total_cache * 100) if total_cache > 0 else 0
        
        return {
            "code": 0,
            "data": {
                "time_range": {
                    "start": start_time.isoformat(),
                    "end": end_time.isoformat(),
                    "hours": hours
                },
                "total_logs": stats["total_logs"],
                "error_count": stats["error_count"],
                "warning_count": stats["warning_count"],
                "api_calls": stats["api_calls"],
                "avg_response_time": round(avg_duration, 2),
                "error_rate": round(error_rate, 2),
                "cache_hit_rate": round(cache_hit_rate, 2),
                "cache_hits": stats["cache_hits"],
                "cache_misses": stats["cache_misses"]
            }
        }
        
    except Exception as e:
        logger.error(f"获取日志统计失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@monitor_router.get("/api/admin/logs/errors")
def get_error_logs(
    limit: int = Query(20, ge=1, le=100),
    current_user: User = Depends(require_hr)
):
    """
    获取最近的错误日志 - HR 权限
    """
    try:
        log_file = "logs/error.log"
        if not os.path.exists(log_file):
            return {"code": 0, "data": [], "total": 0}
        
        errors = []
        with open(log_file, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            # 取最后 N 条
            for line in lines[-limit:]:
                try:
                    entry = json.loads(line.strip())
                    errors.append(entry)
                except:
                    errors.append({"raw": line.strip()})
        
        errors.reverse()
        
        return {
            "code": 0,
            "data": errors,
            "total": len(errors)
        }
        
    except Exception as e:
        logger.error(f"获取错误日志失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@monitor_router.get("/api/admin/dashboard")
def get_dashboard(
    current_user: User = Depends(require_hr)
):
    """
    获取仪表盘数据 - HR 权限
    
    汇总关键指标：
    - 今日 API 调用量
    - 平均响应时间
    - 错误率
    - 缓存命中率
    - 活跃用户
    """
    try:
        logger.info(f"HR查看仪表盘: user={current_user.name}")
        
        # 获取24小时统计
        stats_response = get_log_stats(hours=24, current_user=current_user)
        stats = stats_response["data"]
        
        # 获取活跃用户数（去重）
        log_file = "logs/app.log"
        active_users = set()
        
        if os.path.exists(log_file):
            end_time = datetime.utcnow()
            start_time = end_time - timedelta(hours=24)
            
            with open(log_file, 'r', encoding='utf-8') as f:
                for line in f:
                    try:
                        entry = json.loads(line.strip())
                        entry_time = datetime.fromisoformat(entry['timestamp'].replace('Z', '+00:00'))
                        
                        if entry_time >= start_time and entry.get('user_id'):
                            active_users.add(entry['user_id'])
                    except:
                        continue
        
        return {
            "code": 0,
            "data": {
                "summary": {
                    "active_users_24h": len(active_users),
                    "total_api_calls_24h": stats["api_calls"],
                    "avg_response_time": stats["avg_response_time"],
                    "error_rate": stats["error_rate"],
                    "cache_hit_rate": stats["cache_hit_rate"]
                },
                "health_status": {
                    "api": "healthy" if stats["error_rate"] < 5 else "warning",
                    "cache": "healthy" if stats["cache_hit_rate"] > 50 else "warning",
                    "overall": "healthy" if stats["error_rate"] < 5 else "degraded"
                },
                "alerts": []  # 如果有告警规则触发，这里会显示
            }
        }
        
    except Exception as e:
        logger.error(f"获取仪表盘数据失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@monitor_router.post("/api/admin/alerts/test")
def test_alert(
    webhook: str = Query(..., description="飞书 webhook URL"),
    current_user: User = Depends(require_hr)
):
    """
    测试告警 webhook - HR 权限
    """
    try:
        from logger import AlertManager
        
        alert_manager = AlertManager(webhook_url=webhook)
        alert_manager.send_alert(
            level='info',
            title='测试告警',
            message='这是一条测试告警消息，来自年假查询系统',
            details={
                '发送人': current_user.name,
                '时间': datetime.utcnow().isoformat(),
                '系统': '年假查询系统 v1.4'
            }
        )
        
        return {
            "code": 0,
            "message": "测试告警已发送，请检查飞书"
        }
        
    except Exception as e:
        logger.error(f"发送测试告警失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))
