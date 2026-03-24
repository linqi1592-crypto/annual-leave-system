import os

# 飞书配置（从环境变量读取，避免硬编码）
FEISHU_CONFIG = {
    "app_id": os.getenv("FEISHU_APP_ID", "cli_a94b9cb9af39dccc"),
    "app_secret": os.getenv("FEISHU_APP_SECRET", ""),  # 从环境变量读取
    "app_token": os.getenv("FEISHU_APP_TOKEN", "DH8rbr0abakqOks4nGNcF8JYn6c"),
}

# 多维表格配置
BITABLE_CONFIG = {
    "employee_table_id": "tbls5vXl99F0fFRn",  # 员工信息表
    "leave_table_id": "tbl5vlfwyRzhNIhb",     # 请假记录表
}

# API 端点
FEISHU_API = {
    "base_url": "https://open.feishu.cn/open-apis",
    "auth_url": "/auth/v3/tenant_access_token/internal",
    "bitable_records": "/bitable/v1/apps/{app_token}/tables/{table_id}/records",
}

# 年假规则配置
LEAVE_RULES = {
    # 法定年假（按社保工龄，月）
    "legal_leave": {
        (0, 12): 0,        # < 12个月
        (12, 180): 5,      # 12-180个月
        (180, 240): 10,    # 180-240个月
        (240, float('inf')): 15,  # > 240个月
    },
    # 福利年假（按司龄）
    "welfare_leave": {
        "new_employee_months": 12,   # 新员工界限（月）
        "new_employee_days": 6,      # 新员工福利年假
        "mid_senior_months": 180,    # 中高级界限（月）
        "mid_base_days": 1,          # 中高级基础福利
    },
    # 封顶
    "cap": {
        "normal": 12,      # 一般员工封顶
        "senior": 15,      # 老员工封顶（工龄>240月）
        "senior_threshold": 240,  # 老员工界限（月）
    },
    # 结转
    "carryover": {
        "max_days": 3,     # 最多结转3天
        "expire_month": 3, # 3月31日到期
        "expire_day": 31,
    },
}

# 请假类型（算入年假额度的）
VALID_LEAVE_TYPES = ["年假", "事假"]

# 申请状态（参与计算的）
VALID_STATUSES = {
    "approved": "已通过",  # 扣减年假
    "withdrawn": "已撤回",  # 加回年假
}

# 数据库配置
DB_CONFIG = {
    "path": "data/leave_adjustments.db",
}
