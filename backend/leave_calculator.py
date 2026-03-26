"""
年假计算引擎 - v1.3 更新
- P1-5: 司龄递增自动化（根据入职日期自动计算司龄）
- P1-1: 余额卡片分栏展示（返回更详细的余额信息）
"""

import math
from datetime import datetime, date
from typing import Dict, List, Any, Optional, Tuple
from config import LEAVE_RULES, VALID_LEAVE_TYPES, VALID_STATUSES


class LeaveCalculator:
    """年假计算器"""
    
    def __init__(self):
        self.rules = LEAVE_RULES
    
    def calculate_service_months(self, entry_date: Optional[date], current_date: date) -> int:
        """
        根据入职日期计算司龄（月）- v1.3 P1-5 新增
        
        Args:
            entry_date: 入职日期
            current_date: 当前日期
            
        Returns:
            司龄（月）
        """
        if not entry_date:
            return 0
        
        months = (current_date.year - entry_date.year) * 12
        months += current_date.month - entry_date.month
        
        # 如果当前日期还没到入职日，减去1个月
        if current_date.day < entry_date.day:
            months -= 1
        
        return max(0, months)
    
    def calculate_legal_leave(self, social_security_months: int) -> int:
        """
        计算法定年假
        
        Args:
            social_security_months: 社保工龄（月）
            
        Returns:
            法定年假天数
        """
        legal_rules = self.rules["legal_leave"]
        
        for (min_months, max_months), days in legal_rules.items():
            if min_months <= social_security_months < max_months:
                return days
        
        return 0
    
    def calculate_welfare_leave(self, service_months: int) -> int:
        """
        计算公司福利年假（基于司龄月数）
        
        Args:
            service_months: 司龄（月）
            
        Returns:
            福利年假天数
        """
        welfare = self.rules["welfare_leave"]
        
        # 新员工（<12个月）
        if service_months < welfare["new_employee_months"]:
            return welfare["new_employee_days"]
        
        # 司龄年数
        service_years = service_months // 12
        
        # 中高级员工（12-180个月）
        if service_months < welfare["mid_senior_months"]:
            return welfare["mid_base_days"] + service_years
        
        # 高级员工（>=180个月）
        return service_years
    
    def apply_cap(self, total_leave: int, social_security_months: int) -> int:
        """
        应用封顶规则
        
        Args:
            total_leave: 法定+福利总和
            social_security_months: 社保工龄（月）
            
        Returns:
            封顶后的年假天数
        """
        cap = self.rules["cap"]
        
        # 老员工（工龄>=240月）封顶15天
        if social_security_months >= cap["senior_threshold"]:
            return min(total_leave, cap["senior"])
        
        # 一般员工封顶12天
        return min(total_leave, cap["normal"])
    
    def calculate_prorated_leave(
        self, 
        annual_leave: float, 
        entry_date: Optional[date],
        leave_date: Optional[date],
        year: int
    ) -> float:
        """
        计算折算后的年假（入职/离职）
        
        Args:
            annual_leave: 原始年假天数
            entry_date: 入职日期
            leave_date: 离职日期
            year: 计算年份
            
        Returns:
            折算后的年假天数（0.5天为最小单位）
        """
        # 如果当年没有入职/离职变动，不折算
        if not entry_date and not leave_date:
            return annual_leave
        
        # 计算当年实际工作月数
        year_start = date(year, 1, 1)
        year_end = date(year, 12, 31)
        
        actual_start = max(entry_date, year_start) if entry_date else year_start
        actual_end = min(leave_date, year_end) if leave_date else year_end
        
        if actual_start > actual_end:
            return 0
        
        # 计算月数
        months = (actual_end.year - actual_start.year) * 12 + (actual_end.month - actual_start.month)
        if actual_end.day >= actual_start.day:
            months += 1
        
        months = max(0, min(months, 12))
        
        # 按比例计算，四舍五入到0.5天
        prorated = annual_leave * months / 12
        return round(prorated * 2) / 2
    
    def calculate_carryover(
        self, 
        previous_year_remaining: float, 
        current_date: date
    ) -> Tuple[float, Optional[date]]:
        """
        计算上年结转年假
        
        Args:
            previous_year_remaining: 上年剩余年假（v1.3 P1-2: 支持负数，负数结转为0）
            current_date: 当前日期
            
        Returns:
            (结转天数, 到期日期)
        """
        carryover_rules = self.rules["carryover"]
        
        # 构建当年到期日（3月31日）
        expire_date = date(current_date.year, carryover_rules["expire_month"], carryover_rules["expire_day"])
        
        # 如果已过3月31日，结转清零
        if current_date > expire_date:
            return 0, None
        
        # v1.3 P1-2: 如果上年剩余为负数，结转为0（不传递负数）
        if previous_year_remaining <= 0:
            return 0, expire_date
        
        # 结转最多3天
        carryover_days = min(previous_year_remaining, carryover_rules["max_days"])
        return carryover_days, expire_date
    
    def calculate_used_leave(
        self, 
        leave_records: List[Dict[str, Any]], 
        year: int
    ) -> Dict[str, float]:
        """
        计算已用年假
        
        Args:
            leave_records: 请假记录列表
            year: 计算年份
            
        Returns:
            {"approved": 已通过天数, "withdrawn": 已撤回天数, "net": 净使用天数}
        """
        approved_days = 0.0
        withdrawn_days = 0.0
        
        for record in leave_records:
            fields = record.get("fields", {})
            
            # 检查请假类型
            leave_type = fields.get("请假类型", "")
            if leave_type not in VALID_LEAVE_TYPES:
                continue
            
            # 检查状态
            status = fields.get("申请状态", "")
            duration = fields.get("时长", 0) or 0
            
            # 获取请假日期
            start_time = fields.get("开始时间")
            if not start_time:
                continue
            
            # 解析日期（飞书返回的是时间戳或ISO格式）
            try:
                if isinstance(start_time, (int, float)):
                    leave_year = datetime.fromtimestamp(start_time / 1000).year
                else:
                    leave_year = datetime.fromisoformat(start_time.replace('Z', '+00:00')).year
            except:
                continue
            
            # 只统计当年
            if leave_year != year:
                continue
            
            # 已通过：扣减年假
            if status == VALID_STATUSES["approved"]:
                approved_days += float(duration)
            
            # 已撤回：加回年假
            elif status == VALID_STATUSES["withdrawn"]:
                withdrawn_days += float(duration)
        
        return {
            "approved": approved_days,
            "withdrawn": withdrawn_days,
            "net": approved_days - withdrawn_days
        }
    
    def calculate_annual_leave_balance(
        self,
        employee_data: Dict[str, Any],
        leave_records: List[Dict[str, Any]],
        previous_year_remaining: float = 0.0,
        current_date: Optional[date] = None
    ) -> Dict[str, Any]:
        """
        计算年假余额（完整流程）- v1.3 更新
        
        Args:
            employee_data: 员工信息
            leave_records: 请假记录
            previous_year_remaining: 上年剩余（已调整后的）
            current_date: 当前日期（默认今天）
            
        Returns:
            年假计算结果（包含 v1.3 P1-1 分栏展示所需数据）
        """
        if current_date is None:
            current_date = date.today()
        
        year = current_date.year
        
        # 提取员工信息
        fields = employee_data.get("fields", {})
        social_security_months = fields.get("工龄(月)", 0) or 0
        
        # v1.3 P1-5: 根据入职日期自动计算司龄
        entry_date = self._parse_date(fields.get("入职时间"))
        service_months = self.calculate_service_months(entry_date, current_date)
        
        # 兼容：如果无法从入职日期计算，回退到读取表格字段
        if service_months == 0 and fields.get("司龄(月)"):
            service_months = fields.get("司龄(月)", 0) or 0
        
        # 解析离职日期
        leave_date = self._parse_date(fields.get("离职时间"))
        
        # 1. 计算法定年假
        legal_leave = self.calculate_legal_leave(social_security_months)
        
        # 2. 计算福利年假（使用自动计算的司龄）
        welfare_leave = self.calculate_welfare_leave(service_months)
        
        # 3. 小计
        subtotal = legal_leave + welfare_leave
        
        # 4. 应用封顶
        capped_leave = self.apply_cap(subtotal, social_security_months)
        
        # 5. 入职/离职折算
        current_year_leave = self.calculate_prorated_leave(
            capped_leave, entry_date, leave_date, year
        )
        
        # 6. 计算上年结转
        carryover, expire_date = self.calculate_carryover(previous_year_remaining, current_date)
        
        # 7. 总年假额度
        total_quota = current_year_leave + carryover
        
        # 8. 计算已用年假
        used_info = self.calculate_used_leave(leave_records, year)
        
        # 9. 剩余年假（v1.3 P1-2: 支持负数）
        remaining = total_quota - used_info["net"]
        
        # v1.3 P1-1: 返回分栏展示所需数据
        return {
            "year": year,
            "current_date": current_date.isoformat(),
            "employee": {
                "name": fields.get("发起人", ""),
                "fullname": fields.get("Fullname", ""),
                "social_security_months": social_security_months,
                "service_months": service_months,  # v1.3: 自动计算的司龄
                "service_years": service_months // 12,
                "entry_date": entry_date.isoformat() if entry_date else None,
                "leave_date": leave_date.isoformat() if leave_date else None,
            },
            "annual_leave": {
                # v1.3 P1-1: 分栏展示数据
                "current_year": {
                    "quota": current_year_leave,
                    "used": used_info["approved"],  # 当年额度中已使用的
                },
                "carryover": {
                    "quota": carryover,
                    "used": max(0, used_info["net"] - current_year_leave) if used_info["net"] > current_year_leave else 0,
                    "expire_date": expire_date.isoformat() if expire_date else None,
                },
                "total_used": used_info["net"],
                "remaining": remaining,
                "is_negative": remaining < 0,  # v1.3 P1-2: 负数标识
                
                # 详细计算过程（保留供参考）
                "legal_quota": legal_leave,
                "welfare_quota": welfare_leave,
                "subtotal": subtotal,
                "capped": capped_leave,
                "total_quota": total_quota,
                "used": used_info,
            },
            "calculation_details": {
                "formula": f"剩余年假 = 当年额度({current_year_leave}) + 结转({carryover}) - 已用({used_info['net']})",
                "breakdown": {
                    "当年额度": current_year_leave,
                    "上年结转": carryover,
                    "已通过请假": used_info["approved"],
                    "已撤回请假": used_info["withdrawn"],
                    "净使用": used_info["net"],
                }
            }
        }
    
    def _parse_date(self, date_value: Any) -> Optional[date]:
        """解析日期字段 - P1: 统一时区处理"""
        if not date_value:
            return None
        
        try:
            from zoneinfo import ZoneInfo
            tz = ZoneInfo("Asia/Shanghai")
            
            if isinstance(date_value, (int, float)):
                # 时间戳（毫秒）- 统一使用 UTC 解析后转本地
                if date_value > 1e10:
                    dt = datetime.fromtimestamp(date_value / 1000, tz=ZoneInfo("UTC"))
                else:
                    dt = datetime.fromtimestamp(date_value, tz=ZoneInfo("UTC"))
                return dt.astimezone(tz).date()
            elif isinstance(date_value, str):
                # ISO 格式或普通日期字符串
                if 'T' in date_value:
                    dt = datetime.fromisoformat(date_value.replace('Z', '+00:00'))
                    return dt.astimezone(tz).date()
                else:
                    return datetime.strptime(date_value, "%Y-%m-%d").date()
        except:
            pass
        
        return None


# 全局计算器实例
calculator = LeaveCalculator()


def calculate_previous_year_remaining(
    employee: dict, 
    employee_name: str, 
    year: int,
    feishu_client_instance=None
) -> float:
    """
    计算某年度系统计算的剩余年假（用于导出和年终清算）
    
    Args:
        employee: 员工数据
        employee_name: 员工姓名
        year: 计算年份
        feishu_client_instance: 飞书客户端实例（避免循环导入）
    
    Returns:
        该年度剩余年假天数
    """
    try:
        if not employee:
            return 0.0
        
        # 延迟导入避免循环导入
        if feishu_client_instance is None:
            from feishu_client import feishu_client as fc
            feishu_client_instance = fc
        
        # 获取该年度的请假记录
        leave_records = feishu_client_instance.get_leave_records(employee_name)
        
        # 只保留该年度的记录
        year_records = []
        for record in leave_records:
            fields = record.get("fields", {})
            start_time = fields.get("开始时间")
            if start_time:
                try:
                    # 统一时区解析
                    from datetime import datetime
                    from zoneinfo import ZoneInfo
                    
                    if isinstance(start_time, (int, float)):
                        if start_time > 1e10:
                            dt = datetime.fromtimestamp(start_time / 1000, tz=ZoneInfo("UTC"))
                        else:
                            dt = datetime.fromtimestamp(start_time, tz=ZoneInfo("UTC"))
                        record_year = dt.astimezone(ZoneInfo("Asia/Shanghai")).year
                    elif isinstance(start_time, str) and 'T' in start_time:
                        dt = datetime.fromisoformat(start_time.replace('Z', '+00:00'))
                        record_year = dt.astimezone(ZoneInfo("Asia/Shanghai")).year
                    else:
                        record_year = int(str(start_time)[:4])
                    
                    if record_year == year:
                        year_records.append(record)
                except:
                    continue
        
        # 计算该年度（假设没有上年结转）
        year_end = date(year, 12, 31)
        result = calculator.calculate_annual_leave_balance(
            employee, year_records, 0.0, year_end
        )
        
        return result["annual_leave"]["remaining"]
        
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"计算上年剩余失败: {employee_name}, year={year}, error={e}")
        return 0.0


if __name__ == "__main__":
    # 测试计算逻辑
    print("测试年假计算引擎 v1.3...")
    
    # 测试用例1: 司龄自动计算
    print("\n1. 司龄自动计算测试")
    entry_date = date(2020, 3, 15)
    current_date = date(2026, 3, 25)
    service_months = calculator.calculate_service_months(entry_date, current_date)
    print(f"   入职日期: {entry_date}, 当前日期: {current_date}")
    print(f"   司龄: {service_months}个月 ({service_months // 12}年)")
    
    # 测试用例2: 新员工
    print("\n2. 新员工（司龄6个月，工龄6个月）")
    legal = calculator.calculate_legal_leave(6)
    welfare = calculator.calculate_welfare_leave(6)
    print(f"   法定: {legal}天, 福利: {welfare}天")
    
    # 测试用例3: 普通员工
    print("\n3. 普通员工（司龄3年，工龄3年）")
    legal = calculator.calculate_legal_leave(36)
    welfare = calculator.calculate_welfare_leave(36)
    capped = calculator.apply_cap(legal + welfare, 36)
    print(f"   法定: {legal}天, 福利: {welfare}天, 封顶后: {capped}天")
    
    # 测试用例4: 负数余额结转
    print("\n4. 负数余额结转测试（上年剩余-2天）")
    carryover, expire = calculator.calculate_carryover(-2, date(2026, 3, 15))
    print(f"   可结转: {carryover}天 (负数应转为0)")
    
    print("\n✅ 测试完成")
