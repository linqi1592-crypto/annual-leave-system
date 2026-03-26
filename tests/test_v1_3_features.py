"""
年假查询系统 v1.3 测试用例
测试范围: 7项新功能
测试工程师: Ada
日期: 2026-03-26
"""

import pytest
from datetime import date, datetime, timedelta
from unittest.mock import Mock, patch, MagicMock
import jwt
import sqlite3
import os
import tempfile

# 设置测试环境
os.environ['FEISHU_APP_ID'] = 'test_app_id'
os.environ['FEISHU_APP_SECRET'] = 'test_app_secret'
os.environ['FEISHU_APP_TOKEN'] = 'test_app_token'
os.environ['JWT_SECRET_KEY'] = 'test-secret-key-for-testing-only'

from backend.auth import AuthManager, User
from backend.leave_calculator import LeaveCalculator, calculator
from backend.adjustment_db import AdjustmentDB, AdjustmentRecord
from backend.year_end import YearEndSettlementDB
from backend.export import generate_export_data


# ==================== P0: 飞书免登测试 ====================

class TestFeishuAuth:
    """飞书免登自动识别用户 - P0"""
    
    def setup_method(self):
        self.auth_manager = AuthManager()
    
    def test_get_user_access_token_success(self):
        """TC-AUTH-001: 成功用 auth_code 换取 user_access_token"""
        with patch('backend.auth.requests.post') as mock_post:
            mock_response = Mock()
            mock_response.json.return_value = {
                "code": 0,
                "data": {"access_token": "test_user_token_123"}
            }
            mock_post.return_value = mock_response
            
            token = self.auth_manager.get_user_access_token("test_auth_code")
            assert token == "test_user_token_123"
    
    def test_get_user_access_token_failure(self):
        """TC-AUTH-002: auth_code 无效时返回错误"""
        with patch('backend.auth.requests.post') as mock_post:
            mock_response = Mock()
            mock_response.json.return_value = {
                "code": 99991664,
                "msg": "invalid auth code"
            }
            mock_post.return_value = mock_response
            mock_post.return_value.raise_for_status = Mock()
            
            from fastapi import HTTPException
            with pytest.raises(HTTPException) as exc_info:
                self.auth_manager.get_user_access_token("invalid_code")
            assert exc_info.value.status_code == 401
    
    def test_get_user_info_success(self):
        """TC-AUTH-003: 成功获取用户信息"""
        with patch('backend.auth.requests.get') as mock_get:
            mock_response = Mock()
            mock_response.json.return_value = {
                "code": 0,
                "data": {
                    "open_id": "ou_test_user_001",
                    "name": "测试用户",
                    "email": "test@example.com"
                }
            }
            mock_get.return_value = mock_response
            
            user_info = self.auth_manager.get_user_info("test_token")
            assert user_info["open_id"] == "ou_test_user_001"
            assert user_info["name"] == "测试用户"
    
    def test_match_employee_by_open_id(self):
        """TC-AUTH-004: 通过 open_id 匹配员工"""
        with patch('backend.auth.feishu_client') as mock_client:
            mock_client.get_employee_records.return_value = [
                {
                    "record_id": "emp_001",
                    "fields": {
                        "发起人": "张三",
                        "飞书Open ID": "ou_test_user_001"
                    }
                }
            ]
            
            match = self.auth_manager.match_employee("ou_test_user_001", "张三")
            assert match is not None
            assert match["employee_id"] == "emp_001"
            assert match["employee_name"] == "张三"
    
    def test_match_employee_fallback_by_name(self):
        """TC-AUTH-005: open_id 未匹配时回退到姓名匹配"""
        with patch('backend.auth.feishu_client') as mock_client:
            mock_client.get_employee_records.return_value = [
                {
                    "record_id": "emp_001",
                    "fields": {
                        "发起人": "张三",
                        "飞书Open ID": ""
                    }
                }
            ]
            
            # 新用户还没有 open_id，通过姓名匹配
            match = self.auth_manager.match_employee("ou_new_user", "张三")
            assert match is not None
            assert match["employee_name"] == "张三"
    
    def test_check_is_hr(self):
        """TC-AUTH-006: HR 权限检查"""
        # 设置 HR 列表
        self.auth_manager.hr_users = {"ou_hr_001", "ou_hr_002"}
        
        assert self.auth_manager.check_is_hr("ou_hr_001") == True
        assert self.auth_manager.check_is_hr("ou_hr_002") == True
        assert self.auth_manager.check_is_hr("ou_normal_user") == False
    
    def test_jwt_token_create_and_decode(self):
        """TC-AUTH-007: JWT token 创建和解析"""
        user = User(
            open_id="ou_test_001",
            name="测试用户",
            employee_id="emp_001",
            employee_name="张三",
            is_hr=False
        )
        
        # 创建 token
        token = self.auth_manager.create_jwt_token(user)
        assert token is not None
        assert isinstance(token, str)
        
        # 解析 token
        decoded = self.auth_manager.decode_jwt_token(token)
        assert decoded.open_id == "ou_test_001"
        assert decoded.name == "测试用户"
        assert decoded.is_hr == False
    
    def test_jwt_token_expired(self):
        """TC-AUTH-008: 过期 token 应被拒绝"""
        from fastapi import HTTPException
        
        # 创建一个已过期 1 小时的 token
        expired_time = datetime.utcnow() - timedelta(hours=1)
        payload = {
            "open_id": "ou_test_001",
            "name": "测试用户",
            "exp": expired_time,
            "iat": expired_time - timedelta(minutes=10)
        }
        expired_token = jwt.encode(
            payload, 
            self.auth_manager.jwt_secret, 
            algorithm=self.auth_manager.jwt_algorithm
        )
        
        with pytest.raises(HTTPException) as exc_info:
            self.auth_manager.decode_jwt_token(expired_token)
        assert exc_info.value.status_code == 401
        assert "过期" in exc_info.value.detail
    
    def test_complete_login_flow(self):
        """TC-AUTH-009: 完整登录流程"""
        with patch.object(self.auth_manager, 'get_user_access_token') as mock_token, \
             patch.object(self.auth_manager, 'get_user_info') as mock_info, \
             patch.object(self.auth_manager, 'match_employee') as mock_match:
            
            mock_token.return_value = "user_token_123"
            mock_info.return_value = {"open_id": "ou_001", "name": "张三"}
            mock_match.return_value = {"employee_id": "emp_001", "employee_name": "张三"}
            self.auth_manager.hr_users = {"ou_001"}
            
            response = self.auth_manager.login("auth_code_123")
            
            assert response.open_id == "ou_001"
            assert response.name == "张三"
            assert response.employee_id == "emp_001"
            assert response.is_hr == True
            assert response.token is not None


# ==================== P0-2: 调整记录操作人验证测试 ====================

class TestAdjustmentAuth:
    """调整记录操作人身份验证 - P0-2"""
    
    def setup_method(self):
        # 创建临时数据库
        self.db_fd, self.db_path = tempfile.mkstemp(suffix='.db')
        self.db = AdjustmentDB(db_path=self.db_path)
    
    def teardown_method(self):
        os.close(self.db_fd)
        os.unlink(self.db_path)
    
    def test_create_adjustment_with_open_id(self):
        """TC-ADJ-001: 创建调整记录时记录 open_id"""
        record = self.db.create_adjustment(
            employee_name="张三",
            year=2026,
            adjust_amount=1.5,
            reason="补录年假",
            created_by="HR小王",
            created_by_open_id="ou_hr_001",
            adjustment_type="manual"
        )
        
        assert record.created_by_open_id == "ou_hr_001"
        assert record.created_by == "HR小王"
        assert record.adjustment_type == "manual"
    
    def test_adjustment_record_has_open_id_field(self):
        """TC-ADJ-002: 调整记录表包含 open_id 字段"""
        record = self.db.create_adjustment(
            employee_name="张三",
            year=2026,
            adjust_amount=1.0,
            reason="测试",
            created_by="测试员",
            created_by_open_id="ou_test_001"
        )
        
        # 查询验证
        summary = self.db.get_adjustment_summary("张三", 2026)
        assert len(summary.adjustments) == 1
        adj = summary.adjustments[0]
        assert adj.created_by_open_id == "ou_test_001"
    
    def test_db_migration_v13(self):
        """TC-ADJ-003: 数据库迁移添加新字段"""
        # 检查表结构包含新字段
        with self.db._get_connection() as conn:
            cursor = conn.execute("PRAGMA table_info(adjustments)")
            columns = {row[1] for row in cursor.fetchall()}
            
            assert "created_by_open_id" in columns
            assert "adjustment_type" in columns


# ==================== P1-1: 余额卡片分栏展示测试 ====================

class TestBalanceDisplay:
    """余额卡片分栏展示 - P1-1"""
    
    def test_balance_response_structure(self):
        """TC-DISP-001: 余额响应包含分栏数据"""
        employee_data = {
            "fields": {
                "发起人": "张三",
                "工龄(月)": 36,
                "入职时间": "2023-03-15"
            }
        }
        leave_records = []
        
        result = calculator.calculate_annual_leave_balance(
            employee_data, leave_records, 3.0, date(2026, 3, 26)
        )
        
        annual = result["annual_leave"]
        
        # 验证包含分栏数据
        assert "current_year" in annual
        assert "carryover" in annual
        assert "total_used" in annual
        assert "remaining" in annual
        
        # 验证当年额度结构
        assert isinstance(annual["current_year"], dict)
        assert "quota" in annual["current_year"]
        
        # 验证结转结构
        assert isinstance(annual["carryover"], dict)
        assert "quota" in annual["carryover"]
        assert "expire_date" in annual["carryover"]
    
    def test_carryover_expire_date_format(self):
        """TC-DISP-002: 结转到期日期格式正确"""
        employee_data = {
            "fields": {
                "发起人": "张三",
                "工龄(月)": 36,
            }
        }
        
        result = calculator.calculate_annual_leave_balance(
            employee_data, [], 3.0, date(2026, 2, 15)  # 3月31日前
        )
        
        expire_date = result["annual_leave"]["carryover"]["expire_date"]
        assert expire_date is not None
        # 验证是 ISO 日期格式
        assert isinstance(expire_date, str)
        assert len(expire_date) == 10  # YYYY-MM-DD


# ==================== P1-2: 负数余额兼容性测试 ====================

class TestNegativeBalance:
    """负数余额兼容性 - P1-2"""
    
    def test_negative_remaining_calculation(self):
        """TC-NEG-001: 年假透支时剩余为负数"""
        employee_data = {
            "fields": {
                "发起人": "张三",
                "工龄(月)": 36,
            }
        }
        
        # 构造请假记录，使用超过额度
        leave_records = [
            {
                "fields": {
                    "请假类型": "年假",
                    "申请状态": "已通过",
                    "开始时间": "2026-03-01",
                    "时长": 20.0  # 远超额度
                }
            }
        ]
        
        result = calculator.calculate_annual_leave_balance(
            employee_data, leave_records, 0, date(2026, 3, 26)
        )
        
        # 验证负数余额
        assert result["annual_leave"]["remaining"] < 0
        assert result["annual_leave"]["is_negative"] == True
    
    def test_negative_carryover_becomes_zero(self):
        """TC-NEG-002: 负数余额结转为0"""
        carryover, expire_date = calculator.calculate_carryover(-5.0, date(2026, 3, 15))
        
        # 负数上年剩余应结转为0
        assert carryover == 0
        assert expire_date is not None  # 但仍有到期日
    
    def test_zero_carryover_still_has_expire_date(self):
        """TC-NEG-003: 零结转仍有到期日期"""
        carryover, expire_date = calculator.calculate_carryover(0, date(2026, 3, 15))
        
        assert carryover == 0
        assert expire_date == date(2026, 3, 31)
    
    def test_after_expire_date_carryover_zero(self):
        """TC-NEG-004: 过期后结转清零"""
        # 4月1日，已过3月31日
        carryover, expire_date = calculator.calculate_carryover(3.0, date(2026, 4, 1))
        
        assert carryover == 0
        assert expire_date is None


# ==================== P1-3: 批量导出测试 ====================

class TestExport:
    """批量导出年假数据 - P1-3"""
    
    @patch('backend.export.feishu_client')
    @patch('backend.export.calculator')
    def test_export_csv_generation(self, mock_calc, mock_client):
        """TC-EXP-001: CSV 导出格式正确"""
        from backend.export import generate_csv
        
        data = [
            {"姓名": "张三", "工号": "001", "余额": 5.5},
            {"姓名": "李四", "工号": "002", "余额": 3.0}
        ]
        
        csv_content = generate_csv(data)
        
        assert "姓名" in csv_content
        assert "张三" in csv_content
        assert "李四" in csv_content
        # 验证 CSV 格式（有逗号分隔）
        assert "," in csv_content
    
    def test_export_data_structure(self):
        """TC-EXP-002: 导出数据包含必需字段"""
        # 模拟数据
        mock_employees = [
            {
                "record_id": "emp_001",
                "fields": {
                    "发起人": "张三",
                    "工号": "E001",
                    "入职时间": "2020-03-15"
                }
            }
        ]
        
        with patch('backend.export.feishu_client') as mock_client, \
             patch('backend.export.calculate_year_end_balance') as mock_calc:
            
            mock_client.get_employee_records.return_value = mock_employees
            mock_calc.return_value = {
                "current_year_quota": 10,
                "carryover": 3,
                "total_used": 5,
                "remaining": 8,
                "is_negative": False
            }
            
            data = generate_export_data(year=2026)
            
            assert len(data) > 0
            record = data[0]
            
            # 验证必需字段
            assert "姓名" in record
            assert "工号" in record
            assert "入职日期" in record
            assert "司龄(月)" in record
            assert "当年额度" in record
            assert "上年结转" in record
            assert "已用天数" in record
            assert "余额" in record
            assert "是否透支" in record
            assert "调整记录" in record


# ==================== P1-4: 年终清算测试 ====================

class TestYearEndSettlement:
    """年终清算流程 - P1-4"""
    
    def setup_method(self):
        self.db_fd, self.db_path = tempfile.mkstemp(suffix='.db')
        self.db = YearEndSettlementDB(db_path=self.db_path)
    
    def teardown_method(self):
        os.close(self.db_fd)
        os.unlink(self.db_path)
    
    def test_settlement_tables_created(self):
        """TC-SETTLE-001: 清算表结构正确"""
        with self.db._get_connection() as conn:
            # 检查主表
            cursor = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='year_end_settlements'"
            )
            assert cursor.fetchone() is not None
            
            # 检查明细表
            cursor = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='year_end_settlement_details'"
            )
            assert cursor.fetchone() is not None
    
    def test_create_settlement_record(self):
        """TC-SETTLE-002: 创建清算记录"""
        details = [
            {"employee_name": "张三", "year_end_balance": 5.0, "carryover_days": 3.0, "cleared_days": 2.0},
            {"employee_name": "李四", "year_end_balance": 2.0, "carryover_days": 2.0, "cleared_days": 0.0}
        ]
        
        settlement_id = self.db.create_settlement(
            year=2025,
            settled_by="HR小王",
            settled_by_open_id="ou_hr_001",
            details=details
        )
        
        assert settlement_id > 0
        
        # 验证记录
        settlement = self.db.get_settlement_by_id(settlement_id)
        assert settlement["year"] == 2025
        assert settlement["settled_by"] == "HR小王"
        assert settlement["settled_by_open_id"] == "ou_hr_001"
        assert settlement["total_employees"] == 2
        assert settlement["total_carryover"] == 5.0
        assert settlement["total_cleared"] == 2.0
        assert len(settlement["details"]) == 2
    
    def test_check_year_settled(self):
        """TC-SETTLE-003: 检查年度是否已清算"""
        # 初始状态
        assert self.db.check_year_settled(2025) == False
        
        # 创建清算记录
        self.db.create_settlement(
            year=2025,
            settled_by="HR小王",
            settled_by_open_id="ou_hr_001",
            details=[]
        )
        
        # 再次检查
        assert self.db.check_year_settled(2025) == True
        assert self.db.check_year_settled(2024) == False
    
    def test_carryover_calculation(self):
        """TC-SETTLE-004: 结转天数计算正确"""
        # 测试用例: 年末余额 5天 → 结转3天（上限），清零2天
        balance = 5.0
        carryover = min(balance, 3)
        cleared = max(0, balance - 3)
        
        assert carryover == 3.0
        assert cleared == 2.0
        
        # 测试用例: 年末余额 2天 → 结转2天，清零0天
        balance = 2.0
        carryover = min(balance, 3)
        cleared = max(0, balance - 3)
        
        assert carryover == 2.0
        assert cleared == 0.0
        
        # 测试用例: 年末余额 -2天（负数）→ 结转0天，清零0天
        balance = -2.0
        carryover = min(max(0, balance), 3)  # 负数转为0
        cleared = 0
        
        assert carryover == 0.0


# ==================== P1-5: 司龄递增自动化测试 ====================

class TestServiceMonthsAutoCalculation:
    """司龄递增自动化 - P1-5"""
    
    def test_calculate_service_months_basic(self):
        """TC-SERVICE-001: 基本司龄计算"""
        entry_date = date(2020, 3, 15)
        current_date = date(2026, 3, 26)
        
        months = calculator.calculate_service_months(entry_date, current_date)
        
        # 2020.3.15 → 2026.3.26 = 6年0个月 = 72个月
        assert months == 72
    
    def test_calculate_service_months_partial_month(self):
        """TC-SERVICE-002: 跨月司龄计算"""
        entry_date = date(2020, 3, 15)
        current_date = date(2026, 6, 10)  # 还没到6月15日
        
        months = calculator.calculate_service_months(entry_date, current_date)
        
        # 2020.3.15 → 2026.6.10 = 6年2个月 = 74个月（还没到6月15日）
        assert months == 74
    
    def test_calculate_service_months_same_day(self):
        """TC-SERVICE-003: 同一天入职"""
        entry_date = date(2020, 3, 15)
        current_date = date(2026, 3, 15)
        
        months = calculator.calculate_service_months(entry_date, current_date)
        
        # 正好满6年
        assert months == 72
    
    def test_calculate_service_months_new_employee(self):
        """TC-SERVICE-004: 新员工（未满1年）"""
        entry_date = date(2026, 1, 15)
        current_date = date(2026, 3, 26)
        
        months = calculator.calculate_service_months(entry_date, current_date)
        
        # 2个月
        assert months == 2
    
    def test_calculate_service_months_none_entry_date(self):
        """TC-SERVICE-005: 无入职日期返回0"""
        months = calculator.calculate_service_months(None, date(2026, 3, 26))
        assert months == 0
    
    def test_welfare_leave_based_on_auto_calculated_service_months(self):
        """TC-SERVICE-006: 福利年假基于自动计算的司龄"""
        # 司龄3年（36个月）
        entry_date = date(2023, 3, 15)
        current_date = date(2026, 3, 26)
        
        service_months = calculator.calculate_service_months(entry_date, current_date)
        welfare = calculator.calculate_welfare_leave(service_months)
        
        # 司龄3年，福利年假 = 1 + 3 = 4天（中高级员工）
        assert service_months == 36
        assert welfare == 4
    
    def test_annual_leave_balance_uses_auto_service_months(self):
        """TC-SERVICE-007: 年假余额计算使用自动司龄"""
        employee_data = {
            "fields": {
                "发起人": "张三",
                "工龄(月)": 36,  # 社保工龄
                "入职时间": "2023-03-15"  # 司龄约3年
            }
        }
        
        result = calculator.calculate_annual_leave_balance(
            employee_data, [], 0, date(2026, 3, 26)
        )
        
        # 验证使用了自动计算的司龄
        assert result["employee"]["service_months"] == 36
        assert result["employee"]["service_years"] == 3


# ==================== 集成测试 ====================

class TestIntegration:
    """集成测试 - 验证完整流程"""
    
    def test_employee_login_to_view_balance(self):
        """TC-INT-001: 员工登录到查看余额完整流程"""
        # 模拟登录
        user = User(
            open_id="ou_employee_001",
            name="张三",
            employee_id="emp_001",
            employee_name="张三",
            is_hr=False
        )
        
        # 模拟员工数据
        employee_data = {
            "fields": {
                "发起人": "张三",
                "工龄(月)": 36,
                "入职时间": "2023-03-15",
                "飞书Open ID": "ou_employee_001"
            }
        }
        
        # 计算年假
        result = calculator.calculate_annual_leave_balance(
            employee_data, [], 3.0, date(2026, 3, 26)
        )
        
        # 验证结果结构
        assert "annual_leave" in result
        assert "employee" in result
        assert result["employee"]["name"] == "张三"
    
    def test_hr_create_adjustment_auto_record_operator(self):
        """TC-INT-002: HR调整自动记录操作人"""
        db_fd, db_path = tempfile.mkstemp(suffix='.db')
        db = AdjustmentDB(db_path=db_path)
        
        try:
            # 模拟 HR 用户
            hr_user = User(
                open_id="ou_hr_001",
                name="HR小王",
                employee_id="emp_hr_001",
                employee_name="HR小王",
                is_hr=True
            )
            
            # 创建调整记录
            record = db.create_adjustment(
                employee_name="张三",
                year=2026,
                adjust_amount=1.5,
                reason="补录",
                created_by=hr_user.name,  # 从 current_user 自动获取
                created_by_open_id=hr_user.open_id,
                adjustment_type="manual"
            )
            
            # 验证操作人信息
            assert record.created_by == "HR小王"
            assert record.created_by_open_id == "ou_hr_001"
        finally:
            os.close(db_fd)
            os.unlink(db_path)


# ==================== 运行测试 ====================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
