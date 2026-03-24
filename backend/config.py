import os
import logging

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 飞书配置（全部从环境变量读取，无默认值）
FEISHU_CONFIG = {
    "app_id": os.getenv("FEISHU_APP_ID"),
    "app_secret": os.getenv("FEISHU_APP_SECRET"),
    "app_token": os.getenv("FEISHU_APP_TOKEN"),
    "encrypt_key": os.getenv("FEISHU_ENCRYPT_KEY"),
    "verification_token": os.getenv("FEISHU_VERIFICATION_TOKEN"),
}

# 验证必要配置
if not FEISHU_CONFIG["app_id"]:
    logger.error("FEISHU_APP_ID 未配置，请检查 .env 文件")
    raise ValueError("FEISHU_APP_ID 是必填项")
if not FEISHU_CONFIG["app_secret"]:
    logger.error("FEISHU_APP_SECRET 未配置，请检查 .env 文件")
    raise ValueError("FEISHU_APP_SECRET 是必填项")
if not FEISHU_CONFIG["app_token"]:
    logger.error("FEISHU_APP_TOKEN 未配置，请检查 .env 文件")
    raise ValueError("FEISHU_APP_TOKEN 是必填项")

# CORS 配置
CORS_ORIGINS = os.getenv("CORS_ORIGINS", "*")
if CORS_ORIGINS == "*":
    CORS_ALLOW_ALL = True
    CORS_ALLOWED_ORIGINS = ["*"]
else:
    CORS_ALLOW_ALL = False
    CORS_ALLOWED_ORIGINS = [origin.strip() for origin in CORS_ORIGINS.split(",")]

# 时区配置
TIMEZONE = os.getenv("TIMEZONE", "Asia/Shanghai")

# 多维表格配置
BITABLE_CONFIG = {
    "employee_table_id": os.getenv("EMPLOYEE_TABLE_ID", "tbls5vXl99F0fFRn"),
    "leave_table_id": os.getenv("LEAVE_TABLE_ID", "tbl5vlfwyRzhNIhb"),
}

# API 端点
FEISHU_API = {
    "base_url": "https://open.feishu.cn/open-apis",
    "auth_url": "/auth/v3/tenant_access_token/internal",
    "bitable_records": "/bitable/v1/apps/{app_token}/tables/{table_id}/records",
    "user_info": "/contact/v3/users/{user_id}",
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
    "path": os.getenv("DB_PATH", "data/leave_adjustments.db"),
}
