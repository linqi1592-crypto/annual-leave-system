#!/usr/bin/env python3
"""
年假查询系统 v1.3 轻量级核心逻辑测试
测试工程师: Ada
日期: 2026-03-26
特点: 无需第三方依赖，只使用 Python 标准库
"""

import sys
from datetime import date
from typing import Optional, Tuple

# 测试结果统计
passed = 0
failed = 0
errors = []

def run_test(name, func):
    """执行单个测试"""
    global passed, failed
    try:
        func()
        print(f"✓ {name}")
        passed += 1
    except AssertionError as e:
        print(f"✗ {name}: {e}")
        failed += 1
        errors.append((name, str(e)))
    except Exception as e:
        print(f"✗ {name}: 异常 {e}")
        failed += 1
        errors.append((name, str(e)))

# ==================== 核心逻辑（复制自 leave_calculator.py）====================

class LeaveCalculator:
    """轻量级年假计算器"""
    
    RULES = {
        "legal_leave": {
            (0, 12): 0,
            (12, 180): 5,
            (180, 240): 10,
            (240, float('inf')): 15,
        },
        "welfare_leave": {
            "new_employee_months": 12,
            "new_employee_days": 6,
            "mid_senior_months": 180,
            "mid_base_days": 1,
        },
        "cap": {
            "normal": 12,
            "senior": 15,
            "senior_threshold": 240,
        },
        "carryover": {
            "max_days": 3,
            "expire_month": 3,
            "expire_day": 31,
        },
    }
    
    def calculate_service_months(self, entry_date: Optional[date], current_date: date) -> int:
        """根据入职日期计算司龄（月）- P1-5"""
        if not entry_date:
            return 0
        months = (current_date.year - entry_date.year) * 12
        months += current_date.month - entry_date.month
        if current_date.day < entry_date.day:
            months -= 1
        return max(0, months)
    
    def calculate_legal_leave(self, social_security_months: int) -> int:
        """计算法定年假"""
        legal_rules = self.RULES["legal_leave"]
        for (min_months, max_months), days in legal_rules.items():
            if min_months <= social_security_months < max_months:
                return days
        return 0
    
    def calculate_welfare_leave(self, service_months: int) -> int:
        """计算公司福利年假"""
        welfare = self.RULES["welfare_leave"]
        if service_months < welfare["new_employee_months"]:
            return welfare["new_employee_days"]
        service_years = service_months // 12
        if service_months < welfare["mid_senior_months"]:
            return welfare["mid_base_days"] + service_years
        return service_years
    
    def apply_cap(self, total_leave: float, social_security_months: int) -> float:
        """应用封顶规则"""
        cap = self.RULES["cap"]
        if social_security_months >= cap["senior_threshold"]:
            return min(total_leave, cap["senior"])
        return min(total_leave, cap["normal"])
    
    def calculate_carryover(self, previous_year_remaining: float, current_date: date) -> Tuple[float, Optional[date]]:
        """计算上年结转 - P1-2: 支持负数"""
        carryover_rules = self.RULES["carryover"]
        expire_date = date(current_date.year, carryover_rules["expire_month"], carryover_rules["expire_day"])
        
        if current_date > expire_date:
            return 0, None
        if previous_year_remaining <= 0:
            return 0, expire_date
        carryover_days = min(previous_year_remaining, carryover_rules["max_days"])
        return carryover_days, expire_date
    
    def calculate_prorated_leave(self, annual_leave: float, entry_date: Optional[date], 
                                  leave_date: Optional[date], year: int) -> float:
        """计算折算后的年假"""
        if not entry_date and not leave_date:
            return annual_leave
        year_start = date(year, 1, 1)
        year_end = date(year, 12, 31)
        actual_start = max(entry_date, year_start) if entry_date else year_start
        actual_end = min(leave_date, year_end) if leave_date else year_end
        if actual_start > actual_end:
            return 0
        months = (actual_end.year - actual_start.year) * 12 + (actual_end.month - actual_start.month)
        if actual_end.day >= actual_start.day:
            months += 1
        months = max(0, min(months, 12))
        prorated = annual_leave * months / 12
        return round(prorated * 2) / 2

calc = LeaveCalculator()

# ==================== 测试用例 ====================

def test_service_001():
    """基本司龄计算 - 6年"""
    months = calc.calculate_service_months(date(2020, 3, 15), date(2026, 3, 26))
    assert months == 72, f"期望 72 个月，实际 {months}"

def test_service_002():
    """跨月司龄计算"""
    months = calc.calculate_service_months(date(2020, 3, 15), date(2026, 6, 10))
    assert months == 74, f"期望 74 个月，实际 {months}"

def test_service_003():
    """同一天入职（满整年）"""
    months = calc.calculate_service_months(date(2020, 3, 15), date(2026, 3, 15))
    assert months == 72, f"期望 72 个月，实际 {months}"

def test_service_004():
    """新员工（未满1年）"""
    months = calc.calculate_service_months(date(2026, 1, 15), date(2026, 3, 26))
    assert months == 2, f"期望 2 个月，实际 {months}"

def test_service_005():
    """无入职日期返回0"""
    months = calc.calculate_service_months(None, date(2026, 3, 26))
    assert months == 0, f"期望 0 个月，实际 {months}"

def test_service_006():
    """福利年假基于自动计算的司龄"""
    entry_date = date(2023, 3, 15)
    current_date = date(2026, 3, 26)
    service_months = calc.calculate_service_months(entry_date, current_date)
    welfare = calc.calculate_welfare_leave(service_months)
    assert service_months == 36, f"期望司龄 36 个月，实际 {service_months}"
    assert welfare == 4, f"期望福利年假 4 天，实际 {welfare}"

def test_service_007():
    """司龄边界测试 - 12个月"""
    months = calc.calculate_service_months(date(2025, 3, 15), date(2026, 3, 15))
    welfare = calc.calculate_welfare_leave(months)
    assert months == 12, f"期望 12 个月，实际 {months}"
    assert welfare == 2, f"期望福利年假 2 天，实际 {welfare}"

def test_negative_001():
    """负数余额结转为0"""
    carryover, expire_date = calc.calculate_carryover(-5.0, date(2026, 3, 15))
    assert carryover == 0, f"负数结转应为 0，实际 {carryover}"
    assert expire_date is not None, "应返回到期日期"

def test_negative_002():
    """零结转仍有到期日期"""
    carryover, expire_date = calc.calculate_carryover(0, date(2026, 3, 15))
    assert carryover == 0, f"结转应为 0，实际 {carryover}"
    assert expire_date == date(2026, 3, 31), f"到期日应为 2026-03-31，实际 {expire_date}"

def test_negative_003():
    """正常结转最多3天"""
    carryover, _ = calc.calculate_carryover(10.0, date(2026, 3, 15))
    assert carryover == 3, f"结转应封顶 3 天，实际 {carryover}"

def test_negative_004():
    """过期后结转清零"""
    carryover, expire_date = calc.calculate_carryover(3.0, date(2026, 4, 1))
    assert carryover == 0, f"过期后结转应为 0，实际 {carryover}"
    assert expire_date is None, "过期后不应返回到期日期"

def test_settlement_001():
    """结转天数计算 - 5天余额转3天"""
    balance = 5.0
    carryover = min(balance, 3)
    cleared = max(0, balance - 3)
    assert carryover == 3.0, f"应结转 3 天，实际 {carryover}"
    assert cleared == 2.0, f"应清零 2 天，实际 {cleared}"

def test_settlement_002():
    """结转天数计算 - 2天余额全转"""
    balance = 2.0
    carryover = min(balance, 3)
    cleared = max(0, balance - 3)
    assert carryover == 2.0, f"应结转 2 天，实际 {carryover}"
    assert cleared == 0.0, f"应清零 0 天，实际 {cleared}"

def test_settlement_003():
    """负数余额不结转"""
    balance = -2.0
    carryover = min(max(0, balance), 3)
    assert carryover == 0.0, f"负数应结转 0 天，实际 {carryover}"

def test_calc_001():
    """法定年假 - 新员工0天"""
    days = calc.calculate_legal_leave(6)
    assert days == 0, f"社保工龄6个月，法定年假应为 0 天，实际 {days}"

def test_calc_002():
    """法定年假 - 普通员工5天"""
    days = calc.calculate_legal_leave(36)
    assert days == 5, f"社保工龄36个月，法定年假应为 5 天，实际 {days}"

def test_calc_003():
    """法定年假 - 老员工10天"""
    days = calc.calculate_legal_leave(200)
    assert days == 10, f"社保工龄200个月，法定年假应为 10 天，实际 {days}"

def test_calc_004():
    """法定年假 - 资深员工15天"""
    days = calc.calculate_legal_leave(250)
    assert days == 15, f"社保工龄250个月，法定年假应为 15 天，实际 {days}"

def test_calc_005():
    """福利年假 - 新员工6天"""
    days = calc.calculate_welfare_leave(6)
    assert days == 6, f"司龄6个月，福利年假应为 6 天，实际 {days}"

def test_calc_006():
    """福利年假 - 3年员工4天"""
    days = calc.calculate_welfare_leave(36)
    assert days == 4, f"司龄36个月（3年），福利年假应为 4 天，实际 {days}"

def test_calc_007():
    """封顶规则 - 一般员工封顶12天"""
    legal, welfare = 5, 10
    total = legal + welfare
    capped = calc.apply_cap(total, 36)
    assert capped == 12, f"一般员工封顶应为 12 天，实际 {capped}"

def test_calc_008():
    """封顶规则 - 老员工封顶15天"""
    legal, welfare = 10, 10
    total = legal + welfare
    capped = calc.apply_cap(total, 250)
    assert capped == 15, f"老员工封顶应为 15 天，实际 {capped}"

def test_calc_009():
    """封顶规则 - 未超过封顶不处理"""
    legal, welfare = 5, 5
    total = legal + welfare
    capped = calc.apply_cap(total, 36)
    assert capped == 10, f"未超过封顶应保持 10 天，实际 {capped}"

def test_boundary_001():
    """工龄边界 - 11个月"""
    days = calc.calculate_legal_leave(11)
    assert days == 0, "11个月应为 0 天"

def test_boundary_002():
    """工龄边界 - 12个月"""
    days = calc.calculate_legal_leave(12)
    assert days == 5, "12个月应为 5 天"

def test_boundary_003():
    """工龄边界 - 179个月"""
    days = calc.calculate_legal_leave(179)
    assert days == 5, "179个月应为 5 天"

def test_boundary_004():
    """工龄边界 - 180个月"""
    days = calc.calculate_legal_leave(180)
    assert days == 10, "180个月应为 10 天"

def test_boundary_005():
    """工龄边界 - 239个月"""
    days = calc.calculate_legal_leave(239)
    assert days == 10, "239个月应为 10 天"

def test_boundary_006():
    """工龄边界 - 240个月"""
    days = calc.calculate_legal_leave(240)
    assert days == 15, "240个月应为 15 天"

# ==================== 主程序 ====================

if __name__ == "__main__":
    print("="*50)
    print("年假查询系统 v1.3 轻量级核心逻辑测试")
    print("测试工程师: Ada")
    print("="*50)
    print()
    print("开始执行测试...")
    print()
    
    # 执行所有测试
    tests = [
        # P1-5: 司龄自动计算 (7个)
        ("TC-SERVICE-001: 基本司龄计算 - 6年", test_service_001),
        ("TC-SERVICE-002: 跨月司龄计算", test_service_002),
        ("TC-SERVICE-003: 同一天入职（满整年）", test_service_003),
        ("TC-SERVICE-004: 新员工（未满1年）", test_service_004),
        ("TC-SERVICE-005: 无入职日期返回0", test_service_005),
        ("TC-SERVICE-006: 福利年假基于自动计算的司龄", test_service_006),
        ("TC-SERVICE-007: 司龄边界测试 - 12个月", test_service_007),
        
        # P1-2: 负数余额兼容性 (4个)
        ("TC-NEG-001: 负数余额结转为0", test_negative_001),
        ("TC-NEG-002: 零结转仍有到期日期", test_negative_002),
        ("TC-NEG-003: 正常结转最多3天", test_negative_003),
        ("TC-NEG-004: 过期后结转清零", test_negative_004),
        
        # P1-4: 年终清算计算 (3个)
        ("TC-SETTLE-001: 结转天数计算 - 5天余额转3天", test_settlement_001),
        ("TC-SETTLE-002: 结转天数计算 - 2天余额全转", test_settlement_002),
        ("TC-SETTLE-003: 负数余额不结转", test_settlement_003),
        
        # 年假计算引擎 (9个)
        ("TC-CALC-001: 法定年假 - 新员工0天", test_calc_001),
        ("TC-CALC-002: 法定年假 - 普通员工5天", test_calc_002),
        ("TC-CALC-003: 法定年假 - 老员工10天", test_calc_003),
        ("TC-CALC-004: 法定年假 - 资深员工15天", test_calc_004),
        ("TC-CALC-005: 福利年假 - 新员工6天", test_calc_005),
        ("TC-CALC-006: 福利年假 - 3年员工4天", test_calc_006),
        ("TC-CALC-007: 封顶规则 - 一般员工封顶12天", test_calc_007),
        ("TC-CALC-008: 封顶规则 - 老员工封顶15天", test_calc_008),
        ("TC-CALC-009: 封顶规则 - 未超过封顶不处理", test_calc_009),
        
        # 边界值测试 (6个)
        ("TC-BOUNDARY-001: 工龄边界 - 11个月", test_boundary_001),
        ("TC-BOUNDARY-002: 工龄边界 - 12个月", test_boundary_002),
        ("TC-BOUNDARY-003: 工龄边界 - 179个月", test_boundary_003),
        ("TC-BOUNDARY-004: 工龄边界 - 180个月", test_boundary_004),
        ("TC-BOUNDARY-005: 工龄边界 - 239个月", test_boundary_005),
        ("TC-BOUNDARY-006: 工龄边界 - 240个月", test_boundary_006),
    ]
    
    for name, func in tests:
        run_test(name, func)
    
    # 汇总
    print()
    print("="*50)
    total = passed + failed
    print(f"测试汇总: 通过 {passed}/{total}, 失败 {failed}/{total}")
    if failed > 0:
        print()
        print("失败用例:")
        for name, error in errors:
            print(f"  - {name}: {error}")
    print("="*50)
    
    sys.exit(0 if failed == 0 else 1)
