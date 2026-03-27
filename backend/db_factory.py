"""
数据库工厂 - v1.5 FIX 重构版
统一 SQLite/PostgreSQL 接口
"""
import os
from typing import Optional, Any, List, Dict
from contextlib import contextmanager
from config import DB_CONFIG, logger

DB_TYPE = os.getenv("DB_TYPE", "sqlite")


class DatabaseAdapter:
    """数据库适配器 - 统一接口"""
    
    def execute(self, sql: str, parameters: tuple = ()) -> Any:
        """执行SQL，返回影响行数或自增ID"""
        raise NotImplementedError
    
    def fetchone(self, sql: str, parameters: tuple = ()) -> Optional[Dict]:
        """查询单条记录"""
        raise NotImplementedError
    
    def fetchall(self, sql: str, parameters: tuple = ()) -> List[Dict]:
        """查询多条记录"""
        raise NotImplementedError
    
    @contextmanager
    def transaction(self):
        """事务上下文管理器"""
        raise NotImplementedError


class SQLiteAdapter(DatabaseAdapter):
    """SQLite 适配器（使用连接池）"""
    
    def __init__(self, db_path: str):
        from db_pool import PooledDB
        self.pool = PooledDB(db_path)
        logger.info(f"SQLiteAdapter 初始化: {db_path}")
    
    def execute(self, sql: str, parameters: tuple = ()) -> int:
        """执行SQL，返回最后插入的ID或影响行数"""
        # PooledDB.execute 返回最后插入的ID
        return self.pool.execute(sql, parameters)
    
    def fetchone(self, sql: str, parameters: tuple = ()) -> Optional[Dict]:
        """查询单条记录"""
        return self.pool.execute(sql, parameters, fetch=True, fetch_one=True)
    
    def fetchall(self, sql: str, parameters: tuple = ()) -> List[Dict]:
        """查询多条记录"""
        return self.pool.execute(sql, parameters, fetch=True) or []
    
    @contextmanager
    def transaction(self):
        """事务上下文"""
        # PooledDB 的连接池已经处理了事务
        yield self


class PostgresAdapter(DatabaseAdapter):
    """PostgreSQL 适配器"""
    
    def __init__(self, db_url: str):
        from postgres_db import PostgresDB
        self.db = PostgresDB(db_url)
        logger.info("PostgresAdapter 初始化")
    
    def execute(self, sql: str, parameters: tuple = ()) -> int:
        """执行SQL"""
        # 转换 ? 占位符为 %s
        sql = sql.replace("?", "%s")
        result = self.db.execute(sql, list(parameters))
        return result
    
    def fetchone(self, sql: str, parameters: tuple = ()) -> Optional[Dict]:
        """查询单条记录"""
        sql = sql.replace("?", "%s")
        return self.db.fetchone(sql, list(parameters))
    
    def fetchall(self, sql: str, parameters: tuple = ()) -> List[Dict]:
        """查询多条记录"""
        sql = sql.replace("?", "%s")
        return self.db.fetchall(sql, list(parameters)) or []
    
    @contextmanager
    def transaction(self):
        """事务上下文"""
        with self.db.transaction():
            yield self


def create_database() -> DatabaseAdapter:
    """创建数据库适配器（根据 DB_TYPE 自动选择）"""
    global DB_TYPE
    
    if DB_TYPE == "postgres":
        db_url = os.getenv("DATABASE_URL")
        if db_url:
            try:
                return PostgresAdapter(db_url)
            except Exception as e:
                logger.error(f"PostgreSQL 初始化失败: {e}，回退到 SQLite")
                DB_TYPE = "sqlite"
        else:
            logger.warning("DB_TYPE=postgres 但 DATABASE_URL 未配置，使用 SQLite")
            DB_TYPE = "sqlite"
    
    # 默认使用 SQLite
    return SQLiteAdapter(DB_CONFIG["path"])


# 全局数据库实例（延迟初始化）
_db_instance: Optional[DatabaseAdapter] = None

def get_db() -> DatabaseAdapter:
    """获取数据库实例（单例）"""
    global _db_instance
    if _db_instance is None:
        _db_instance = create_database()
    return _db_instance


def reset_db():
    """重置数据库实例（用于测试）"""
    global _db_instance
    _db_instance = None
