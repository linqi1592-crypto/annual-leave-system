"""
批量导出模块 - v1.3 P1-3
支持 CSV/Excel 格式导出全员年假数据
"""

import csv
import io
from datetime import date
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, Query, Response, Depends
from fastapi.responses import StreamingResponse
import logging

try:
    from openpyxl import Workbook
    OPENPYXL_AVAILABLE = True
except ImportError:
    OPENPYXL_AVAILABLE = False

from auth import require_hr
from feishu_client import feishu_client
from leave_calculator import calculator
from adjustment_db import db

logger = logging.getLogger(__name__)

export_router = APIRouter()


def calculate_year_end_balance(
    employee: Dict[str, Any],
    employee_name: str,
    year: int
) -> Dict[str, float]:
    """
    计算某员工某年度年末余额
    """
    try:
        from main import calculate_previous_year_remaining_v2
        
        # 获取该年度的请假记录
        leave_records = feishu_client.get_leave_records(employee_name)
        
        # 上年剩余（系统计算+调整）
        previous_year = year - 1
        previous_system_remaining = calculate_previous_year_remaining_v2(
            employee, employee_name, previous_year
        )
        adjustment = db.get_total_adjustment(employee_name, previous_year)
        previous_year_remaining = previous_system_remaining + adjustment
        
        # 计算当年余额
        year_end_date = date(year, 12, 31)
        result = calculator.calculate_annual_leave_balance(
            employee, leave_records, previous_year_remaining, year_end_date
        )
        
        return {
            "current_year_quota": result["annual_leave"]["current_year"]["quota"],
            "carryover": result["annual_leave"]["carryover"]["quota"],
            "total_used": result["annual_leave"]["total_used"],
            "remaining": result["annual_leave"]["remaining"],
            "is_negative": result["annual_leave"]["is_negative"]
        }
    except Exception as e:
        logger.error(f"计算年末余额失败: {employee_name}, year={year}, error={e}")
        return {
            "current_year_quota": 0,
            "carryover": 0,
            "total_used": 0,
            "remaining": 0,
            "is_negative": False
        }


def generate_export_data(year: Optional[int] = None) -> List[Dict[str, Any]]:
    """
    生成导出数据
    
    Args:
        year: 导出年份（默认当前年）
        
    Returns:
        全员年假数据列表
    """
    if year is None:
        year = date.today().year
    
    logger.info(f"开始生成导出数据: year={year}")
    
    # 获取所有员工
    employees = feishu_client.get_employee_records()
    
    data = []
    for emp in employees:
        fields = emp.get("fields", {})
        employee_name = fields.get("发起人", "")
        employee_id = fields.get("工号", "") or emp.get("record_id", "")[:8]
        entry_date = fields.get("入职时间", "")
        
        # 解析入职日期
        entry_date_str = ""
        if entry_date:
            try:
                if isinstance(entry_date, (int, float)):
                    from datetime import datetime
                    entry_date_str = datetime.fromtimestamp(entry_date / 1000).strftime("%Y-%m-%d")
                else:
                    entry_date_str = str(entry_date)[:10]
            except:
                entry_date_str = str(entry_date)
        
        # 计算司龄（月）
        from leave_calculator import calculator
        entry_date_obj = calculator._parse_date(entry_date)
        service_months = calculator.calculate_service_months(entry_date_obj, date.today())
        
        # 计算年假数据
        balance = calculate_year_end_balance(emp, employee_name, year)
        
        # 获取调整记录摘要
        adjustments = db.get_adjustments(employee_name, year - 1, only_active=True)
        adjustment_summary = "; ".join([
            f"{a.adjust_amount:+.1f}({a.reason[:10]}...)"
            for a in adjustments[:3]  # 只显示前3条
        ]) if adjustments else "无"
        
        data.append({
            "姓名": employee_name,
            "工号": employee_id,
            "入职日期": entry_date_str,
            "司龄(月)": service_months,
            "当年额度": balance["current_year_quota"],
            "上年结转": balance["carryover"],
            "已用天数": balance["total_used"],
            "余额": balance["remaining"],
            "是否透支": "是" if balance["is_negative"] else "否",
            "调整记录": adjustment_summary,
        })
    
    logger.info(f"导出数据生成完成: {len(data)} 条记录")
    return data


def generate_csv(data: List[Dict[str, Any]]) -> str:
    """生成 CSV 格式"""
    if not data:
        return ""
    
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=data[0].keys())
    writer.writeheader()
    writer.writerows(data)
    return output.getvalue()


def generate_excel(data: List[Dict[str, Any]]) -> bytes:
    """生成 Excel 格式"""
    if not OPENPYXL_AVAILABLE:
        raise ImportError("openpyxl 未安装，请运行: pip install openpyxl")
    
    if not data:
        return b""
    
    wb = Workbook()
    ws = wb.active
    ws.title = "年假数据"
    
    # 写入表头
    headers = list(data[0].keys())
    ws.append(headers)
    
    # 写入数据
    for row in data:
        ws.append(list(row.values()))
    
    # 设置列宽
    column_widths = {
        "姓名": 12,
        "工号": 12,
        "入职日期": 12,
        "司龄(月)": 10,
        "当年额度": 10,
        "上年结转": 10,
        "已用天数": 10,
        "余额": 10,
        "是否透支": 10,
        "调整记录": 30,
    }
    
    for i, header in enumerate(headers, 1):
        ws.column_dimensions[chr(64 + i)].width = column_widths.get(header, 12)
    
    # 保存到内存
    output = io.BytesIO()
    wb.save(output)
    output.seek(0)
    return output.getvalue()


@export_router.get("/api/admin/export")
async def export_leave_data(
    year: Optional[int] = Query(default=None, description="导出年份（默认当前年）"),
    format: str = Query(default="csv", regex="^(csv|xlsx)$", description="导出格式: csv 或 xlsx"),
    current_user = Depends(require_hr)
):
    """
    导出全员年假数据（HR权限）
    
    导出字段:
    - 姓名、工号、入职日期、司龄(月)
    - 当年额度、上年结转、已用天数、余额、是否透支
    - 调整记录摘要
    """
    logger.info(f"HR导出年假数据: year={year}, format={format}, user={current_user.name}")
    
    # 生成数据
    data = generate_export_data(year)
    
    if not data:
        raise HTTPException(status_code=404, detail="无数据可导出")
    
    # 生成文件名
    export_year = year or date.today().year
    timestamp = date.today().strftime("%Y%m%d")
    
    if format == "csv":
        content = generate_csv(data)
        filename = f"年假数据_{export_year}_{timestamp}.csv"
        media_type = "text/csv; charset=utf-8-sig"  # UTF-8 with BOM for Excel
        
        return Response(
            content=content.encode("utf-8-sig"),
            media_type=media_type,
            headers={
                "Content-Disposition": f"attachment; filename={filename}",
                "Cache-Control": "no-cache"
            }
        )
    
    else:  # xlsx
        content = generate_excel(data)
        filename = f"年假数据_{export_year}_{timestamp}.xlsx"
        media_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        
        return Response(
            content=content,
            media_type=media_type,
            headers={
                "Content-Disposition": f"attachment; filename={filename}",
                "Cache-Control": "no-cache"
            }
        )


# 导出辅助函数供年终清算使用
def get_employee_leave_summary(employee_name: str, year: int) -> Dict[str, Any]:
    """
    获取员工年假汇总（供年终清算使用）
    
    Returns:
        {
            "employee_name": 员工姓名,
            "year_end_balance": 年末余额,
            "carryover_days": 应结转天数,
            "cleared_days": 应清零天数,
            "current_year_quota": 当年额度,
            "carryover_quota": 上年结转额度,
            "total_used": 已用天数,
        }
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
            return None
        
        # 计算年末余额
        balance = calculate_year_end_balance(employee, employee_name, year)
        
        year_end_balance = balance["remaining"]
        carryover_days = min(year_end_balance, 3) if year_end_balance > 0 else 0
        cleared_days = max(0, year_end_balance - 3) if year_end_balance > 0 else 0
        
        return {
            "employee_name": employee_name,
            "year_end_balance": year_end_balance,
            "carryover_days": carryover_days,
            "cleared_days": cleared_days,
            "current_year_quota": balance["current_year_quota"],
            "carryover_quota": balance["carryover"],
            "total_used": balance["total_used"],
            "is_negative": balance["is_negative"]
        }
    except Exception as e:
        logger.error(f"获取员工年假汇总失败: {employee_name}, error={e}")
        return None


from fastapi import HTTPException

__all__ = [
    "export_router",
    "generate_export_data",
    "get_employee_leave_summary"
]
