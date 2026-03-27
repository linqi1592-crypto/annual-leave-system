"""
调整记录数据库模块 - v1.5 FIX
- P0-2: 调整记录操作人身份验证
- v1.5: 使用数据库适配器，支持 SQLite/PostgreSQL 自动切换
"""

import os
from datetime import datetime
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from config import DB_CONFIG, logger
from db_factory import create_database, DatabaseAdapter


@dataclass
class AdjustmentRecord:
    """调整记录数据类"""
    id: Optional[int] = None
    employee_name: str = ""
    year: int = 0
    adjust_amount: float = 0.0
    reason: str = ""
    created_by: str = ""
    created_by_open_id: Optional[str] = None
    adjustment_type: str = "manual"
    created_at: Optional[str] = None
    is_active: bool = True


class AdjustmentDB:
    """调整记录数据库操作类 - v1.5 FIX 使用数据库适配器"""
    
    def __init__(self, db_path: Optional[str] = None, pool_size: int = 5):
        if db_path is None:
            db_path = DB_CONFIG["path"]
        
        self.db_path = db_path
        self._ensure_db_dir()
        
        # v1.5 FIX: 使用数据库工厂自动选择 SQLite/PostgreSQL
        self.db: DatabaseAdapter = create_database()
        logger.info(f"AdjustmentDB 初始化完成，使用适配器: {type(self.db).__name__}")
        
        self._init_tables()
        self._migrate_v13()
    
    def _ensure_db_dir(self):
        """确保数据库目录存在（仅 SQLite 需要）"""
        db_dir = os.path.dirname(self.db_path)
        if db_dir and not os.path.exists(db_dir):
            os.makedirs(db_dir)
    
    def _init_tables(self):
        """初始化数据表"""
        # 使用适配器的 execute 方法
        self.db.execute("""
            CREATE TABLE IF NOT EXISTS adjustments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                employee_name TEXT NOT NULL,
                year INTEGER NOT NULL,
                adjust_amount REAL NOT NULL,
                reason TEXT,
                created_by TEXT NOT NULL,
                created_by_open_id TEXT,
                adjustment_type TEXT DEFAULT 'manual',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                is_active BOOLEAN DEFAULT 1
            )
        """)
        
        self.db.execute("""
            CREATE INDEX IF NOT EXISTS idx_employee_year 
            ON adjustments(employee_name, year)
        """)
        
        self.db.execute("""
            CREATE INDEX IF NOT EXISTS idx_adjustment_type 
            ON adjustments(adjustment_type)
        """)
    
    def _migrate_v13(self):
        """v1.3 数据库迁移"""
        try:
            # 尝试查询 created_by_open_id 字段
            self.db.fetchone("SELECT created_by_open_id FROM adjustments LIMIT 1")
        except:
            # 字段不存在，添加
            try:
                self.db.execute("ALTER TABLE adjustments ADD COLUMN created_by_open_id TEXT")
                logger.info("迁移: 添加 created_by_open_id 字段")
            except Exception as e:
                logger.warning(f"添加 created_by_open_id 字段失败: {e}")
        
        try:
            self.db.fetchone("SELECT adjustment_type FROM adjustments LIMIT 1")
        except:
            try:
                self.db.execute("ALTER TABLE adjustments ADD COLUMN adjustment_type TEXT DEFAULT 'manual'")
                logger.info("迁移: 添加 adjustment_type 字段")
            except Exception as e:
                logger.warning(f"添加 adjustment_type 字段失败: {e}")
    
    def create_adjustment(
        self,
        employee_name: str,
        year: int,
        adjust_amount: float,
        reason: str,
        created_by: str,
        created_by_open_id: Optional[str] = None,
        adjustment_type: str = "manual"
    ) -> AdjustmentRecord:
        """创建调整记录 - v1.5 FIX"""
        record_id = self.db.execute(
            """
            INSERT INTO adjustments 
            (employee_name, year, adjust_amount, reason, created_by, created_by_open_id, adjustment_type)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (employee_name, year, adjust_amount, reason, created_by, created_by_open_id, adjustment_type)
        )
        
        return self.get_adjustment_by_id(record_id)
    
    def get_adjustment_by_id(self, record_id: int) -> Optional[AdjustmentRecord]:
        """根据ID获取调整记录 - v1.5 FIX"""
        row = self.db.fetchone(
            "SELECT * FROM adjustments WHERE id = ?",
            (record_id,)
        )
        
        return self._row_to_record(row) if row else None
    
    def get_adjustments(
        self, 
        employee_name: Optional[str] = None,
        year: Optional[int] = None,
        adjustment_type: Optional[str] = None,
        only_active: bool = True
    ) -> List[AdjustmentRecord]:
        """查询调整记录 - v1.5 FIX"""
        conditions = []
        params = []
        
        if employee_name:
            conditions.append("employee_name = ?")
            params.append(employee_name)
        
        if year:
            conditions.append("year = ?")
            params.append(year)
        
        if adjustment_type:
            conditions.append("adjustment_type = ?")
            params.append(adjustment_type)
        
        if only_active:
            conditions.append("is_active = 1")
        
        where_clause = " AND ".join(conditions) if conditions else "1=1"
        
        rows = self.db.fetchall(
            f"SELECT * FROM adjustments WHERE {where_clause} ORDER BY created_at DESC",
            tuple(params)
        )
        
        return [self._row_to_record(row) for row in rows]
    
    def get_total_adjustment(
        self, 
        employee_name: str, 
        year: int,
        adjustment_type: Optional[str] = None
    ) -> float:
        """获取总调整值 - v1.5 FIX"""
        sql = """
            SELECT SUM(adjust_amount) as total 
            FROM adjustments 
            WHERE employee_name = ? AND year = ? AND is_active = 1
        """
        params = (employee_name, year)
        
        if adjustment_type:
            sql += " AND adjustment_type = ?"
            params = (employee_name, year, adjustment_type)
        
        row = self.db.fetchone(sql, params)
        return row["total"] if row and row["total"] else 0.0
    
    def deactivate_adjustment(self, record_id: int) -> bool:
        """撤销调整记录"""
        try:
            self.db.execute(
                "UPDATE adjustments SET is_active = 0 WHERE id = ?",
                (record_id,)
            )
            return True
        except Exception as e:
            logger.error(f"撤销调整记录失败: {e}")
            return False
    
    def get_adjustment_summary(
        self, 
        employee_name: str, 
        year: int
    ) -> Dict[str, Any]:
        """获取调整统计摘要"""
        # 总数
        total = self.get_total_adjustment(employee_name, year)
        
        # 手动调整
        manual = self.get_total_adjustment(employee_name, year, "manual")
        
        # 年终清算
        year_end = self.get_total_adjustment(employee_name, year, "year_end")
        
        # 记录数
        all_adjustments = self.get_adjustments(employee_name, year)
        
        return {
            "total": total,
            "manual": manual,
            "year_end": year_end,
            "record_count": len(all_adjustments)
        }
    
    def get_all_employees_with_adjustments(self, year: int) -> List[str]:
        """获取有调整记录的所有员工名称"""
        rows = self.db.fetchall(
            """
            SELECT DISTINCT employee_name 
            FROM adjustments 
            WHERE year = ? AND is_active = 1
            """,
            (year,)
        )
        return [row["employee_name"] for row in rows]
    
    def _row_to_record(self, row: Dict) -> AdjustmentRecord:
        """将数据库行转换为 AdjustmentRecord"""
        return AdjustmentRecord(
            id=row.get("id"),
            employee_name=row.get("employee_name", ""),
            year=row.get("year", 0),
            adjust_amount=row.get("adjust_amount", 0.0),
            reason=row.get("reason", ""),
            created_by=row.get("created_by", ""),
            created_by_open_id=row.get("created_by_open_id"),
            adjustment_type=row.get("adjustment_type", "manual"),
            created_at=row.get("created_at"),
            is_active=bool(row.get("is_active", 1))
        )


# 全局实例（延迟初始化）
_db: Optional[AdjustmentDB] = None

def get_adjustment_db() -> AdjustmentDB:
    """获取 AdjustmentDB 实例（单例）"""
    global _db
    if _db is None:
        _db = AdjustmentDB()
    return _db


# 兼容旧代码的直接导入
db = get_adjustment_db()
