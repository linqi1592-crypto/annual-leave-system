"""
年假查询系统 - FastAPI 主服务
"""

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional, List
from datetime import date
import uvicorn

from feishu_client import feishu_client
from leave_calculator import calculator
from adjustment_db import db

app = FastAPI(
    title="年假查询系统",
    description="飞书年假查询 API",
    version="1.0.0"
)

# CORS 配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 生产环境需要限制
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def root():
    """根路径"""
    return {"message": "年假查询系统 API", "version": "1.0.0"}


@app.get("/api/leave/balance")
def get_leave_balance(
    employee_name: str = Query(..., description="员工姓名"),
    year: Optional[int] = Query(None, description="查询年份（默认当前年）")
):
    """
    查询年假余额
    
    - employee_name: 员工姓名
    - year: 查询年份（默认今年）
    """
    try:
        # 默认当前年
        if year is None:
            year = date.today().year
        
        # 1. 获取员工信息
        employees = feishu_client.get_employee_records()
        employee = None
        for emp in employees:
            if emp.get("fields", {}).get("发起人") == employee_name:
                employee = emp
                break
        
        if not employee:
            raise HTTPException(status_code=404, detail=f"未找到员工: {employee_name}")
        
        # 2. 获取请假记录
        leave_records = feishu_client.get_leave_records(employee_name)
        
        # 3. 计算上年剩余（含调整）
        previous_year = year - 1
        previous_system_remaining = calculate_previous_year_remaining(
            employee_name, previous_year
        )
        adjustment = db.get_total_adjustment(employee_name, previous_year)
        previous_year_remaining = previous_system_remaining + adjustment
        
        # 4. 计算年假余额
        current_date = date(year, date.today().month, date.today().day)
        result = calculator.calculate_annual_leave_balance(
            employee, leave_records, previous_year_remaining, current_date
        )
        
        # 5. 添加调整信息
        result["adjustment"] = {
            "system_remaining": previous_system_remaining,
            "adjustment_amount": adjustment,
            "final_remaining": previous_year_remaining
        }
        
        return {"code": 0, "data": result}
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/leave/history")
def get_leave_history(
    employee_name: str = Query(..., description="员工姓名"),
    year: Optional[int] = Query(None, description="查询年份（默认当前年）")
):
    """
    查询请假明细
    
    - employee_name: 员工姓名
    - year: 查询年份（默认今年）
    """
    try:
        if year is None:
            year = date.today().year
        
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
                    if isinstance(start_time, (int, float)):
                        from datetime import datetime
                        record_year = datetime.fromtimestamp(start_time / 1000).year
                    else:
                        record_year = int(start_time[:4])
                    
                    if record_year != year:
                        continue
                except:
                    continue
            
            leave_type = fields.get("请假类型", "")
            status = fields.get("申请状态", "")
            duration = fields.get("时长", 0) or 0
            
            # 只统计年假和事假
            if leave_type not in ["年假", "事假"]:
                continue
            
            records.append({
                "apply_no": fields.get("申请编号", ""),
                "type": leave_type,
                "status": status,
                "start_date": fields.get("开始时间", ""),
                "end_date": fields.get("结束时间", ""),
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
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/leave/rules")
def get_leave_rules(employee_name: str = Query(..., description="员工姓名")):
    """
    查询年假计算规则（该员工的计算明细）
    """
    try:
        # 获取员工信息
        employees = feishu_client.get_employee_records()
        employee = None
        for emp in employees:
            if emp.get("fields", {}).get("发起人") == employee_name:
                employee = emp
                break
        
        if not employee:
            raise HTTPException(status_code=404, detail=f"未找到员工: {employee_name}")
        
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
        raise HTTPException(status_code=500, detail=str(e))


# ==================== 后台管理 API ====================

@app.get("/api/admin/adjustments")
def get_adjustments(
    employee_name: str = Query(..., description="员工姓名"),
    year: int = Query(..., description="调整年度")
):
    """
    查询调整记录（HR后台）
    """
    try:
        summary = db.get_adjustment_summary(employee_name, year)
        return {"code": 0, "data": summary}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/admin/adjustments")
def create_adjustment(
    employee_name: str = Query(..., description="员工姓名"),
    year: int = Query(..., description="调整年度"),
    adjust_amount: float = Query(..., description="调整金额（正数增加，负数减少）"),
    reason: str = Query(..., description="调整原因"),
    created_by: str = Query(..., description="操作人")
):
    """
    新增调整记录（HR后台）
    """
    try:
        record = db.create_adjustment(
            employee_name=employee_name,
            year=year,
            adjust_amount=adjust_amount,
            reason=reason,
            created_by=created_by
        )
        
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
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/admin/adjustments/{record_id}")
def delete_adjustment(record_id: int):
    """
    撤销调整记录（HR后台）
    """
    try:
        success = db.deactivate_adjustment(record_id)
        if not success:
            raise HTTPException(status_code=404, detail="调整记录不存在")
        
        return {
            "code": 0,
            "message": "调整记录已撤回",
            "data": {"id": record_id, "is_active": False}
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ==================== 辅助函数 ====================

def calculate_previous_year_remaining(employee_name: str, year: int) -> float:
    """
    计算某年度系统计算的剩余年假
    用于计算上年剩余（不含调整）
    """
    try:
        # 获取员工信息
        employees = feishu_client.get_employee_records()
        employee = None
        for emp in employees:
            if emp.get("fields", {}).get("发起人") == employee_name:
                employee = emp
                break
        
        if not employee:
            return 0.0
        
        # 获取请假记录
        leave_records = feishu_client.get_leave_records(employee_name)
        
        # 计算该年度（假设没有上年结转）
        from datetime import date
        year_end = date(year, 12, 31)
        result = calculator.calculate_annual_leave_balance(
            employee, leave_records, 0.0, year_end
        )
        
        return result["annual_leave"]["remaining"]
        
    except:
        return 0.0


if __name__ == "__main__":
    print("🚀 启动年假查询系统 API...")
    uvicorn.run(app, host="0.0.0.0", port=8000)
