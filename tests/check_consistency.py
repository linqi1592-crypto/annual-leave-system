"""
前后端逻辑一致性检查 + 数据库结构验证
检查工程师: Ada
日期: 2026-03-26
"""

import ast
import re
from pathlib import Path
from typing import List, Dict, Set, Tuple


class ConsistencyChecker:
    """一致性检查器"""
    
    def __init__(self, backend_dir: str, frontend_dir: str):
        self.backend_dir = Path(backend_dir)
        self.frontend_dir = Path(frontend_dir)
        self.issues = []
        self.warnings = []
    
    def check_api_routes(self) -> Tuple[Set[str], Set[str]]:
        """检查前后端 API 路由一致性"""
        print("=" * 60)
        print("1. API 路由一致性检查")
        print("=" * 60)
        
        # 后端路由
        backend_routes = set()
        main_file = self.backend_dir / "main.py"
        
        if main_file.exists():
            content = main_file.read_text()
            # 提取 @app.get/post/delete 装饰器
            routes = re.findall(r'@app\.(get|post|delete|put)\(["\']([^"\']+)', content, re.IGNORECASE)
            for method, path in routes:
                backend_routes.add(f"{method.upper()} {path}")
        
        # 前端 API 调用
        frontend_routes = set()
        for js_file in self.frontend_dir.rglob("*.js"):
            content = js_file.read_text()
            # 提取 API 调用
            api_calls = re.findall(r'fetch\(`?\$\{API_BASE\}([^`\s\?]+)', content)
            api_calls += re.findall(r'api\.(get|post|delete)\(["\']([^"\']+)', content)
            for match in api_calls:
                if isinstance(match, tuple):
                    method, path = match
                    frontend_routes.add(f"{method.upper()} {path}")
                else:
                    frontend_routes.add(f"GET {match}")
        
        print(f"\n后端路由 ({len(backend_routes)} 个):")
        for route in sorted(backend_routes):
            print(f"  {route}")
        
        print(f"\n前端调用 ({len(frontend_routes)} 个):")
        for route in sorted(frontend_routes):
            print(f"  {route}")
        
        # 检查不一致
        only_backend = backend_routes - frontend_routes
        only_frontend = frontend_routes - backend_routes
        
        if only_backend:
            self.warnings.append(f"后端有但前端未调用的 API: {only_backend}")
        
        if only_frontend:
            self.issues.append(f"前端调用但后端不存在的 API: {only_frontend}")
        
        return backend_routes, frontend_routes
    
    def check_data_models(self):
        """检查数据模型一致性"""
        print("\n" + "=" * 60)
        print("2. 数据模型一致性检查")
        print("=" * 60)
        
        # 后端 Pydantic 模型
        backend_models = {}
        for py_file in self.backend_dir.glob("*.py"):
            content = py_file.read_text()
            # 查找类定义
            classes = re.findall(r'class (\w+)\([^\)]*\):', content)
            for cls in classes:
                if 'Model' in cls or 'Base' in cls:
                    backend_models[cls] = py_file.name
        
        print(f"\n后端模型 ({len(backend_models)} 个):")
        for model, file in sorted(backend_models.items()):
            print(f"  {model} ({file})")
        
        # 检查关键模型
        required_models = ['AdjustmentCreate', 'AdjustmentResponse', 'User']
        for model in required_models:
            if model not in backend_models:
                self.issues.append(f"缺少关键模型: {model}")
    
    def check_database_schema(self):
        """检查数据库表结构"""
        print("\n" + "=" * 60)
        print("3. 数据库表结构检查")
        print("=" * 60)
        
        tables = {}
        
        # SQLite 表
        adj_file = self.backend_dir / "adjustment_db.py"
        if adj_file.exists():
            content = adj_file.read_text()
            # 提取 CREATE TABLE
            create_statements = re.findall(
                r'CREATE TABLE IF NOT EXISTS (\w+) \((.*?)\)',
                content,
                re.DOTALL
            )
            for table_name, columns in create_statements:
                cols = re.findall(r'(\w+)\s+(\w+)', columns)
                tables[table_name] = {
                    'type': 'sqlite',
                    'columns': [c[0] for c in cols],
                    'file': 'adjustment_db.py'
                }
        
        # PostgreSQL 表 (SQLAlchemy)
        pg_file = self.backend_dir / "postgres_db.py"
        if pg_file.exists():
            content = pg_file.read_text()
            models = re.findall(r'class (\w+)\(Base\):', content)
            for model in models:
                tables[model] = {
                    'type': 'postgresql',
                    'model': model,
                    'file': 'postgres_db.py'
                }
        
        print(f"\n发现 {len(tables)} 个表/模型:")
        for name, info in tables.items():
            print(f"  {name} ({info['type']}) - {info.get('file', '')}")
        
        # 检查必需表
        required_tables = ['adjustments', 'year_end_settlements', 'year_end_settlement_details']
        for table in required_tables:
            found = False
            for t in tables.keys():
                if table.lower() in t.lower():
                    found = True
                    break
            if not found:
                self.warnings.append(f"可能缺少表: {table}")
    
    def check_field_consistency(self):
        """检查字段命名一致性"""
        print("\n" + "=" * 60)
        print("4. 字段命名一致性检查")
        print("=" * 60)
        
        # 调整后端的字段
        adj_fields = []
        adj_file = self.backend_dir / "adjustment_db.py"
        if adj_file.exists():
            content = adj_file.read_text()
            fields = re.findall(r'employee_name|adjust_amount|created_by|adjustment_type', content)
            adj_fields = list(set(fields))
        
        # 前端使用的字段
        frontend_fields = []
        for js_file in self.frontend_dir.rglob("*.js"):
            content = js_file.read_text()
            fields = re.findall(r'employee_name|adjust_amount|created_by|adjustment_type', content)
            frontend_fields.extend(fields)
        frontend_fields = list(set(frontend_fields))
        
        print(f"\n后端字段: {sorted(adj_fields)}")
        print(f"前端字段: {sorted(frontend_fields)}")
        
        # 检查 snake_case vs camelCase
        backend_snake = [f for f in adj_fields if '_' in f]
        frontend_camel = [f for f in frontend_fields if '_' not in f and f.islower()]
        
        if backend_snake and frontend_camel:
            self.warnings.append("后端使用 snake_case，前端使用 camelCase，建议统一")
    
    def generate_report(self):
        """生成检查报告"""
        print("\n" + "=" * 60)
        print("5. 检查报告汇总")
        print("=" * 60)
        
        if self.issues:
            print(f"\n❌ 发现 {len(self.issues)} 个问题:")
            for issue in self.issues:
                print(f"  - {issue}")
        else:
            print("\n✅ 未发现严重问题")
        
        if self.warnings:
            print(f"\n⚠️  发现 {len(self.warnings)} 个警告:")
            for warning in self.warnings:
                print(f"  - {warning}")
        else:
            print("\n✅ 无警告")
        
        return len(self.issues) == 0


# 运行检查
if __name__ == "__main__":
    checker = ConsistencyChecker(
        backend_dir="/Users/mac/.openclaw/workspace/年假查询系统/backend",
        frontend_dir="/Users/mac/.openclaw/workspace/年假查询系统/frontend"
    )
    
    checker.check_api_routes()
    checker.check_data_models()
    checker.check_database_schema()
    checker.check_field_consistency()
    
    success = checker.generate_report()
    
    exit(0 if success else 1)
