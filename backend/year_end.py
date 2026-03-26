"""
年终清算模块 - v1.3 P1-4
年终清算流程：预览 -> 确认 -> 生成年结转记录
"""

import sqlite3
from datetime import date, datetime
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from fastapi import APIRouter, Query, Body, Depends, HTTPException
from pydantic import BaseModel
import logging

from auth import require_hr, User
from feishu_client import feishu_client
from adjustment_db import db, AdjustmentDB
from export import get_employee_leave_summary

logger = logging.getLogger(__name__)

year_end_router = APIRouter()


# ==================== 数据模型 ====================

class EmployeeSettlementDetail(BaseModel):
    """员工清算明细"""
    employee_name: str
    year_end_balance: float
    carryover_days: float
    cleared_days: float


class SettlementConfirmRequest(BaseModel):
    """清算确认请求"""
    year: int
    details: List[EmployeeSettlementDetail]


class SettlementPreview(BaseModel):
    """清算预览响应"""
    year: int
    total_employees: int
    total_carryover: float
    total_cleared: float
    details: List[Dict[str, Any]]


# ==================== 年终清算数据库 ====================

class YearEndSettlementDB:
    """年终清算数据库操作"""
    
    def __init__(self, db_path: str = "data/leave_adjustments.db"):
        self.db_path = db_path
        self._ensure_db_dir()
        self._init_tables()
    
    def _ensure_db_dir(self):
        """确保数据库目录存在"""
        import os
        db_dir = os.path.dirname(self.db_path)
        if db_dir and not os.path.exists(db_dir):
            os.makedirs(db_dir)
    
    def _get_connection(self) -> sqlite3.Connection:
        """获取数据库连接"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn
    
    def _init_tables(self):
        """初始化清算表"""
        with self._get_connection() as conn:
            # 清算主表
            conn.execute("""
                CREATE TABLE IF NOT EXISTS year_end_settlements (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    year INTEGER NOT NULL,
                    settled_by TEXT NOT NULL,
                    settled_by_open_id TEXT,
                    settled_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    total_employees INTEGER DEFAULT 0,
                    total_carryover REAL DEFAULT 0,
                    total_cleared REAL DEFAULT 0
                )
            """)
            
            # 清算明细表
            conn.execute("""
                CREATE TABLE IF NOT EXISTS year_end_settlement_details (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    settlement_id INTEGER NOT NULL,
                    employee_name TEXT NOT NULL,
                    year_end_balance REAL DEFAULT 0,
                    carryover_days REAL DEFAULT 0,
                    cleared_days REAL DEFAULT 0,
                    FOREIGN KEY (settlement_id) REFERENCES year_end_settlements(id)
                )
            """)
            
            # 创建索引
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_settlement_year 
                ON year_end_settlements(year)
            """)
            
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_settlement_detail_id 
                ON year_end_settlement_details(settlement_id)
            """)
            
            conn.commit()
    
    def create_settlement(
        self,
        year: int,
        settled_by: str,
        settled_by_open_id: Optional[str],
        details: List[Dict[str, Any]]
    ) -> int:
        """
        创建清算记录
        
        Returns:
            清算记录ID
        """
        with self._get_connection() as conn:
            # 插入主表
            cursor = conn.execute(
                """
                INSERT INTO year_end_settlements 
                (year, settled_by, settled_by_open_id, total_employees, total_carryover, total_cleared)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    year,
                    settled_by,
                    settled_by_open_id,
                    len(details),
                    sum(d["carryover_days"] for d in details),
                    sum(d["cleared_days"] for d in details)
                )
            )
            
            settlement_id = cursor.lastrowid
            
            # 插入明细
            for detail in details:
                conn.execute(
                    """
                    INSERT INTO year_end_settlement_details
                    (settlement_id, employee_name, year_end_balance, carryover_days, cleared_days)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        settlement_id,
                        detail["employee_name"],
                        detail["year_end_balance"],
                        detail["carryover_days"],
                        detail["cleared_days"]
                    )
                )
            
            conn.commit()
            return settlement_id
    
    def get_settlement_by_id(self, settlement_id: int) -> Optional[Dict[str, Any]]:
        """根据ID获取清算记录"""
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM year_end_settlements WHERE id = ?",
                (settlement_id,)
            ).fetchone()
            
            if not row:
                return None
            
            # 获取明细
            details = conn.execute(
                "SELECT * FROM year_end_settlement_details WHERE settlement_id = ?",
                (settlement_id,)
            ).fetchall()
            
            return {
                "id": row["id"],
                "year": row["year"],
                "settled_by": row["settled_by"],
                "settled_by_open_id": row["settled_by_open_id"],
                "settled_at": row["settled_at"],
                "total_employees": row["total_employees"],
                "total_carryover": row["total_carryover"],
                "total_cleared": row["total_cleared"],
                "details": [
                    {
                        "employee_name": d["employee_name"],
                        "year_end_balance": d["year_end_balance"],
                        "carryover_days": d["carryover_days"],
                        "cleared_days": d["cleared_days"]
                    }
                    for d in details
                ]
            }
    
    def get_settlements_by_year(self, year: int) -> List[Dict[str, Any]]:
        """获取某年度的所有清算记录"""
        with self._get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM year_end_settlements WHERE year = ? ORDER BY settled_at DESC",
                (year,)
            ).fetchall()
            
            return [
                {
                    "id": row["id"],
                    "year": row["year"],
                    "settled_by": row["settled_by"],
                    "settled_at": row["settled_at"],
                    "total_employees": row["total_employees"],
                    "total_carryover": row["total_carryover"],
                    "total_cleared": row["total_cleared"]
                }
                for row in rows
            ]
    
    def check_year_settled(self, year: int) -> bool:
        """检查某年度是否已清算"""
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT COUNT(*) as count FROM year_end_settlements WHERE year = ?",
                (year,)
            ).fetchone()
            return row["count"] > 0


# 全局数据库实例
settlement_db = YearEndSettlementDB()


# ==================== API 路由 ====================

@year_end_router.get("/api/admin/year-end/preview", response_model=SettlementPreview)
async def preview_year_end_settlement(
    year: int = Query(..., description="清算年份（如2025）"),
    current_user: User = Depends(require_hr)
):
    """
    年终清算预览
    
    展示所有员工的年末余额、预计结转天数（≤3天）、即将清零的天数
    """
    logger.info(f"HR查看年终清算预览: year={year}, user={current_user.name}")
    
    # 获取所有员工
    employees = feishu_client.get_employee_records()
    
    details = []
    for emp in employees:
        employee_name = emp.get("fields", {}).get("发起人", "")
        if not employee_name:
            continue
        
        # 获取员工年假汇总
        summary = get_employee_leave_summary(employee_name, year)
        if not summary:
            continue
        
        details.append({
            "employee_name": employee_name,
            "year_end_balance": summary["year_end_balance"],
            "carryover_days": summary["carryover_days"],
            "cleared_days": summary["cleared_days"],
            "current_year_quota": summary["current_year_quota"],
            "carryover_quota": summary["carryover_quota"],
            "total_used": summary["total_used"],
            "is_negative": summary["is_negative"]
        })
    
    # 按余额排序（从高到低）
    details.sort(key=lambda x: x["year_end_balance"], reverse=True)
    
    return {
        "year": year,
        "total_employees": len(details),
        "total_carryover": sum(d["carryover_days"] for d in details),
        "total_cleared": sum(d["cleared_days"] for d in details),
        "details": details
    }


@year_end_router.post("/api/admin/year-end/confirm")
async def confirm_year_end_settlement(
    request: SettlementConfirmRequest,
    current_user: User = Depends(require_hr)
):
    """
    确认年终清算
    
    为每个有余额结转的员工生成下一年度的结转调整记录
    """
    logger.info(f"HR确认年终清算: year={request.year}, user={current_user.name}")
    
    # 检查是否已清算
    if settlement_db.check_year_settled(request.year):
        raise HTTPException(status_code=400, detail=f"{request.year}年已进行过年终清算，请勿重复操作")
    
    # 过滤出有结转的员工
    carryover_details = [
        d for d in request.details
        if d.carryover_days > 0
    ]
    
    # 1. 创建清算记录
    settlement_id = settlement_db.create_settlement(
        year=request.year,
        settled_by=current_user.name,
        settled_by_open_id=current_user.open_id,
        details=[d.dict() for d in request.details]
    )
    
    # 2. 为每个员工生成年结转调整记录
    created_count = 0
    for detail in carryover_details:
        try:
            db.create_adjustment(
                employee_name=detail.employee_name,
                year=request.year + 1,  # 结转到下一年
                adjust_amount=detail.carryover_days,
                reason=f"{request.year}年年终清算结转",
                created_by=current_user.name,
                created_by_open_id=current_user.open_id,
                adjustment_type="year_end_carryover"
            )
            created_count += 1
        except Exception as e:
            logger.error(f"创建结转记录失败: {detail.employee_name}, error={e}")
    
    logger.info(f"年终清算完成: settlement_id={settlement_id}, 结转记录数={created_count}")
    
    return {
        "code": 0,
        "message": "年终清算完成",
        "data": {
            "settlement_id": settlement_id,
            "year": request.year,
            "total_employees": len(request.details),
            "carryover_employees": created_count,
            "total_carryover": sum(d.carryover_days for d in carryover_details),
            "total_cleared": sum(d.cleared_days for d in request.details)
        }
    }


@year_end_router.get("/api/admin/year-end/history")
async def get_settlement_history(
    year: Optional[int] = Query(None, description="查询年份（可选）"),
    current_user: User = Depends(require_hr)
):
    """
    查询清算历史记录
    """
    logger.info(f"HR查询清算历史: year={year}, user={current_user.name}")
    
    if year:
        settlements = settlement_db.get_settlements_by_year(year)
    else:
        # 获取最近10条
        with settlement_db._get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM year_end_settlements ORDER BY settled_at DESC LIMIT 10"
            ).fetchall()
            settlements = [
                {
                    "id": row["id"],
                    "year": row["year"],
                    "settled_by": row["settled_by"],
                    "settled_at": row["settled_at"],
                    "total_employees": row["total_employees"],
                    "total_carryover": row["total_carryover"],
                    "total_cleared": row["total_cleared"]
                }
                for row in rows
            ]
    
    return {
        "code": 0,
        "data": settlements
    }


@year_end_router.get("/api/admin/year-end/settlement/{settlement_id}")
async def get_settlement_detail(
    settlement_id: int,
    current_user: User = Depends(require_hr)
):
    """
    获取清算详情
    """
    settlement = settlement_db.get_settlement_by_id(settlement_id)
    if not settlement:
        raise HTTPException(status_code=404, detail="清算记录不存在")
    
    return {
        "code": 0,
        "data": settlement
    }


__all__ = [
    "year_end_router",
    "YearEndSettlementDB",
    "settlement_db"
]
