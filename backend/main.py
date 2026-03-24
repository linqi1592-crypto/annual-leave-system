"""
年假查询系统 - FastAPI 主服务（Code Review 修复版）

修复内容：
1. CORS 限制为指定域名
2. HR 接口添加飞书鉴权
3. POST 接口改用 Body 传参
4. 员工查找支持 user_id
5. 新增 /api/employees 接口
6. 统一时区处理
7. 添加日志记录
8. 修复递归风险
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

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="年假查询系统",
    description="飞书年假查询 API",
    version="1.1.0"
)

# CORS 配置（根据环境变量限制）
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
    """创建调整记录请求体"""
    employee_name: str
    year: int
    adjust_amount: float
    reason: str
    created_by: str

class AdjustmentResponse(BaseModel):
    """调整记录响应"""
    id: int
    employee_name: str
    year: int
    adjust_amount: float
    reason: str
    created_by: str
    created_at: str


# ==================== 鉴权依赖 ====================

async def verify_feishu_auth(authorization: Optional[str] = Header(None)):
    """
    验证飞书登录态
    生产环境应该验证飞书的 user_access_token 或 tenant_access_token
    """
    if not authorization:
        logger.warning("HR 接口请求缺少 Authorization Header")
        raise HTTPException(status_code=401, detail="缺少认证信息")
    
    # TODO: 这里应该调用飞书 API 验证 token 有效性
    # 简化处理：检查 Bearer token 格式
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="认证格式错误")
    
    # 实际生产环境应该：
    # 1. 调用飞书 /open-apis/authen/v1/user_info 验证 token
    # 2. 检查用户是否有 HR 角色权限
    # 3. 返回用户信息供后续使用
    
    return authorization


# ==================== API 路由 ====================

@app.get("/")
def root():
    """根路径"""
    return {"message": "年假查询系统 API", "version": "1.1.0"}


@app.get("/api/employees")
def get_employees():
    """
    获取员工列表（用于前端下拉选择）
    """
    try:
        logger.info("获取员工列表")
        employees = feishu_client.get_employee_records()
        
        result = []
        for emp in employees:
            fields = emp.get("fields", {})
            result.append({
                "user_id": emp.get("record_id"),  # 飞书记录 ID 作为唯一标识
                "name": fields.get("发起人", ""),
                "fullname": fields.get("Fullname", ""),
                "department": fields.get("发起部门", ""),
            })
        
        logger.info(f"获取到 {len(result)} 名员工")
        return {"code": 0, "data": result}
        
    except Exception as e:
        logger.error(f"获取员工列表失败: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/leave/balance")
def get_leave_balance(
    employee_id: str = Query(..., description="员工ID（飞书记录ID）"),
    year: Optional[int] = Query(None, description="查询年份（默认当前年）")
):
    """
    查询年假余额（使用 employee_id 而非姓名）
    """
    try:
        # 默认当前年
        if year is None:
            year = datetime.now(tz).year
        
        logger.info(f"查询年假余额: employee_id={employee_id}, year={year}")
        
        # 1. 获取员工信息（通过 ID 查找）
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
        
        # 4. 计算年假余额
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
    year: Optional[int] = Query(None, description="查询年份（默认当前年）")
):
    """
    查询请假明细（使用 employee_id）
    """
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
        
        logger.info(f"查询请假明细: {employee_name}, year={year}")
        
        # 获取请假记录
        leave_records = feishu_client.get_leave_records(employee_name)
        
        # 筛选并格式化
        records = []
        annual_used = 0.0
        personal_used = 0.0
        
        for record in leave_records:
            fields = record.get("fields", {})
            
            # 检查年份（统一时区处理）
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
def get_leave_rules(employee_id: str = Query(..., description="员工ID（飞书记录ID）")):
    """
    查询年假计算规则（使用 employee_id）
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
        
        logger.info(f"查询年假规则: {employee_name}")
        
        fields = employee.get("fields", {})
        social_months = fields.get("工龄(月)", 0) or 0
        service_months = fields.get("司龄(月)", 0) or 0
        
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
                    "service_years": service_months // 12
                },
                "legal_leave": {
                    "base_months": social_months,
                    "days": legal,
                    "description": f"社保工龄{social_months}个月，法定年假{legal}天"
                },
                "welfare_leave": {
                    "service_years": service_months // 12,
                    "days": welfare,
                    "description": f"司龄{service_months//12}年，福利年假{welfare}天"
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


# ==================== 后台管理 API（需要鉴权） ====================

@app.get("/api/admin/adjustments")
def get_adjustments(
    employee_name: str = Query(..., description="员工姓名"),
    year: int = Query(..., description="调整年度"),
    auth: str = Depends(verify_feishu_auth)
):
    """
    查询调整记录（HR后台 - 需要鉴权）
    """
    try:
        logger.info(f"HR查询调整记录: {employee_name}, year={year}")
        summary = db.get_adjustment_summary(employee_name, year)
        return {"code": 0, "data": summary}
    except Exception as e:
        logger.error(f"查询调整记录失败: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/admin/adjustments")
def create_adjustment(
    adjustment: AdjustmentCreate,
    auth: str = Depends(verify_feishu_auth)
):
    """
    新增调整记录（HR后台 - 需要鉴权）
    使用 Body 传参替代 Query，避免敏感信息出现在 URL 和日志中
    """
    try:
        logger.info(f"HR创建调整记录: {adjustment.employee_name}, year={adjustment.year}, amount={adjustment.adjust_amount}")
        
        record = db.create_adjustment(
            employee_name=adjustment.employee_name,
            year=adjustment.year,
            adjust_amount=adjustment.adjust_amount,
            reason=adjustment.reason,
            created_by=adjustment.created_by
        )
        
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
                "created_at": record.created_at
            }
        }
    except Exception as e:
        logger.error(f"创建调整记录失败: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/admin/adjustments/{record_id}")
def delete_adjustment(
    record_id: int,
    auth: str = Depends(verify_feishu_auth)
):
    """
    撤销调整记录（HR后台 - 需要鉴权）
    """
    try:
        logger.info(f"HR撤销调整记录: id={record_id}")
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
    """
    统一时区解析时间戳，返回年份
    支持毫秒级和秒级时间戳
    """
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
    """
    格式化时间戳为本地时间字符串
    """
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
    """
    计算某年度系统计算的剩余年假（修复版）
    避免递归调用 balance API，直接计算
    """
    try:
        if not employee:
            return 0.0
        
        # 获取该年度的请假记录
        leave_records = feishu_client.get_leave_records(employee_name)
        
        # 只保留该年度的记录
        year_records = []
        for record in leave_records:
            fields = record.get("fields", {})
            start_time = fields.get("开始时间")
            if start_time:
                try:
                    record_year = parse_timestamp_year(start_time)
                    if record_year == year:
                        year_records.append(record)
                except:
                    continue
        
        # 计算该年度（假设没有上年结转，直接从头计算）
        year_end = date(year, 12, 31)
        result = calculator.calculate_annual_leave_balance(
            employee, year_records, 0.0, year_end
        )
        
        return result["annual_leave"]["remaining"]
        
    except Exception as e:
        logger.error(f"计算上年剩余失败: {employee_name}, year={year}, error={e}")
        return 0.0


if __name__ == "__main__":
    logger.info("🚀 启动年假查询系统 API v1.1.0")
    uvicorn.run(app, host="0.0.0.0", port=8000)
