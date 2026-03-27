"""
数据库工厂 - v1.5 FIX 重构版
统一 SQLite/PostgreSQL 接口
"""
import os
import re
import sqlite3
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


class _SQLiteTransaction:
    """SQLite 事务执行器 - 在事务中保持同一个连接"""
    
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn
    
    def execute(self, sql: str, parameters: tuple = ()) -> int:
        """在事务中执行 SQL"""
        cursor = self.conn.execute(sql, parameters or ())
        return cursor.lastrowid
    
    def fetchone(self, sql: str, parameters: tuple = ()) -> Optional[Dict]:
        """在事务中查询单条"""
        cursor = self.conn.execute(sql, parameters or ())
        row = cursor.fetchone()
        if row:
            columns = [desc[0] for desc in cursor.description]
            return dict(zip(columns, row))
        return None
    
    def fetchall(self, sql: str, parameters: tuple = ()) -> List[Dict]:
        """在事务中查询多条"""
        cursor = self.conn.execute(sql, parameters or ())
        rows = cursor.fetchall()
        if rows:
            columns = [desc[0] for desc in cursor.description]
            return [dict(zip(columns, row)) for row in rows]
        return []


class SQLiteAdapter(DatabaseAdapter):
    """SQLite 适配器（使用连接池）"""
    
    def __init__(self, db_path: str):
        from db_pool import PooledDB
        self.pool = PooledDB(db_path)
        self.db_path = db_path
        logger.info(f"SQLiteAdapter 初始化: {db_path}")
    
    def execute(self, sql: str, parameters: tuple = ()) -> int:
        """执行SQL，返回最后插入的ID或影响行数"""
        return self.pool.execute(sql, parameters)
    
    def fetchone(self, sql: str, parameters: tuple = ()) -> Optional[Dict]:
        """查询单条记录"""
        return self.pool.execute(sql, parameters, fetch=True, fetch_one=True)
    
    def fetchall(self, sql: str, parameters: tuple = ()) -> List[Dict]:
        """查询多条记录"""
        return self.pool.execute(sql, parameters, fetch=True) or []
    
    @contextmanager
    def transaction(self):
        """事务上下文 - 真正的事务支持"""
        conn = None
        try:
            # 直接从底层获取连接（绕过连接池的自动管理）
            conn = sqlite3.connect(
                self.db_path,
                check_same_thread=False,
                timeout=30
            )
            # 开始事务（显式 BEGIN）
            conn.execute("BEGIN")
            
            # 创建事务执行器
            tx = _SQLiteTransaction(conn)
            yield tx
            
            # 提交事务
            conn.commit()
        except Exception as e:
            # 回滚事务
            if conn:
                conn.rollback()
            raise e
        finally:
            # 关闭连接
            if conn:
                conn.close()


class PostgresAdapter(DatabaseAdapter):
    """PostgreSQL 适配器"""
    
    def __init__(self, db_url: str):
        from postgres_db import PostgresDB
        self.db = PostgresDB(db_url)
        logger.info("PostgresAdapter 初始化")
    
    def _convert_sql(self, sql: str) -> str:
        """
        将 SQLite 风格的 ? 占位符转换为 PostgreSQL 的 %s
        使用状态机，只替换真正的占位符，不替换字符串中的 ?
        """
        result = []
        in_string = False
        string_char = None
        i = 0
        while i < len(sql):
            char = sql[i]
            if char in ("'", '"'):
                if not in_string:
                    in_string = True
                    string_char = char
                elif char == string_char:
                    # 检查是否是转义（两个连续的引号）
                    if i + 1 < len(sql) and sql[i + 1] == char:
                        result.append(char)
                        i += 1
                    else:
                        in_string = False
                        string_char = None
                result.append(char)
            elif char == '?' and not in_string:
                result.append('%s')
            else:
                result.append(char)
            i += 1
        return ''.join(result)
    
    def execute(self, sql: str, parameters: tuple = ()) -> int:
        """执行SQL"""
        sql = self._convert_sql(sql)
        result = self.db.execute(sql, list(parameters))
        return result
    
    def fetchone(self, sql: str, parameters: tuple = ()) -> Optional[Dict]:
        """查询单条记录"""
        sql = self._convert_sql(sql)
        return self.db.fetchone(sql, list(parameters))
    
    def fetchall(self, sql: str, parameters: tuple = ()) -> List[Dict]:
        """查询多条记录"""
        sql = self._convert_sql(sql)
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
