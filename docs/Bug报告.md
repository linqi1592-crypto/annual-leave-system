# Bug 报告（最终版）

**测试工程师**: Ada + 另一 QA  
**日期**: 2026-03-24  
**测试范围**: leave_calculator.py 年假计算引擎

---

## Bug 汇总

| Bug ID | 严重程度 | 状态 | 标题 | 发现者 |
|--------|----------|------|------|--------|
| BUG-001 | 🔴 严重 | **已修复** | 工龄 240 个月时封顶逻辑错误 | 双方 |
| BUG-002 | 🟡 一般 | **已修复** | 测试用例数据错误（非代码 Bug）| Ada |
| BUG-003 | 🟡 一般 | **待添加测试** | 时区解析边界场景 | 另一 QA |

---

## Bug 详情

### BUG-001: 🔴 严重 - 工龄 240 个月封顶逻辑错误 ✅ 已修复

**严重程度**: P0  
**状态**: ✅ 已修复  
**发现者**: Ada 和另一 QA 同时发现

#### 问题
工龄 **正好等于 240 个月**（20 年）时，按一般员工封顶 12 天，应为老员工封顶 15 天。

#### 修复
```python
# leave_calculator.py 第 79 行
# 从
if social_security_months > cap["senior_threshold"]:
# 改为
if social_security_months >= cap["senior_threshold"]:
```

#### 验证
```bash
pytest tests/test_leave_calculator.py::TestCapCalculation -v
# 3 个 240 个月边界测试全部通过
```

---

### BUG-002: 🟡 一般 - 测试用例数据错误 ✅ 已修复

**严重程度**: P1  
**状态**: ✅ 已修复（测试用例修正）  
**发现者**: Ada

#### 问题
测试用例 `test_full_calculation_old_employee_cap_15` 中：
- 设置 `previous_year_remaining=0`（上年剩余 0 天）
- 但期望 `remaining == 18`（15+3 结转）

这是矛盾的，上年剩余 0 天 → 结转 0 天 → 剩余应为 15 天。

#### 修复
```python
# 修改测试数据
previous_year_remaining=3  # 上年剩余 3 天可结转
current_date=date(2026, 3, 15)  # 确保在 3 月 31 日前

# 期望结果
assert result["annual_leave"]["remaining"] == 18  # 15+3=18天
```

**结论**: 这是**测试用例数据错误**，不是代码 Bug。代码逻辑正确（结转独立于封顶）。

---

### BUG-003: 🟡 一般 - 时区解析边界场景 ⚠️ 待添加测试

**严重程度**: P1  
**状态**: ⚠️ 需添加测试用例覆盖  
**发现者**: 另一 QA

#### 问题描述
时间戳 `1748707200000`（UTC 2025-05-31 16:00:00）在 UTC+8 下是 2025-06-01 00:00:00，年份为 2025。

如果测试期望是 2026，那是测试数据问题。但**真实风险**在于：
- 飞书返回 UTC 时间戳
- 跨年时区差异可能导致 12 月 31 日 UTC 被解析为次年 1 月 1 日北京时间
- 影响跨年请假记录的年份归属

#### 建议添加测试用例
```python
def test_cross_year_timezone_boundary(self):
    """跨年时区边界测试"""
    # UTC 12月31日 20:00 = 北京时间次年1月1日 04:00
    ts = 1735689600000  # 2025-01-01 00:00:00 UTC
    
    # 应正确解析为北京时间 2025年（而非2024年）
    year = parse_timestamp_year(ts)
    assert year == 2025
```

#### 当前代码状态
`parse_timestamp_year()` 已实现 UTC→本地时区转换，但**测试覆盖不足**。

---

## 修复记录

### 代码修改

1. **leave_calculator.py** (1 行)
   - `>` 改为 `>=` （240个月边界）

2. **tests/test_leave_calculator.py** (1 处)
   - `previous_year_remaining=0` 改为 `=3`

3. **docs/Bug报告.md** (更新状态)
   - 添加 BUG-003 时区问题

### 测试验证

```bash
$ pytest tests/test_leave_calculator.py -v

============================= test session starts ==============================
platform darwin -- Python 3.9.6, pytest-8.4.2 -- /Library/Developer/CommandLineTools/usr/bin/python3
collected 55 items

tests/test_leave_calculator.py::TestLegalLeaveCalculation::test_legal_leave_11_months PASSED [  1%]
...
tests/test_leave_calculator.py::TestIntegration::test_full_calculation_old_employee_cap_15 PASSED [ 96%]
...

============================== 55 passed in 0.19s ==============================
```

**通过率**: 100% (55/55)

---

## 规则确认（最终版）

经与 HR 确认，老员工年假计算规则：

| 项目 | 规则 |
|------|------|
| 老员工定义 | 工龄 >= 240 个月（20年） |
| 法定+福利封顶 | 15 天（独立计算） |
| 上年结转 | 最多 3 天，**不包含在15天内** |
| 老员工最大年假 | 15 + 3 = **18 天** |
| 结转有效期 | 次年 3 月 31 日 |

---

## 待办事项

- [x] 修复 240 个月封顶边界 Bug
- [x] 修复测试用例数据错误
- [ ] 添加时区边界测试用例（BUG-003）
- [ ] 补充 API 接口测试（鉴权、错误处理）

---

**报告人**: Ada + 另一 QA  
**修复验证**: 犀甲 🦞
