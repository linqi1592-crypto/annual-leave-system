"""
年假查询系统 - FastAPI 主服务 v1.4
- P0: 飞书免登自动识别
- P0-2: 调整记录操作人身份验证
- P1-1: 余额卡片分栏展示
- P1-2: 负数余额兼容性
- P1-3: 批量导出
- P1-4: 年终清算
- P1-5: 司龄递增自动化
- v1.4: 添加缓存机制
"""

from fastapi import FastAPI, HTTPException, Query, Body, Header, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List
from datetime import date, datetime
from zoneinfo import ZoneInfo
import uvicorn
import logging

from config import (
    FEISHU_CONFIG, CORS_ALLOWED_ORIGINS, CORS_ALLOW_ALL, TIMEZONE,
    logger as config_logger
)
from feishu_client import feishu_client
from leave_calculator import calculator
from adjustment_db import db
from auth import auth_router, get_current_user, require_hr, require_employee_or_hr, User
from export import export_router
from year_end import year_end_router
from cache import LeaveCache, cache

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="年假查询系统",
    description="飞书年假查询 API v1.4",
    version="1.4.0"
)

# CORS 配置
if CORS_ALLOW_ALL:
    logger.warning("CORS 设置为允许所有来源，生产环境建议限制域名")
    allow_origins = ["*"]
else:
    allow_origins = CORS_ALLOWED_ORIGINS
    logger.info(f"CORS 允许的域名: {allow_origins}")

app.add_middleware(
    CORSMiddleware,
    allow_origins=allow_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["*"],
)

# 时区设置
tz = ZoneInfo(TIMEZONE)

# ==================== Pydantic Models ====================

class AdjustmentCreate(BaseModel):
    """创建调整记录请求体 - v1.3: 移除 created_by，后端自动获取"""
    employee_name: str
    year: int
    adjust_amount: float
    reason: str
    # created_by 字段已移除，后端从 current_user 自动获取


class AdjustmentResponse(BaseModel):
    """调整记录响应"""
    id: int
    employee_name: str
    year: int
    adjust_amount: float
    reason: str
    created_by: str
    created_by_open_id: Optional[str] = None  # v1.3
    created_at: str


# ==================== 注册路由 ====================

app.include_router(auth_router)
app.include_router(export_router)
app.include_router(year_end_router)


# ==================== API 路由 ====================

@app.get("/")
def root():
    """根路径"""
    return {"message": "年假查询系统 API", "version": "1.3.0"}


@app.get("/api/employees")
def get_employees(current_user: User = Depends(get_current_user)):
    """
    获取员工列表 - v1.4 添加缓存
    v1.3: 普通员工只能看到自己，HR可以看到全部
    """
    try:
        # v1.4: 尝试从缓存获取
        cache_key = LeaveCache.get_employees_key()
        cached_result = cache.get(cache_key)
        if cached_result is not None:
            logger.info(f"员工列表缓存命中: user={current_user.name}")
            # 即使是缓存，也要过滤权限
            if not current_user.is_hr:
                cached_result = [emp for emp in cached_result if emp["user_id"] == current_user.employee_id]
            return {"code": 0, "data": cached_result}
        
        logger.info(f"获取员工列表: user={current_user.name}, is_hr={current_user.is_hr}")
        employees = feishu_client.get_employee_records()
        
        result = []
        for emp in employees:
            fields = emp.get("fields", {})
            emp_id = emp.get("record_id")
            
            # v1.3: 权限控制 - 普通员工只能看到自己
            if not current_user.is_hr and current_user.employee_id != emp_id:
                continue
            
            result.append({
                "user_id": emp_id,
                "name": fields.get("发起人", ""),
                "fullname": fields.get("Fullname", ""),
                "department": fields.get("发起部门", ""),
            })
        
        # v1.4: 存入缓存，TTL 5分钟（HR查看全部，普通员工只缓存全部）
        if current_user.is_hr:
            cache.set(cache_key, result, ttl=LeaveCache.TTL['employees'])
        
        logger.info(f"获取到 {len(result)} 名员工")
        return {"code": 0, "data": result}
        
    except Exception as e:
        logger.error(f"获取员工列表失败: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/leave/balance")
def get_leave_balance(
    employee_id: str = Query(..., description="员工ID（飞书记录ID）"),
    year: Optional[int] = Query(None, description="查询年份（默认当前年）"),
    current_user: User = Depends(require_employee_or_hr)  # v1.3: 权限控制
):
    """
    查询年假余额 - v1.4 添加缓存
    - P1-1: 余额分栏展示
    - P1-2: 支持负数余额
    - P1-5: 司龄自动计算
    - v1.4: 添加缓存，TTL 30分钟
    """
    try:
        # 默认当前年
        if year is None:
            year = datetime.now(tz).year
        
        # v1.4: 尝试从缓存获取
        cache_key = LeaveCache.get_balance_key(employee_id, year)
        cached_result = cache.get(cache_key)
        if cached_result is not None:
            logger.info(f"年假余额缓存命中: employee_id={employee_id}, year={year}")
            return {"code": 0, "data": cached_result}
        
        logger.info(f"查询年假余额: employee_id={employee_id}, year={year}, user={current_user.name}")
        
        # 1. 获取员工信息
        employees = feishu_client.get_employee_records()
        employee = None
        employee_name = None
        
        for emp in employees:
            if emp.get("record_id") == employee_id:
                employee = emp
                employee_name = emp.get("fields", {}).get("发起人", "")
                break
        
        if not employee:
            logger.warning(f"未找到员工: {employee_id}")
            raise HTTPException(status_code=404, detail=f"未找到员工: {employee_id}")
        
        # 2. 获取请假记录
        leave_records = feishu_client.get_leave_records(employee_name)
        
        # 3. 计算上年剩余（含调整）
        previous_year = year - 1
        previous_system_remaining = calculate_previous_year_remaining_v2(
            employee, employee_name, previous_year
        )
        adjustment = db.get_total_adjustment(employee_name, previous_year)
        previous_year_remaining = previous_system_remaining + adjustment
        
        # 4. 计算年假余额（v1.3: 自动计算司龄，支持负数）
        current_date = date(year, datetime.now(tz).month, datetime.now(tz).day)
        result = calculator.calculate_annual_leave_balance(
            employee, leave_records, previous_year_remaining, current_date
        )
        
        # 5. 添加调整信息
        result["adjustment"] = {
            "system_remaining": previous_system_remaining,
            "adjustment_amount": adjustment,
            "final_remaining": previous_year_remaining
        }
        
        # v1.4: 存入缓存，TTL 30分钟
        cache.set(cache_key, result, ttl=LeaveCache.TTL['leave_balance'])
        
        logger.info(f"年假余额查询成功: {employee_name}, 剩余{result['annual_leave']['remaining']}天")
        return {"code": 0, "data": result}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"查询年假余额失败: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/leave/history")
def get_leave_history(
    employee_id: str = Query(..., description="员工ID（飞书记录ID）"),
    year: Optional[int] = Query(None, description="查询年份（默认当前年）"),
    current_user: User = Depends(require_employee_or_hr)  # v1.3: 权限控制
):
    """查询请假明细"""
    try:
        if year is None:
            year = datetime.now(tz).year
        
        # 先通过 ID 获取员工姓名
        employees = feishu_client.get_employee_records()
        employee_name = None
        for emp in employees:
            if emp.get("record_id") == employee_id:
                employee_name = emp.get("fields", {}).get("发起人", "")
                break
        
        if not employee_name:
            raise HTTPException(status_code=404, detail=f"未找到员工: {employee_id}")
        
        logger.info(f"查询请假明细: {employee_name}, year={year}, user={current_user.name}")
        
        # 获取请假记录
        leave_records = feishu_client.get_leave_records(employee_name)
        
        # 筛选并格式化
        records = []
        annual_used = 0.0
        personal_used = 0.0
        
        for record in leave_records:
            fields = record.get("fields", {})
            
            # 检查年份
            start_time = fields.get("开始时间")
            if start_time:
                try:
                    record_year = parse_timestamp_year(start_time)
                    if record_year != year:
                        continue
                except Exception as e:
                    logger.warning(f"日期解析失败: {start_time}, error: {e}")
                    continue
            
            leave_type = fields.get("请假类型", "")
            status = fields.get("申请状态", "")
            duration = fields.get("时长", 0) or 0
            
            # 只统计年假和事假
            if leave_type not in ["年假", "事假"]:
                continue
            
            # 格式化日期显示
            start_date_str = format_timestamp(fields.get("开始时间"))
            end_date_str = format_timestamp(fields.get("结束时间"))
            
            records.append({
                "apply_no": fields.get("申请编号", ""),
                "type": leave_type,
                "status": status,
                "start_date": start_date_str,
                "end_date": end_date_str,
                "duration": float(duration),
                "reason": fields.get("请假事由", "")
            })
            
            # 统计已通过的数量
            if status == "已通过":
                if leave_type == "年假":
                    annual_used += float(duration)
                elif leave_type == "事假":
                    personal_used += float(duration)
        
        # 按时间倒序
        records.sort(key=lambda x: x["start_date"], reverse=True)
        
        logger.info(f"请假明细查询成功: {len(records)}条记录")
        return {
            "code": 0,
            "data": {
                "year": year,
                "records": records,
                "summary": {
                    "annual_leave_used": annual_used,
                    "personal_leave_used": personal_used,
                    "total_used": annual_used + personal_used
                }
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"查询请假明细失败: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/leave/rules")
def get_leave_rules(
    employee_id: str = Query(..., description="员工ID（飞书记录ID）"),
    current_user: User = Depends(require_employee_or_hr)
):
    """
    查询年假计算规则 - v1.3: 显示自动计算的司龄
    """
    try:
        # 通过 ID 查找员工
        employees = feishu_client.get_employee_records()
        employee = None
        employee_name = None
        
        for emp in employees:
            if emp.get("record_id") == employee_id:
                employee = emp
                employee_name = emp.get("fields", {}).get("发起人", "")
                break
        
        if not employee:
            raise HTTPException(status_code=404, detail=f"未找到员工: {employee_id}")
        
        logger.info(f"查询年假规则: {employee_name}, user={current_user.name}")
        
        fields = employee.get("fields", {})
        social_months = fields.get("工龄(月)", 0) or 0
        
        # v1.3 P1-5: 自动计算司龄
        entry_date = calculator._parse_date(fields.get("入职时间"))
        service_months = calculator.calculate_service_months(entry_date, date.today())
        
        # 计算各阶段
        legal = calculator.calculate_legal_leave(social_months)
        welfare = calculator.calculate_welfare_leave(service_months)
        capped = calculator.apply_cap(legal + welfare, social_months)
        
        return {
            "code": 0,
            "data": {
                "employee": {
                    "id": employee_id,
                    "name": employee_name,
                    "social_security_months": social_months,
                    "service_months": service_months,
                    "service_years": service_months // 12,
                    "entry_date": entry_date.isoformat() if entry_date else None
                },
                "legal_leave": {
                    "base_months": social_months,
                    "days": legal,
                    "description": f"社保工龄{social_months}个月，法定年假{legal}天"
                },
                "welfare_leave": {
                    "service_years": service_months // 12,
                    "days": welfare,
                    "description": f"司龄{service_months//12}年（自动计算），福利年假{welfare}天"
                },
                "cap": {
                    "subtotal": legal + welfare,
                    "capped": capped,
                    "applied": capped < (legal + welfare)
                }
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"查询年假规则失败: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# ==================== 后台管理 API（需要 HR 权限） ====================

@app.get("/api/admin/adjustments")
def get_adjustments(
    employee_name: str = Query(..., description="员工姓名"),
    year: int = Query(..., description="调整年度"),
    current_user: User = Depends(require_hr)
):
    """查询调整记录（HR后台）"""
    try:
        logger.info(f"HR查询调整记录: {employee_name}, year={year}, user={current_user.name}")
        summary = db.get_adjustment_summary(employee_name, year)
        return {"code": 0, "data": summary}
    except Exception as e:
        logger.error(f"查询调整记录失败: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/admin/adjustments")
def create_adjustment(
    adjustment: AdjustmentCreate,
    current_user: User = Depends(require_hr)
):
    """
    新增调整记录（HR后台）- v1.4 添加缓存失效
    - v1.3 P0-2: 操作人自动从 session 获取
    - v1.4: 使相关缓存失效
    """
    try:
        logger.info(f"HR创建调整记录: {adjustment.employee_name}, year={adjustment.year}, user={current_user.name}")
        
        # v1.3: 操作人信息从 current_user 自动获取，不再使用前端传入的 created_by
        record = db.create_adjustment(
            employee_name=adjustment.employee_name,
            year=adjustment.year,
            adjust_amount=adjustment.adjust_amount,
            reason=adjustment.reason,
            created_by=current_user.name,  # 自动获取
            created_by_open_id=current_user.open_id,  # 自动获取
            adjustment_type="manual"
        )
        
        # v1.4: 使年假余额缓存失效（因为调整会影响余额）
        LeaveCache.invalidate_balance_by_name(adjustment.employee_name, adjustment.year)
        logger.info(f"缓存已失效: employee={adjustment.employee_name}, year={adjustment.year}")
        
        logger.info(f"调整记录创建成功: id={record.id}")
        
        return {
            "code": 0,
            "message": "调整记录已创建",
            "data": {
                "id": record.id,
                "employee_name": record.employee_name,
                "year": record.year,
                "adjust_amount": record.adjust_amount,
                "reason": record.reason,
                "created_by": record.created_by,
                "created_by_open_id": record.created_by_open_id,
                "created_at": record.created_at
            }
        }
    except Exception as e:
        logger.error(f"创建调整记录失败: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/admin/adjustments/{record_id}")
def delete_adjustment(
    record_id: int,
    current_user: User = Depends(require_hr)
):
    """撤销调整记录（HR后台）"""
    try:
        logger.info(f"HR撤销调整记录: id={record_id}, user={current_user.name}")
        success = db.deactivate_adjustment(record_id)
        if not success:
            raise HTTPException(status_code=404, detail="调整记录不存在")
        
        logger.info(f"调整记录撤销成功: id={record_id}")
        return {
            "code": 0,
            "message": "调整记录已撤回",
            "data": {"id": record_id, "is_active": False}
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"撤销调整记录失败: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# ==================== 辅助函数 ====================

def parse_timestamp_year(timestamp) -> int:
    """统一时区解析时间戳，返回年份"""
    if isinstance(timestamp, (int, float)):
        # 毫秒级时间戳（飞书默认）
        if timestamp > 1e10:
            dt = datetime.fromtimestamp(timestamp / 1000, tz=ZoneInfo("UTC"))
        else:
            dt = datetime.fromtimestamp(timestamp, tz=ZoneInfo("UTC"))
        return dt.astimezone(tz).year
    elif isinstance(timestamp, str):
        # ISO 格式字符串
        if 'T' in timestamp:
            dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
            return dt.astimezone(tz).year
        else:
            # 简单日期格式 YYYY-MM-DD
            return int(timestamp[:4])
    else:
        raise ValueError(f"不支持的时间格式: {timestamp}")


def format_timestamp(timestamp) -> str:
    """格式化时间戳为本地时间字符串"""
    if not timestamp:
        return ""
    
    try:
        if isinstance(timestamp, (int, float)):
            if timestamp > 1e10:
                dt = datetime.fromtimestamp(timestamp / 1000, tz=ZoneInfo("UTC"))
            else:
                dt = datetime.fromtimestamp(timestamp, tz=ZoneInfo("UTC"))
            return dt.astimezone(tz).strftime("%Y-%m-%d %H:%M")
        elif isinstance(timestamp, str):
            if 'T' in timestamp:
                dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                return dt.astimezone(tz).strftime("%Y-%m-%d %H:%M")
            else:
                return timestamp
        else:
            return str(timestamp)
    except Exception as e:
        logger.warning(f"时间格式化失败: {timestamp}, error: {e}")
        return str(timestamp)


def calculate_previous_year_remaining_v2(employee: dict, employee_name: str, year: int) -> float:
    """计算某年度系统计算的剩余年假（兼容旧调用）"""
    from leave_calculator import calculate_previous_year_remaining
    return calculate_previous_year_remaining(employee, employee_name, year, feishu_client)


# ==================== v1.4: 缓存监控 API ====================

@app.get("/api/admin/cache/stats")
def get_cache_stats(current_user: User = Depends(require_hr)):
    """
    获取缓存统计（HR监控）- v1.4
    
    Returns:
        缓存命中统计、键数量等
    """
    try:
        stats = LeaveCache.get_stats()
        logger.info(f"HR查看缓存统计: user={current_user.name}, stats={stats}")
        return {
            "code": 0,
            "data": {
                "cache_stats": stats,
                "ttl_config": LeaveCache.TTL,
                "message": "缓存统计信息"
            }
        }
    except Exception as e:
        logger.error(f"获取缓存统计失败: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/admin/cache/clear")
def clear_cache_endpoint(
    prefix: Optional[str] = Query(None, description="缓存前缀，空则全部清除"),
    current_user: User = Depends(require_hr)
):
    """
    清除缓存（HR管理）- v1.4
    
    Args:
        prefix: 缓存前缀，如 'balance', 'employees'，空则清除全部
    """
    try:
        cache.clear(prefix)
        logger.info(f"HR清除缓存: user={current_user.name}, prefix={prefix or 'all'}")
        return {
            "code": 0,
            "message": f"缓存已清除: {prefix or 'all'}",
            "data": {"cleared_prefix": prefix}
        }
    except Exception as e:
        logger.error(f"清除缓存失败: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    logger.info("🚀 启动年假查询系统 API v1.4")
    uvicorn.run(app, host="0.0.0.0", port=8000)
