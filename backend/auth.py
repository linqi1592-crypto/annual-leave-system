"""
认证模块 - 飞书免登 + JWT
v1.3 新增
"""

import requests
import jwt
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from fastapi import HTTPException, Header, Depends
from pydantic import BaseModel
import logging

from config import FEISHU_CONFIG, FEISHU_API, JWT_CONFIG, HR_USERS, logger as config_logger
from feishu_client import feishu_client

logger = logging.getLogger(__name__)


class User(BaseModel):
    """当前用户模型"""
    open_id: str
    name: str
    employee_id: Optional[str] = None  # 飞书记录ID
    employee_name: Optional[str] = None  # 员工姓名（匹配员工表的"发起人"）
    is_hr: bool = False


class LoginRequest(BaseModel):
    """登录请求"""
    auth_code: str


class LoginResponse(BaseModel):
    """登录响应"""
    open_id: str
    name: str
    employee_id: Optional[str]
    employee_name: Optional[str]
    is_hr: bool
    token: str


class AuthManager:
    """认证管理器"""
    
    def __init__(self):
        self.app_id = FEISHU_CONFIG["app_id"]
        self.app_secret = FEISHU_CONFIG["app_secret"]
        self.jwt_secret = JWT_CONFIG["secret_key"]
        self.jwt_algorithm = JWT_CONFIG["algorithm"]
        self.token_expire_minutes = JWT_CONFIG["access_token_expire_minutes"]
        self.hr_users = set(HR_USERS.split(",")) if HR_USERS else set()
    
    def get_user_access_token(self, auth_code: str) -> str:
        """
        用 auth_code 换取 user_access_token
        """
        url = f"{FEISHU_API['base_url']}{FEISHU_API['authen_access_token']}"
        
        # 先获取 tenant_access_token
        tenant_token = feishu_client._get_tenant_access_token()
        
        headers = {
            "Authorization": f"Bearer {tenant_token}",
            "Content-Type": "application/json"
        }
        
        data = {
            "grant_type": "authorization_code",
            "code": auth_code
        }
        
        try:
            logger.info("正在用 auth_code 换取 user_access_token...")
            response = requests.post(url, headers=headers, json=data, timeout=10)
            response.raise_for_status()
            result = response.json()
            
            if result.get("code") != 0:
                logger.error(f"换取 user_access_token 失败: {result.get('msg')}")
                raise HTTPException(status_code=401, detail=f"认证失败: {result.get('msg')}")
            
            user_access_token = result["data"]["access_token"]
            logger.info("user_access_token 获取成功")
            return user_access_token
            
        except requests.exceptions.RequestException as e:
            logger.error(f"请求 user_access_token 失败: {str(e)}")
            raise HTTPException(status_code=500, detail=f"认证服务异常: {str(e)}")
    
    def get_user_info(self, user_access_token: str) -> Dict[str, Any]:
        """
        用 user_access_token 获取用户信息
        """
        url = f"{FEISHU_API['base_url']}{FEISHU_API['authen_user_info']}"
        
        headers = {
            "Authorization": f"Bearer {user_access_token}"
        }
        
        try:
            logger.info("正在获取用户信息...")
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()
            result = response.json()
            
            if result.get("code") != 0:
                logger.error(f"获取用户信息失败: {result.get('msg')}")
                raise HTTPException(status_code=401, detail=f"获取用户信息失败: {result.get('msg')}")
            
            user_data = result["data"]
            logger.info(f"用户信息获取成功: {user_data.get('name')}")
            return user_data
            
        except requests.exceptions.RequestException as e:
            logger.error(f"请求用户信息失败: {str(e)}")
            raise HTTPException(status_code=500, detail=f"认证服务异常: {str(e)}")
    
    def match_employee(self, open_id: str, name: str) -> Optional[Dict[str, str]]:
        """
        根据 open_id 匹配员工表
        """
        try:
            employees = feishu_client.get_employee_records()
            
            for emp in employees:
                fields = emp.get("fields", {})
                # 优先匹配 open_id
                emp_open_id = fields.get("飞书Open ID", "")
                if emp_open_id == open_id:
                    return {
                        "employee_id": emp.get("record_id"),
                        "employee_name": fields.get("发起人", "")
                    }
            
            # 如果没有匹配到 open_id，尝试匹配姓名（备选方案）
            for emp in employees:
                fields = emp.get("fields", {})
                emp_name = fields.get("发起人", "")
                if emp_name == name:
                    logger.warning(f"通过姓名匹配到员工: {name}，建议补充 open_id 字段")
                    return {
                        "employee_id": emp.get("record_id"),
                        "employee_name": emp_name
                    }
            
            logger.warning(f"未找到匹配的员工: open_id={open_id}, name={name}")
            return None
            
        except Exception as e:
            logger.error(f"匹配员工失败: {str(e)}")
            return None
    
    def check_is_hr(self, open_id: str) -> bool:
        """
        检查用户是否是 HR
        """
        return open_id in self.hr_users
    
    def create_jwt_token(self, user: User) -> str:
        """
        创建 JWT token
        """
        expire = datetime.utcnow() + timedelta(minutes=self.token_expire_minutes)
        
        payload = {
            "open_id": user.open_id,
            "name": user.name,
            "employee_id": user.employee_id,
            "employee_name": user.employee_name,
            "is_hr": user.is_hr,
            "exp": expire,
            "iat": datetime.utcnow()
        }
        
        token = jwt.encode(payload, self.jwt_secret, algorithm=self.jwt_algorithm)
        return token
    
    def decode_jwt_token(self, token: str) -> User:
        """
        解码 JWT token
        """
        try:
            payload = jwt.decode(token, self.jwt_secret, algorithms=[self.jwt_algorithm])
            return User(
                open_id=payload["open_id"],
                name=payload["name"],
                employee_id=payload.get("employee_id"),
                employee_name=payload.get("employee_name"),
                is_hr=payload.get("is_hr", False)
            )
        except jwt.ExpiredSignatureError:
            raise HTTPException(status_code=401, detail="Token 已过期")
        except jwt.InvalidTokenError:
            raise HTTPException(status_code=401, detail="无效的 Token")
    
    def login(self, auth_code: str) -> LoginResponse:
        """
        完整的登录流程
        """
        # 1. 获取 user_access_token
        user_access_token = self.get_user_access_token(auth_code)
        
        # 2. 获取用户信息
        user_info = self.get_user_info(user_access_token)
        
        open_id = user_info.get("open_id")
        name = user_info.get("name", "")
        
        # 3. 匹配员工
        employee_match = self.match_employee(open_id, name)
        employee_id = employee_match.get("employee_id") if employee_match else None
        employee_name = employee_match.get("employee_name") if employee_match else None
        
        # 4. 检查 HR 权限
        is_hr = self.check_is_hr(open_id)
        
        # 5. 创建用户对象
        user = User(
            open_id=open_id,
            name=name,
            employee_id=employee_id,
            employee_name=employee_name,
            is_hr=is_hr
        )
        
        # 6. 创建 JWT token
        token = self.create_jwt_token(user)
        
        logger.info(f"用户登录成功: {name} ({open_id}), HR={is_hr}")
        
        return LoginResponse(
            open_id=open_id,
            name=name,
            employee_id=employee_id,
            employee_name=employee_name,
            is_hr=is_hr,
            token=token
        )


# 全局认证管理器实例
auth_manager = AuthManager()


# ==================== FastAPI 依赖 ====================

async def get_current_user(authorization: Optional[str] = Header(None)) -> User:
    """
    获取当前登录用户（JWT token 验证）
    """
    if not authorization:
        raise HTTPException(status_code=401, detail="缺少认证信息")
    
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="认证格式错误")
    
    token = authorization.replace("Bearer ", "")
    return auth_manager.decode_jwt_token(token)


async def require_hr(current_user: User = Depends(get_current_user)) -> User:
    """
    要求 HR 权限
    """
    if not current_user.is_hr:
        logger.warning(f"用户 {current_user.name} 尝试访问 HR 接口，但无权限")
        raise HTTPException(status_code=403, detail="需要 HR 权限")
    return current_user


async def require_employee_or_hr(
    employee_id: str,
    current_user: User = Depends(get_current_user)
) -> User:
    """
    要求只能查看自己的数据，或者是 HR
    """
    if current_user.is_hr:
        return current_user
    
    if current_user.employee_id != employee_id:
        logger.warning(f"用户 {current_user.name} 尝试查看他人数据: {employee_id}")
        raise HTTPException(status_code=403, detail="只能查看自己的年假信息")
    
    return current_user


# ==================== API 路由 ====================

from fastapi import APIRouter

auth_router = APIRouter()

@auth_router.post("/api/auth/login", response_model=LoginResponse)
async def login(request: LoginRequest):
    """
    飞书免登登录
    
    前端调用 tt.requestAuthCode() 获取 auth_code 后，调用此接口完成登录
    """
    return auth_manager.login(request.auth_code)


@auth_router.get("/api/auth/me")
async def get_me(current_user: User = Depends(get_current_user)):
    """
    获取当前登录用户信息
    """
    return {
        "code": 0,
        "data": {
            "open_id": current_user.open_id,
            "name": current_user.name,
            "employee_id": current_user.employee_id,
            "employee_name": current_user.employee_name,
            "is_hr": current_user.is_hr
        }
    }
