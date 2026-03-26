"""
调整记录数据库模块 - v1.3 更新
- P0-2: 调整记录操作人身份验证（添加 created_by_open_id 字段）
- 添加 adjustment_type 字段支持年终清算
"""

import sqlite3
import os
from datetime import datetime
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from config import DB_CONFIG


@dataclass
class AdjustmentRecord:
    """调整记录数据类 - v1.3 更新"""
    id: Optional[int] = None
    employee_name: str = ""
    year: int = 0
    adjust_amount: float = 0.0  # 正数增加，负数减少
    reason: str = ""
    created_by: str = ""  # 操作人姓名
    created_by_open_id: Optional[str] = None  # v1.3: 操作人飞书Open ID
    adjustment_type: str = "manual"  # v1.3: 调整类型（manual/year_end_carryover）
    created_at: Optional[str] = None
    is_active: bool = True


class AdjustmentDB:
    """调整记录数据库操作类 - v1.3 更新"""
    
    def __init__(self, db_path: Optional[str] = None):
        if db_path is None:
            db_path = DB_CONFIG["path"]
        
        self.db_path = db_path
        self._ensure_db_dir()
        self._init_tables()
        self._migrate_v13()  # v1.3: 数据库迁移
    
    def _ensure_db_dir(self):
        """确保数据库目录存在"""
        db_dir = os.path.dirname(self.db_path)
        if db_dir and not os.path.exists(db_dir):
            os.makedirs(db_dir)
    
    def _get_connection(self) -> sqlite3.Connection:
        """获取数据库连接"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn
    
    def _init_tables(self):
        """初始化数据表"""
        with self._get_connection() as conn:
            conn.execute("""
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
            
            # 创建索引
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_employee_year 
                ON adjustments(employee_name, year)
            """)
            
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_adjustment_type 
                ON adjustments(adjustment_type)
            """)
            
            conn.commit()
    
    def _migrate_v13(self):
        """v1.3 数据库迁移 - 添加新字段"""
        with self._get_connection() as conn:
            # 检查并添加 created_by_open_id 字段
            cursor = conn.execute("PRAGMA table_info(adjustments)")
            columns = [row[1] for row in cursor.fetchall()]
            
            if "created_by_open_id" not in columns:
                conn.execute("ALTER TABLE adjustments ADD COLUMN created_by_open_id TEXT")
                print("[DB Migrate v1.3] 添加 created_by_open_id 字段")
            
            if "adjustment_type" not in columns:
                conn.execute("ALTER TABLE adjustments ADD COLUMN adjustment_type TEXT DEFAULT 'manual'")
                print("[DB Migrate v1.3] 添加 adjustment_type 字段")
            
            conn.commit()
    
    def create_adjustment(
        self, 
        employee_name: str, 
        year: int, 
        adjust_amount: float,
        reason: str,
        created_by: str,
        created_by_open_id: Optional[str] = None,  # v1.3: 自动传入
        adjustment_type: str = "manual"  # v1.3: 调整类型
    ) -> AdjustmentRecord:
        """
        创建调整记录 - v1.3 更新
        
        Args:
            employee_name: 员工姓名
            year: 调整年度
            adjust_amount: 调整金额（正数增加，负数减少）
            reason: 调整原因
            created_by: 操作人姓名（自动从 session 获取）
            created_by_open_id: 操作人飞书Open ID（自动从 session 获取）
            adjustment_type: 调整类型（manual/year_end_carryover）
            
        Returns:
            创建的记录
        """
        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                INSERT INTO adjustments 
                (employee_name, year, adjust_amount, reason, created_by, created_by_open_id, adjustment_type)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (employee_name, year, adjust_amount, reason, created_by, created_by_open_id, adjustment_type)
            )
            conn.commit()
            
            # 获取刚插入的记录
            record_id = cursor.lastrowid
            return self.get_adjustment_by_id(record_id)
    
    def get_adjustment_by_id(self, record_id: int) -> Optional[AdjustmentRecord]:
        """根据ID获取调整记录"""
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM adjustments WHERE id = ?",
                (record_id,)
            ).fetchone()
            
            if row:
                return self._row_to_record(row)
            return None
    
    def get_adjustments(
        self, 
        employee_name: Optional[str] = None,
        year: Optional[int] = None,
        adjustment_type: Optional[str] = None,  # v1.3: 按类型筛选
        only_active: bool = True
    ) -> List[AdjustmentRecord]:
        """
        查询调整记录 - v1.3 更新
        
        Args:
            employee_name: 按员工姓名筛选
            year: 按年度筛选
            adjustment_type: 按调整类型筛选（manual/year_end_carryover）
            only_active: 只返回有效记录
            
        Returns:
            调整记录列表
        """
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
        
        with self._get_connection() as conn:
            rows = conn.execute(
                f"SELECT * FROM adjustments WHERE {where_clause} ORDER BY created_at DESC",
                params
            ).fetchall()
            
            return [self._row_to_record(row) for row in rows]
    
    def get_total_adjustment(
        self, 
        employee_name: str, 
        year: int,
        adjustment_type: Optional[str] = None  # v1.3: 按类型筛选
    ) -> float:
        """
        获取某员工某年度的总调整值 - v1.3 更新
        
        Args:
            employee_name: 员工姓名
            year: 年度
            adjustment_type: 调整类型筛选（可选）
            
        Returns:
            总调整金额（正数增加，负数减少）
        """
        with self._get_connection() as conn:
            sql = """
                SELECT SUM(adjust_amount) as total 
                FROM adjustments 
                WHERE employee_name = ? AND year = ? AND is_active = 1
            """
            params = [employee_name, year]
            
            if adjustment_type:
                sql += " AND adjustment_type = ?"
                params.append(adjustment_type)
            
            row = conn.execute(sql, params).fetchone()
            return row["total"] or 0.0
    
    def deactivate_adjustment(self, record_id: int) -> bool:
        """
        撤销（软删除）调整记录
        
        Args:
            record_id: 记录ID
            
        Returns:
            是否成功
        """
        with self._get_connection() as conn:
            cursor = conn.execute(
                "UPDATE adjustments SET is_active = 0 WHERE id = ?",
                (record_id,)
            )
            conn.commit()
            return cursor.rowcount > 0
    
    def delete_adjustment(self, record_id: int) -> bool:
        """
        硬删除调整记录（慎用）
        
        Args:
            record_id: 记录ID
            
        Returns:
            是否成功
        """
        with self._get_connection() as conn:
            cursor = conn.execute(
                "DELETE FROM adjustments WHERE id = ?",
                (record_id,)
            )
            conn.commit()
            return cursor.rowcount > 0
    
    def get_adjustment_summary(
        self, 
        employee_name: str, 
        year: int
    ) -> Dict[str, Any]:
        """
        获取调整汇总信息（用于显示）- v1.3 更新
        
        Args:
            employee_name: 员工姓名
            year: 年度
            
        Returns:
            汇总信息（包含操作人 open_id）
        """
        records = self.get_adjustments(employee_name, year, only_active=True)
        total = self.get_total_adjustment(employee_name, year)
        
        return {
            "employee_name": employee_name,
            "year": year,
            "record_count": len(records),
            "total_adjustment": total,
            "records": [
                {
                    "id": r.id,
                    "adjust_amount": r.adjust_amount,
                    "reason": r.reason,
                    "created_by": r.created_by,
                    "created_by_open_id": r.created_by_open_id,  # v1.3
                    "adjustment_type": r.adjustment_type,  # v1.3
                    "created_at": r.created_at,
                }
                for r in records
            ]
        }
    
    def get_yearly_carryover_adjustments(self, year: int) -> List[AdjustmentRecord]:
        """
        v1.3 P1-4: 获取某年度的年终结转调整记录
        
        Args:
            year: 年度（结转到该年）
            
        Returns:
            年终结转调整记录列表
        """
        return self.get_adjustments(
            year=year,
            adjustment_type="year_end_carryover",
            only_active=True
        )
    
    def _row_to_record(self, row: sqlite3.Row) -> AdjustmentRecord:
        """将数据库行转换为记录对象 - v1.3 更新"""
        return AdjustmentRecord(
            id=row["id"],
            employee_name=row["employee_name"],
            year=row["year"],
            adjust_amount=row["adjust_amount"],
            reason=row["reason"],
            created_by=row["created_by"],
            created_by_open_id=row.get("created_by_open_id"),
            adjustment_type=row.get("adjustment_type", "manual"),
            created_at=row["created_at"],
            is_active=bool(row["is_active"])
        )


# 全局数据库实例
db = AdjustmentDB()


if __name__ == "__main__":
    # 测试
    print("测试调整记录数据库 v1.3...")
    
    test_db = AdjustmentDB("test_adjustments_v13.db")
    
    # 创建测试记录（模拟操作人自动记录）
    print("\n1. 创建手动调整记录...")
    record1 = test_db.create_adjustment(
        employee_name="张三",
        year=2025,
        adjust_amount=1.5,
        reason="漏计年假补录",
        created_by="HR小王",  # 自动从 session 获取
        created_by_open_id="ou_abc123",  # 自动从 session 获取
        adjustment_type="manual"
    )
    print(f"   创建: ID={record1.id}, 操作人={record1.created_by}, open_id={record1.created_by_open_id}")
    
    # 创建年终结转记录
    print("\n2. 创建年终结转记录...")
    record2 = test_db.create_adjustment(
        employee_name="张三",
        year=2026,  # 结转到2026年
        adjust_amount=3.0,
        reason="2025年年终清算结转",
        created_by="HR小王",
        created_by_open_id="ou_abc123",
        adjustment_type="year_end_carryover"
    )
    print(f"   创建: ID={record2.id}, 类型={record2.adjustment_type}")
    
    # 查询记录
    print("\n3. 查询张三2025年调整记录...")
    summary = test_db.get_adjustment_summary("张三", 2025)
    print(f"   记录数: {summary['record_count']}")
    print(f"   总调整: {summary['total_adjustment']}天")
    
    # 查询年终结转记录
    print("\n4. 查询2026年年终结转记录...")
    carryover_records = test_db.get_yearly_carryover_adjustments(2026)
    print(f"   结转记录数: {len(carryover_records)}")
    
    # 清理测试文件
    import os
    os.remove("test_adjustments_v13.db")
    
    print("\n✅ 数据库测试完成")
