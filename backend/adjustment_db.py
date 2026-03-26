"""
调整记录数据库模块 - v1.5 更新
- P0-2: 调整记录操作人身份验证
- v1.5: 使用连接池解决并发问题
"""

import os
from datetime import datetime
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from config import DB_CONFIG
from db_pool import PooledDB


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
    """调整记录数据库操作类 - v1.5 使用连接池"""
    
    def __init__(self, db_path: Optional[str] = None, pool_size: int = 5):
        if db_path is None:
            db_path = DB_CONFIG["path"]
        
        self.db_path = db_path
        self._ensure_db_dir()
        
        # v1.5: 使用连接池
        self.pool = PooledDB(db_path, pool_size=pool_size)
        self._init_tables()
        self._migrate_v13()
    
    def _ensure_db_dir(self):
        """确保数据库目录存在"""
        db_dir = os.path.dirname(self.db_path)
        if db_dir and not os.path.exists(db_dir):
            os.makedirs(db_dir)
    
    def _init_tables(self):
        """初始化数据表"""
        self.pool.execute("""
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
        
        self.pool.execute("""
            CREATE INDEX IF NOT EXISTS idx_employee_year 
            ON adjustments(employee_name, year)
        """)
        
        self.pool.execute("""
            CREATE INDEX IF NOT EXISTS idx_adjustment_type 
            ON adjustments(adjustment_type)
        """)
    
    def _migrate_v13(self):
        """v1.3 数据库迁移"""
        try:
            self.pool.execute("ALTER TABLE adjustments ADD COLUMN created_by_open_id TEXT")
            print("[DB Migrate v1.3] 添加 created_by_open_id 字段")
        except:
            pass
        
        try:
            self.pool.execute("ALTER TABLE adjustments ADD COLUMN adjustment_type TEXT DEFAULT 'manual'")
            print("[DB Migrate v1.3] 添加 adjustment_type 字段")
        except:
            pass
    
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
        """创建调整记录 - v1.5 使用连接池"""
        record_id = self.pool.execute(
            """
            INSERT INTO adjustments 
            (employee_name, year, adjust_amount, reason, created_by, created_by_open_id, adjustment_type)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (employee_name, year, adjust_amount, reason, created_by, created_by_open_id, adjustment_type)
        )
        
        return self.get_adjustment_by_id(record_id)
    
    def get_adjustment_by_id(self, record_id: int) -> Optional[AdjustmentRecord]:
        """根据ID获取调整记录"""
        row = self.pool.execute(
            "SELECT * FROM adjustments WHERE id = ?",
            (record_id,),
            fetch=True,
            fetch_one=True
        )
        
        return self._row_to_record(row) if row else None
    
    def get_adjustments(
        self, 
        employee_name: Optional[str] = None,
        year: Optional[int] = None,
        adjustment_type: Optional[str] = None,
        only_active: bool = True
    ) -> List[AdjustmentRecord]:
        """查询调整记录 - v1.5 使用连接池"""
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
        
        rows = self.pool.execute(
            f"SELECT * FROM adjustments WHERE {where_clause} ORDER BY created_at DESC",
            params,
            fetch=True
        )
        
        return [self._row_to_record(row) for row in rows]
    
    def get_total_adjustment(
        self, 
        employee_name: str, 
        year: int,
        adjustment_type: Optional[str] = None
    ) -> float:
        """获取总调整值 - v1.5 使用连接池"""
        sql = """
            SELECT SUM(adjust_amount) as total 
            FROM adjustments 
            WHERE employee_name = ? AND year = ? AND is_active = 1
        """
        params = [employee_name, year]
        
        if adjustment_type:
            sql += " AND adjustment_type = ?"
            params.append(adjustment_type)
        
        row = self.pool.execute(sql, params, fetch=True, fetch_one=True)
        return row["total"] if row and row["total"] else 0.0
    
    def deactivate_adjustment(self, record_id: int) -> bool:
        """撤销调整记录"""
        try:
            self.pool.execute(
                "UPDATE adjustments SET is_active = 0 WHERE id = ?",
                (record_id,)
            )
            return True
        except:
            return False
    
    def get_adjustment_summary(
        self, 
        employee_name: str, 
        year: int
    ) -> Dict[str, Any]:
        """获取调整汇总信息"""
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
                    "created_by_open_id": r.created_by_open_id,
                    "adjustment_type": r.adjustment_type,
                    "created_at": r.created_at,
                }
                for r in records
            ]
        }
    
    def get_yearly_carryover_adjustments(self, year: int) -> List[AdjustmentRecord]:
        """获取年终结转调整记录"""
        return self.get_adjustments(
            year=year,
            adjustment_type="year_end_carryover",
            only_active=True
        )
    
    def _row_to_record(self, row: Dict) -> AdjustmentRecord:
        """将数据库行转换为记录对象"""
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


# 全局数据库实例 - v1.5 使用连接池
db = AdjustmentDB(pool_size=5)


if __name__ == "__main__":
    print("测试调整记录数据库 v1.5 (连接池)...")
    
    test_db = AdjustmentDB("test_adjustments_v15.db", pool_size=3)
    
    # 创建测试记录
    print("\n1. 创建调整记录...")
    record = test_db.create_adjustment(
        employee_name="张三",
        year=2025,
        adjust_amount=1.5,
        reason="漏计年假补录",
        created_by="HR小王",
        created_by_open_id="ou_abc123",
        adjustment_type="manual"
    )
    print(f"   创建: ID={record.id}, 操作人={record.created_by}")
    
    # 查询记录
    print("\n2. 查询汇总...")
    summary = test_db.get_adjustment_summary("张三", 2025)
    print(f"   总调整: {summary['total_adjustment']}天")
    
    # 并发测试
    print("\n3. 并发测试...")
    import threading
    
    def create_record(i):
        try:
            r = test_db.create_adjustment(
                employee_name=f"员工{i}",
                year=2025,
                adjust_amount=1.0,
                reason="测试",
                created_by="HR"
            )
            print(f"   线程{i}: 创建成功 ID={r.id}")
        except Exception as e:
            print(f"   线程{i}: 失败 {e}")
    
    threads = [threading.Thread(target=create_record, args=(i,)) for i in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    
    print("\n✅ 数据库测试完成")
    
    # 清理
    import os
    os.remove("test_adjustments_v15.db")
