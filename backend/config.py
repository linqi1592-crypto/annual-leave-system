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

# JWT 配置
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "")
JWT_CONFIG = {
    "secret_key": JWT_SECRET_KEY or "your-secret-key-change-in-production",
    "algorithm": "HS256",
    "access_token_expire_minutes": int(os.getenv("JWT_EXPIRE_MINUTES", "480")),  # 默认8小时
}

# P1: JWT 默认密钥安全检查
if not JWT_SECRET_KEY:
    logger.error("=" * 60)
    logger.error("严重安全警告: JWT_SECRET_KEY 未配置!")
    logger.error("请设置环境变量 JWT_SECRET_KEY，使用强随机字符串")
    logger.error("示例: export JWT_SECRET_KEY=$(openssl rand -hex 32)")
    logger.error("=" * 60)
    raise ValueError("JWT_SECRET_KEY 是必填项，拒绝启动")

# CORS 配置
CORS_ORIGINS = os.getenv("CORS_ORIGINS", "")
if not CORS_ORIGINS:
    # 飞书工作台应用建议限制为飞书域名
    CORS_ALLOW_ALL = False
    CORS_ALLOWED_ORIGINS = [
        "https://www.feishu.cn",
        "https://open.feishu.cn",
        "https://feishu.cn"
    ]
    logger.warning("CORS 未配置，已限制为飞书域名。如需开发调试，请设置 CORS_ORIGINS=*")
elif CORS_ORIGINS == "*":
    CORS_ALLOW_ALL = True
    CORS_ALLOWED_ORIGINS = ["*"]
    logger.warning("CORS 设置为允许所有来源，生产环境建议限制域名")
else:
    CORS_ALLOW_ALL = False
    CORS_ALLOWED_ORIGINS = [origin.strip() for origin in CORS_ORIGINS.split(",")]
    logger.info(f"CORS 允许的域名: {CORS_ALLOWED_ORIGINS}")

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
    "authen_access_token": "/authen/v1/access_token",  # 免登获取 user_access_token
    "authen_user_info": "/authen/v1/user_info",  # 获取用户信息
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

# 缓存配置
CACHE_TYPE = os.getenv("CACHE_TYPE", "memory")  # memory 或 redis
CACHE_REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

# 验证缓存配置
if CACHE_TYPE == "redis" and not CACHE_REDIS_URL:
    logger.warning("CACHE_TYPE=redis 但 REDIS_URL 未配置，将回退到内存缓存")

# HR 用户配置（简单配置，生产环境建议用飞书角色或数据库配置）
HR_USERS = os.getenv("HR_USERS", "")  # 逗号分隔的 open_id 列表
