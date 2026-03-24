"""
测试配置文件 - 用于单元测试
不使用环境变量，直接提供测试值
"""

# 测试用的飞书配置
FEISHU_CONFIG = {
    "app_id": "test_app_id",
    "app_secret": "test_app_secret",
    "app_token": "test_app_token",
    "encrypt_key": "test_encrypt_key",
    "verification_token": "test_verification_token",
}

# CORS 配置
CORS_ALLOW_ALL = True
CORS_ALLOWED_ORIGINS = ["*"]

# 时区配置
TIMEZONE = "Asia/Shanghai"

# 多维表格配置
BITABLE_CONFIG = {
    "employee_table_id": "test_employee_table",
    "leave_table_id": "test_leave_table",
}

# API 端点
FEISHU_API = {
    "base_url": "https://open.feishu.cn/open-apis",
    "auth_url": "/auth/v3/tenant_access_token/internal",
    "bitable_records": "/bitable/v1/apps/{app_token}/tables/{table_id}/records",
    "user_info": "/contact/v3/users/{user_id}",
}

# 年假规则配置（与生产一致）
LEAVE_RULES = {
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

VALID_LEAVE_TYPES = ["年假", "事假"]
VALID_STATUSES = {
    "approved": "已通过",
    "withdrawn": "已撤回",
}

DB_CONFIG = {
    "path": ":memory:",  # 测试使用内存数据库
}
