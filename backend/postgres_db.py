"""
PostgreSQL 数据库支持 - v1.5 企业级改造
使用 SQLAlchemy ORM + 连接池
"""

import os
from typing import Optional, List, Dict, Any
from datetime import datetime
from dataclasses import dataclass

try:
    from sqlalchemy import create_engine, Column, Integer, String, Float, Boolean, DateTime, Text
    from sqlalchemy.ext.declarative import declarative_base
    from sqlalchemy.orm import sessionmaker, Session
    from sqlalchemy.pool import QueuePool
    SQLALCHEMY_AVAILABLE = True
except ImportError:
    SQLALCHEMY_AVAILABLE = False

from config import DB_CONFIG
import logging

logger = logging.getLogger(__name__)

Base = declarative_base()


class AdjustmentModel(Base):
    """调整记录表模型"""
    __tablename__ = 'adjustments'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    employee_name = Column(String(100), nullable=False, index=True)
    year = Column(Integer, nullable=False, index=True)
    adjust_amount = Column(Float, nullable=False)
    reason = Column(Text)
    created_by = Column(String(100), nullable=False)
    created_by_open_id = Column(String(100))
    adjustment_type = Column(String(50), default='manual')
    created_at = Column(DateTime, default=datetime.utcnow)
    is_active = Column(Boolean, default=True)


class YearEndSettlementModel(Base):
    """年终清算记录表"""
    __tablename__ = 'year_end_settlements'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    year = Column(Integer, nullable=False, index=True)
    settled_by = Column(String(100), nullable=False)
    settled_by_open_id = Column(String(100))
    total_employees = Column(Integer, default=0)
    total_carryover = Column(Float, default=0.0)
    total_cleared = Column(Float, default=0.0)
    settled_at = Column(DateTime, default=datetime.utcnow)


class YearEndSettlementDetailModel(Base):
    """年终清算明细表"""
    __tablename__ = 'year_end_settlement_details'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    settlement_id = Column(Integer, nullable=False, index=True)
    employee_name = Column(String(100), nullable=False)
    year_end_balance = Column(Float, default=0.0)
    carryover_days = Column(Float, default=0.0)
    cleared_days = Column(Float, default=0.0)


class PostgresDB:
    """PostgreSQL 数据库操作类"""
    
    def __init__(self, database_url: str = None, pool_size: int = 10):
        if not SQLALCHEMY_AVAILABLE:
            raise ImportError("SQLAlchemy 未安装，请运行: pip install sqlalchemy psycopg2-binary")
        
        self.database_url = database_url or os.getenv(
            'DATABASE_URL', 
            'postgresql://user:password@localhost:5432/annual_leave'
        )
        
        # 创建引擎（带连接池）
        self.engine = create_engine(
            self.database_url,
            poolclass=QueuePool,
            pool_size=pool_size,
            max_overflow=20,
            pool_pre_ping=True,  # 自动检测断开的连接
            pool_recycle=3600,   # 1小时回收连接
            echo=False
        )
        
        # 创建表
        Base.metadata.create_all(self.engine)
        
        # 创建会话工厂
        self.SessionLocal = sessionmaker(bind=self.engine)
        
        logger.info(f"PostgreSQL 连接池初始化完成: pool_size={pool_size}")
    
    def get_session(self) -> Session:
        """获取数据库会话"""
        return self.SessionLocal()
    
    # ==================== 调整记录操作 ====================
    
    def create_adjustment(
        self,
        employee_name: str,
        year: int,
        adjust_amount: float,
        reason: str,
        created_by: str,
        created_by_open_id: Optional[str] = None,
        adjustment_type: str = "manual"
    ) -> Dict:
        """创建调整记录"""
        session = self.get_session()
        try:
            adjustment = AdjustmentModel(
                employee_name=employee_name,
                year=year,
                adjust_amount=adjust_amount,
                reason=reason,
                created_by=created_by,
                created_by_open_id=created_by_open_id,
                adjustment_type=adjustment_type
            )
            session.add(adjustment)
            session.commit()
            session.refresh(adjustment)
            
            return self._adjustment_to_dict(adjustment)
        finally:
            session.close()
    
    def get_adjustments(
        self,
        employee_name: Optional[str] = None,
        year: Optional[int] = None,
        adjustment_type: Optional[str] = None,
        only_active: bool = True
    ) -> List[Dict]:
        """查询调整记录"""
        session = self.get_session()
        try:
            query = session.query(AdjustmentModel)
            
            if employee_name:
                query = query.filter(AdjustmentModel.employee_name == employee_name)
            if year:
                query = query.filter(AdjustmentModel.year == year)
            if adjustment_type:
                query = query.filter(AdjustmentModel.adjustment_type == adjustment_type)
            if only_active:
                query = query.filter(AdjustmentModel.is_active == True)
            
            adjustments = query.order_by(AdjustmentModel.created_at.desc()).all()
            return [self._adjustment_to_dict(adj) for adj in adjustments]
        finally:
            session.close()
    
    def get_total_adjustment(
        self,
        employee_name: str,
        year: int,
        adjustment_type: Optional[str] = None
    ) -> float:
        """获取总调整值"""
        session = self.get_session()
        try:
            query = session.query(AdjustmentModel).filter(
                AdjustmentModel.employee_name == employee_name,
                AdjustmentModel.year == year,
                AdjustmentModel.is_active == True
            )
            
            if adjustment_type:
                query = query.filter(AdjustmentModel.adjustment_type == adjustment_type)
            
            total = query.with_entities(
                AdjustmentModel.adjust_amount
            ).all()
            
            return sum(adj.adjust_amount for adj in total) if total else 0.0
        finally:
            session.close()
    
    def deactivate_adjustment(self, record_id: int) -> bool:
        """撤销调整记录"""
        session = self.get_session()
        try:
            adjustment = session.query(AdjustmentModel).filter(
                AdjustmentModel.id == record_id
            ).first()
            
            if adjustment:
                adjustment.is_active = False
                session.commit()
                return True
            return False
        finally:
            session.close()
    
    def get_adjustment_summary(self, employee_name: str, year: int) -> Dict:
        """获取调整汇总"""
        adjustments = self.get_adjustments(employee_name, year, only_active=True)
        total = self.get_total_adjustment(employee_name, year)
        
        return {
            "employee_name": employee_name,
            "year": year,
            "record_count": len(adjustments),
            "total_adjustment": total,
            "records": [
                {
                    "id": adj["id"],
                    "adjust_amount": adj["adjust_amount"],
                    "reason": adj["reason"],
                    "created_by": adj["created_by"],
                    "created_by_open_id": adj["created_by_open_id"],
                    "adjustment_type": adj["adjustment_type"],
                    "created_at": adj["created_at"].isoformat() if adj["created_at"] else None,
                }
                for adj in adjustments
            ]
        }
    
    def _adjustment_to_dict(self, adjustment: AdjustmentModel) -> Dict:
        """转换为字典"""
        return {
            "id": adjustment.id,
            "employee_name": adjustment.employee_name,
            "year": adjustment.year,
            "adjust_amount": adjustment.adjust_amount,
            "reason": adjustment.reason,
            "created_by": adjustment.created_by,
            "created_by_open_id": adjustment.created_by_open_id,
            "adjustment_type": adjustment.adjustment_type,
            "created_at": adjustment.created_at,
            "is_active": adjustment.is_active
        }
    
    # ==================== 年终清算操作 ====================
    
    def create_year_end_settlement(
        self,
        year: int,
        settled_by: str,
        settled_by_open_id: Optional[str],
        total_employees: int,
        total_carryover: float,
        total_cleared: float,
        details: List[Dict]
    ) -> int:
        """创建年终清算记录"""
        session = self.get_session()
        try:
            settlement = YearEndSettlementModel(
                year=year,
                settled_by=settled_by,
                settled_by_open_id=settled_by_open_id,
                total_employees=total_employees,
                total_carryover=total_carryover,
                total_cleared=total_cleared
            )
            session.add(settlement)
            session.commit()
            session.refresh(settlement)
            
            # 创建明细
            for detail in details:
                detail_record = YearEndSettlementDetailModel(
                    settlement_id=settlement.id,
                    employee_name=detail["employee_name"],
                    year_end_balance=detail["year_end_balance"],
                    carryover_days=detail["carryover_days"],
                    cleared_days=detail["cleared_days"]
                )
                session.add(detail_record)
            
            session.commit()
            return settlement.id
        finally:
            session.close()
    
    def check_year_settled(self, year: int) -> bool:
        """检查年度是否已清算"""
        session = self.get_session()
        try:
            count = session.query(YearEndSettlementModel).filter(
                YearEndSettlementModel.year == year
            ).count()
            return count > 0
        finally:
            session.close()
    
    def health_check(self) -> Dict:
        """健康检查"""
        try:
            session = self.get_session()
            session.execute("SELECT 1")
            session.close()
            
            return {
                "status": "healthy",
                "database": "postgresql",
                "connected": True
            }
        except Exception as e:
            return {
                "status": "unhealthy",
                "database": "postgresql",
                "connected": False,
                "error": str(e)
            }


# 数据库工厂函数
def create_database(db_type: str = None):
    """
    创建数据库实例
    
    Args:
        db_type: 'sqlite', 'postgres', 或自动检测
    """
    db_type = db_type or os.getenv('DB_TYPE', 'sqlite')
    
    if db_type == 'postgres':
        if not SQLALCHEMY_AVAILABLE:
            logger.error("SQLAlchemy 未安装，无法使用 PostgreSQL")
            raise ImportError("pip install sqlalchemy psycopg2-binary")
        
        return PostgresDB()
    else:
        # SQLite 回退
        from adjustment_db import AdjustmentDB
        return AdjustmentDB()


# 全局实例（根据配置自动选择）
# db = create_database()


if __name__ == "__main__":
    print("测试 PostgreSQL 支持...")
    
    if not SQLALCHEMY_AVAILABLE:
        print("✗ SQLAlchemy 未安装")
        print("请运行: pip install sqlalchemy psycopg2-binary")
        exit(1)
    
    try:
        # 测试连接
        pg_db = PostgresDB(pool_size=5)
        
        # 健康检查
        health = pg_db.health_check()
        print(f"✓ 健康检查: {health}")
        
        # 创建测试记录
        result = pg_db.create_adjustment(
            employee_name="张三",
            year=2025,
            adjust_amount=1.5,
            reason="测试",
            created_by="HR"
        )
        print(f"✓ 创建记录: ID={result['id']}")
        
        # 查询
        summary = pg_db.get_adjustment_summary("张三", 2025)
        print(f"✓ 查询汇总: {summary['record_count']} 条记录")
        
        print("\n✅ PostgreSQL 测试通过")
        
    except Exception as e:
        print(f"✗ 测试失败: {e}")
        print("请确保 PostgreSQL 服务已启动")
