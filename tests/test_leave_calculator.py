"""
年假计算引擎测试脚本
测试目标：leave_calculator.py 中的核心计算函数
"""

import sys
import pytest
from datetime import date, datetime
from pathlib import Path

# 添加 backend 目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

# 使用测试配置
sys.modules['config'] = __import__('test_config', fromlist=[''])

from leave_calculator import LeaveCalculator


class TestLegalLeaveCalculation:
    """法定年假计算测试 - 按社保工龄"""
    
    @pytest.fixture
    def calculator(self):
        return LeaveCalculator()
    
    # ===== 边界值测试：12个月边界 =====
    def test_legal_leave_11_months(self, calculator):
        """工龄11个月 - 应得0天"""
        assert calculator.calculate_legal_leave(11) == 0
    
    def test_legal_leave_12_months(self, calculator):
        """工龄12个月 - 应得5天（边界）"""
        assert calculator.calculate_legal_leave(12) == 5
    
    def test_legal_leave_13_months(self, calculator):
        """工龄13个月 - 应得5天"""
        assert calculator.calculate_legal_leave(13) == 5
    
    # ===== 边界值测试：180个月边界 =====
    def test_legal_leave_179_months(self, calculator):
        """工龄179个月 - 应得5天"""
        assert calculator.calculate_legal_leave(179) == 5
    
    def test_legal_leave_180_months(self, calculator):
        """工龄180个月 - 应得10天（边界）"""
        assert calculator.calculate_legal_leave(180) == 10
    
    def test_legal_leave_181_months(self, calculator):
        """工龄181个月 - 应得10天"""
        assert calculator.calculate_legal_leave(181) == 10
    
    # ===== 边界值测试：240个月边界 =====
    def test_legal_leave_239_months(self, calculator):
        """工龄239个月 - 应得10天"""
        assert calculator.calculate_legal_leave(239) == 10
    
    def test_legal_leave_240_months(self, calculator):
        """工龄240个月 - 应得15天（边界）"""
        assert calculator.calculate_legal_leave(240) == 15
    
    def test_legal_leave_241_months(self, calculator):
        """工龄241个月 - 应得15天"""
        assert calculator.calculate_legal_leave(241) == 15
    
    # ===== 常规场景测试 =====
    def test_legal_leave_0_months(self, calculator):
        """工龄0个月 - 应得0天"""
        assert calculator.calculate_legal_leave(0) == 0
    
    def test_legal_leave_36_months(self, calculator):
        """工龄36个月（3年）- 应得5天"""
        assert calculator.calculate_legal_leave(36) == 5
    
    def test_legal_leave_300_months(self, calculator):
        """工龄300个月（25年）- 应得15天"""
        assert calculator.calculate_legal_leave(300) == 15


class TestWelfareLeaveCalculation:
    """福利年假计算测试 - 按司龄"""
    
    @pytest.fixture
    def calculator(self):
        return LeaveCalculator()
    
    # ===== 边界值测试：12个月边界 =====
    def test_welfare_leave_11_months(self, calculator):
        """司龄11个月 - 新员工福利6天"""
        assert calculator.calculate_welfare_leave(11) == 6
    
    def test_welfare_leave_12_months(self, calculator):
        """司龄12个月 - 福利2天（1年+1基础）"""
        assert calculator.calculate_welfare_leave(12) == 2
    
    def test_welfare_leave_13_months(self, calculator):
        """司龄13个月 - 福利2天"""
        assert calculator.calculate_welfare_leave(13) == 2
    
    # ===== 边界值测试：180个月边界 =====
    def test_welfare_leave_179_months(self, calculator):
        """司龄179个月（14年11月）- 福利15天（14+1）"""
        assert calculator.calculate_welfare_leave(179) == 15
    
    def test_welfare_leave_180_months(self, calculator):
        """司龄180个月（15年）- 福利15天"""
        assert calculator.calculate_welfare_leave(180) == 15
    
    def test_welfare_leave_181_months(self, calculator):
        """司龄181个月（15年1月）- 福利15天"""
        assert calculator.calculate_welfare_leave(181) == 15
    
    # ===== 常规场景测试 =====
    def test_welfare_leave_0_months(self, calculator):
        """司龄0个月 - 新员工福利6天"""
        assert calculator.calculate_welfare_leave(0) == 6
    
    def test_welfare_leave_6_months(self, calculator):
        """司龄6个月 - 新员工福利6天"""
        assert calculator.calculate_welfare_leave(6) == 6
    
    def test_welfare_leave_24_months(self, calculator):
        """司龄24个月（2年）- 福利3天（2+1）"""
        assert calculator.calculate_welfare_leave(24) == 3
    
    def test_welfare_leave_240_months(self, calculator):
        """司龄240个月（20年）- 福利20天"""
        assert calculator.calculate_welfare_leave(240) == 20


class TestCapCalculation:
    """封顶逻辑测试"""
    
    @pytest.fixture
    def calculator(self):
        return LeaveCalculator()
    
    # ===== 一般员工封顶（12天）=====
    def test_cap_normal_employee_12_total(self, calculator):
        """一般员工：法定5+福利7=12，不封顶"""
        assert calculator.apply_cap(12, 36) == 12
    
    def test_cap_normal_employee_exceed_12(self, calculator):
        """一般员工：法定5+福利8=13，应封顶为12"""
        assert calculator.apply_cap(13, 36) == 12
    
    def test_cap_normal_employee_at_boundary(self, calculator):
        """一般员工在工龄239月边界：法定10+福利15=25，应封顶为12"""
        assert calculator.apply_cap(25, 239) == 12
    
    # ===== 老员工封顶（15天）=====
    def test_cap_senior_employee_15_total(self, calculator):
        """老员工：法定15+福利0=15，不封顶"""
        assert calculator.apply_cap(15, 250) == 15
    
    def test_cap_senior_employee_exceed_15(self, calculator):
        """老员工：法定15+福利25=40，应封顶为15"""
        assert calculator.apply_cap(40, 250) == 15
    
    def test_cap_senior_employee_at_boundary_240(self, calculator):
        """老员工在工龄240月边界：法定15+福利15=30，应封顶为15"""
        assert calculator.apply_cap(30, 240) == 15
    
    def test_cap_senior_employee_just_over_240(self, calculator):
        """老员工工龄241月：法定15+福利15=30，应封顶为15"""
        assert calculator.apply_cap(30, 241) == 15
    
    # ===== 边界测试：工龄恰好在240月 =====
    def test_cap_at_240_boundary(self, calculator):
        """工龄=240月时，属于老员工，封顶15天"""
        assert calculator.apply_cap(20, 240) == 15


class TestProratedCalculation:
    """入职/离职折算测试"""
    
    @pytest.fixture
    def calculator(self):
        return LeaveCalculator()
    
    # ===== 无入职/离职变动 =====
    def test_no_prorate_no_dates(self, calculator):
        """无入职/离职日期，不折算"""
        result = calculator.calculate_prorated_leave(12, None, None, 2026)
        assert result == 12
    
    # ===== 年中入职折算 =====
    def test_entry_july(self, calculator):
        """7月1日入职，应得6/12=0.5比例"""
        entry_date = date(2026, 7, 1)
        result = calculator.calculate_prorated_leave(12, entry_date, None, 2026)
        # 工作月份：7-12月共6个月
        assert result == 6.0  # 12 * 6/12 = 6
    
    def test_entry_march(self, calculator):
        """3月15日入职，应得10/12比例，四舍五入到0.5"""
        entry_date = date(2026, 3, 15)
        result = calculator.calculate_prorated_leave(12, entry_date, None, 2026)
        # 工作月份：3-12月共10个月（15日算整月）
        expected = round(12 * 10 / 12 * 2) / 2  # 10.0
        assert result == expected
    
    def test_entry_december(self, calculator):
        """12月入职，应得1/12比例"""
        entry_date = date(2026, 12, 1)
        result = calculator.calculate_prorated_leave(12, entry_date, None, 2026)
        # 工作月份：12月共1个月
        assert result == 1.0  # 12 * 1/12 = 1
    
    # ===== 年中离职折算 =====
    def test_leave_june(self, calculator):
        """6月30日离职，应得6/12=0.5比例"""
        leave_date = date(2026, 6, 30)
        result = calculator.calculate_prorated_leave(12, None, leave_date, 2026)
        # 工作月份：1-6月共6个月
        assert result == 6.0  # 12 * 6/12 = 6
    
    def test_leave_same_month_as_entry(self, calculator):
        """同月入职离职，按规则计算"""
        entry_date = date(2026, 6, 1)
        leave_date = date(2026, 6, 30)
        result = calculator.calculate_prorated_leave(12, entry_date, leave_date, 2026)
        # 工作月份：6月1个月（1日和30日比较，30>=1，所以算1个月）
        assert result == 1.0
    
    # ===== 入职前或离职后查询 =====
    def test_entry_next_year(self, calculator):
        """次年入职，当年查询应为0"""
        entry_date = date(2027, 3, 1)
        result = calculator.calculate_prorated_leave(12, entry_date, None, 2026)
        assert result == 0
    
    def test_leave_last_year(self, calculator):
        """去年离职，当年查询应为0"""
        leave_date = date(2025, 6, 30)
        result = calculator.calculate_prorated_leave(12, None, leave_date, 2026)
        assert result == 0
    
    # ===== 小数天数四舍五入测试 =====
    def test_prorate_round_to_half(self, calculator):
        """测试四舍五入到0.5天"""
        # 5个月折算：12 * 5/12 = 5.0
        entry_date = date(2026, 8, 15)  # 8-12月约5个月
        result = calculator.calculate_prorated_leave(12, entry_date, None, 2026)
        # 实际计算：15日>=1日，算整月，8-12月=5个月
        expected = round(12 * 5 / 12 * 2) / 2
        assert result == expected


class TestCarryoverCalculation:
    """上年结转测试"""
    
    @pytest.fixture
    def calculator(self):
        return LeaveCalculator()
    
    # ===== 3月31日前 =====
    def test_carryover_before_expire(self, calculator):
        """3月15日，上年剩余4天，应结转3天"""
        current_date = date(2026, 3, 15)
        carryover, expire_date = calculator.calculate_carryover(4, current_date)
        assert carryover == 3
        assert expire_date == date(2026, 3, 31)
    
    def test_carryover_less_than_max(self, calculator):
        """上年剩余2天，应全部结转"""
        current_date = date(2026, 3, 15)
        carryover, _ = calculator.calculate_carryover(2, current_date)
        assert carryover == 2
    
    def test_carryover_zero(self, calculator):
        """上年剩余0天"""
        current_date = date(2026, 3, 15)
        carryover, _ = calculator.calculate_carryover(0, current_date)
        assert carryover == 0
    
    # ===== 3月31日当天及之后 =====
    def test_carryover_on_expire_date(self, calculator):
        """3月31日当天，应正常结转"""
        current_date = date(2026, 3, 31)
        carryover, expire_date = calculator.calculate_carryover(4, current_date)
        # BUG 发现：代码中使用 > 而不是 >=，所以3月31日当天仍然可以结转
        # 这可能是预期行为，也可能是bug
        assert carryover == 3
        assert expire_date == date(2026, 3, 31)
    
    def test_carryover_after_expire(self, calculator):
        """4月1日，结转应清零"""
        current_date = date(2026, 4, 1)
        carryover, expire_date = calculator.calculate_carryover(4, current_date)
        assert carryover == 0
        assert expire_date is None


class TestUsedLeaveCalculation:
    """已用年假计算测试"""
    
    @pytest.fixture
    def calculator(self):
        return LeaveCalculator()
    
    # ===== 正常请假记录 =====
    def test_no_leave_records(self, calculator):
        """无请假记录"""
        result = calculator.calculate_used_leave([], 2026)
        assert result["approved"] == 0
        assert result["withdrawn"] == 0
        assert result["net"] == 0
    
    def test_approved_leave(self, calculator):
        """已通过请假2天"""
        records = [
            {
                "fields": {
                    "请假类型": "年假",
                    "申请状态": "已通过",
                    "时长": 2,
                    "开始时间": "2026-03-01T09:00:00Z"
                }
            }
        ]
        result = calculator.calculate_used_leave(records, 2026)
        assert result["approved"] == 2
        assert result["net"] == 2
    
    def test_withdrawn_leave(self, calculator):
        """已撤回请假1天"""
        records = [
            {
                "fields": {
                    "请假类型": "年假",
                    "申请状态": "已撤回",
                    "时长": 1,
                    "开始时间": "2026-03-01T09:00:00Z"
                }
            }
        ]
        result = calculator.calculate_used_leave(records, 2026)
        assert result["withdrawn"] == 1
        assert result["net"] == -1  # 撤回相当于加回
    
    def test_mixed_leave(self, calculator):
        """混合请假：通过3天+撤回1天"""
        records = [
            {
                "fields": {
                    "请假类型": "年假",
                    "申请状态": "已通过",
                    "时长": 3,
                    "开始时间": "2026-03-01T09:00:00Z"
                }
            },
            {
                "fields": {
                    "请假类型": "年假",
                    "申请状态": "已撤回",
                    "时长": 1,
                    "开始时间": "2026-04-01T09:00:00Z"
                }
            }
        ]
        result = calculator.calculate_used_leave(records, 2026)
        assert result["approved"] == 3
        assert result["withdrawn"] == 1
        assert result["net"] == 2
    
    # ===== 非年假类型过滤 =====
    def test_non_annual_leave_filtered(self, calculator):
        """病假不应计入年假"""
        records = [
            {
                "fields": {
                    "请假类型": "病假",
                    "申请状态": "已通过",
                    "时长": 3,
                    "开始时间": "2026-03-01T09:00:00Z"
                }
            }
        ]
        result = calculator.calculate_used_leave(records, 2026)
        assert result["approved"] == 0
        assert result["net"] == 0
    
    # ===== 跨年度记录过滤 =====
    def test_cross_year_filtered(self, calculator):
        """2025年的请假不应计入2026"""
        records = [
            {
                "fields": {
                    "请假类型": "年假",
                    "申请状态": "已通过",
                    "时长": 2,
                    "开始时间": "2025-03-01T09:00:00Z"
                }
            }
        ]
        result = calculator.calculate_used_leave(records, 2026)
        assert result["approved"] == 0


class TestIntegration:
    """综合计算流程测试"""
    
    @pytest.fixture
    def calculator(self):
        return LeaveCalculator()
    
    def test_full_calculation_normal_employee(self, calculator):
        """普通员工完整计算流程"""
        employee_data = {
            "fields": {
                "发起人": "测试员工",
                "Fullname": "Test Employee",
                "工龄(月)": 36,
                "司龄(月)": 36,
                "入职时间": "2023-03-01",
                "离职时间": None
            }
        }
        leave_records = []  # 无请假记录
        
        result = calculator.calculate_annual_leave_balance(
            employee_data, 
            leave_records, 
            previous_year_remaining=2,
            current_date=date(2026, 3, 15)
        )
        
        # 验证计算结果
        assert result["annual_leave"]["legal_quota"] == 5  # 法定5天
        assert result["annual_leave"]["welfare_quota"] == 4  # 福利3+1=4天
        assert result["annual_leave"]["subtotal"] == 9
        assert result["annual_leave"]["capped"] == 9  # 未超过12天封顶
        assert result["annual_leave"]["carryover"] == 2  # 上年结转2天
        assert result["annual_leave"]["remaining"] == 11  # 9+2=11天总额
    
    def test_full_calculation_senior_employee_with_cap(self, calculator):
        """资深员工封顶测试"""
        employee_data = {
            "fields": {
                "发起人": "资深员工",
                "Fullname": "Senior Employee",
                "工龄(月)": 200,
                "司龄(月)": 200,
                "入职时间": "2009-07-01",
                "离职时间": None
            }
        }
        leave_records = []
        
        result = calculator.calculate_annual_leave_balance(
            employee_data,
            leave_records,
            previous_year_remaining=3,
            current_date=date(2026, 2, 15)
        )
        
        # 验证：法定10+福利16=26，封顶12天
        assert result["annual_leave"]["legal_quota"] == 10
        assert result["annual_leave"]["welfare_quota"] == 16
        assert result["annual_leave"]["capped"] == 12  # 一般员工封顶12天
        assert result["annual_leave"]["remaining"] == 15  # 12+3=15天
    
    def test_full_calculation_old_employee_cap_15(self, calculator):
        """老员工15天封顶测试"""
        employee_data = {
            "fields": {
                "发起人": "老员工",
                "Fullname": "Old Employee",
                "工龄(月)": 300,
                "司龄(月)": 300,
                "入职时间": "2001-03-01",
                "离职时间": None
            }
        }
        leave_records = []
        
        result = calculator.calculate_annual_leave_balance(
            employee_data,
            leave_records,
            previous_year_remaining=3,  # 上年剩余3天可结转
            current_date=date(2026, 3, 15)  # 3月15日在结转有效期内
        )
        
        # 验证：法定15+福利25=40，老员工封顶15天
        assert result["annual_leave"]["legal_quota"] == 15
        assert result["annual_leave"]["welfare_quota"] == 25
        assert result["annual_leave"]["capped"] == 15  # 老员工封顶15天
        assert result["annual_leave"]["carryover"] == 3  # 结转3天
        assert result["annual_leave"]["remaining"] == 18  # 15+3=18天
    
    def test_full_calculation_mid_year_entry(self, calculator):
        """年中入职折算测试"""
        employee_data = {
            "fields": {
                "发起人": "新员工",
                "Fullname": "New Employee",
                "工龄(月)": 3,
                "司龄(月)": 3,
                "入职时间": "2025-09-01",
                "离职时间": None
            }
        }
        leave_records = []
        
        result = calculator.calculate_annual_leave_balance(
            employee_data,
            leave_records,
            previous_year_remaining=0,
            current_date=date(2026, 3, 15)
        )
        
        # 验证：法定0+福利6=6，全年折算4个月(9-12月)
        assert result["annual_leave"]["legal_quota"] == 0
        assert result["annual_leave"]["welfare_quota"] == 6
        # 2026年已过入职时间，不折算（假设在职满年）
        # 如果入职时间在当年，则会折算
    
    def test_full_calculation_with_used_leave(self, calculator):
        """有请假记录的完整计算"""
        employee_data = {
            "fields": {
                "发起人": "请假员工",
                "Fullname": "Leave Employee",
                "工龄(月)": 36,
                "司龄(月)": 36,
                "入职时间": "2023-03-01",
                "离职时间": None
            }
        }
        leave_records = [
            {
                "fields": {
                    "请假类型": "年假",
                    "申请状态": "已通过",
                    "时长": 2,
                    "开始时间": "2026-03-01T09:00:00Z"
                }
            },
            {
                "fields": {
                    "请假类型": "年假",
                    "申请状态": "已撤回",
                    "时长": 0.5,
                    "开始时间": "2026-02-15T09:00:00Z"
                }
            }
        ]
        
        result = calculator.calculate_annual_leave_balance(
            employee_data,
            leave_records,
            previous_year_remaining=1,
            current_date=date(2026, 3, 15)
        )
        
        # 验证已用年假计算
        assert result["annual_leave"]["used"]["approved"] == 2
        assert result["annual_leave"]["used"]["withdrawn"] == 0.5
        assert result["annual_leave"]["used"]["net"] == 1.5
        # 总剩余：9(当年)+1(结转)-1.5(净使用)=8.5
        assert result["annual_leave"]["remaining"] == 8.5


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
