"""
飞书 API 客户端
用于获取 token 和读取多维表格数据
"""

import requests
import time
from typing import Optional, List, Dict, Any
from config import FEISHU_CONFIG, FEISHU_API


class FeishuClient:
    """飞书 API 客户端"""
    
    def __init__(self):
        self.app_id = FEISHU_CONFIG["app_id"]
        self.app_secret = FEISHU_CONFIG["app_secret"]
        self.app_token = FEISHU_CONFIG["app_token"]
        self.base_url = FEISHU_API["base_url"]
        
        self._tenant_token: Optional[str] = None
        self._token_expire_time: float = 0
    
    def _get_tenant_access_token(self) -> str:
        """获取 tenant_access_token（带缓存）"""
        # 检查 token 是否过期（提前5分钟刷新）
        if self._tenant_token and time.time() < self._token_expire_time - 300:
            return self._tenant_token
        
        url = f"{self.base_url}{FEISHU_API['auth_url']}"
        payload = {
            "app_id": self.app_id,
            "app_secret": self.app_secret
        }
        
        try:
            response = requests.post(url, json=payload, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            if data.get("code") != 0:
                raise Exception(f"获取 token 失败: {data.get('msg')}")
            
            self._tenant_token = data["tenant_access_token"]
            # token 有效期7200秒，这里记录过期时间
            self._token_expire_time = time.time() + data.get("expire", 7200)
            
            return self._tenant_token
            
        except Exception as e:
            raise Exception(f"获取 tenant_access_token 失败: {str(e)}")
    
    def _get_headers(self) -> Dict[str, str]:
        """获取请求头"""
        token = self._get_tenant_access_token()
        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
    
    def get_bitable_records(
        self, 
        table_id: str, 
        filter_formula: Optional[str] = None,
        page_size: int = 500
    ) -> List[Dict[str, Any]]:
        """
        获取多维表格记录
        
        Args:
            table_id: 表格 ID
            filter_formula: 筛选条件（可选）
            page_size: 每页数量
            
        Returns:
            记录列表
        """
        url = f"{self.base_url}/bitable/v1/apps/{self.app_token}/tables/{table_id}/records"
        headers = self._get_headers()
        
        all_records = []
        page_token = None
        
        while True:
            params = {"page_size": page_size}
            if page_token:
                params["page_token"] = page_token
            if filter_formula:
                params["filter"] = filter_formula
            
            try:
                response = requests.get(url, headers=headers, params=params, timeout=30)
                response.raise_for_status()
                data = response.json()
                
                if data.get("code") != 0:
                    raise Exception(f"获取表格数据失败: {data.get('msg')}")
                
                items = data.get("data", {}).get("items", [])
                all_records.extend(items)
                
                # 检查是否有下一页
                page_token = data.get("data", {}).get("page_token")
                if not page_token or not items:
                    break
                    
            except Exception as e:
                raise Exception(f"读取多维表格失败: {str(e)}")
        
        return all_records
    
    def get_employee_records(self) -> List[Dict[str, Any]]:
        """获取员工信息表记录"""
        from config import BITABLE_CONFIG
        return self.get_bitable_records(BITABLE_CONFIG["employee_table_id"])
    
    def get_leave_records(self, employee_name: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        获取请假记录表记录
        
        Args:
            employee_name: 按员工姓名筛选（可选）
        """
        from config import BITABLE_CONFIG
        
        filter_formula = None
        if employee_name:
            # 飞书多维表格筛选语法
            filter_formula = f'CurrentValue.[发起人] = "{employee_name}"'
        
        return self.get_bitable_records(BITABLE_CONFIG["leave_table_id"], filter_formula)


# 全局客户端实例
feishu_client = FeishuClient()


if __name__ == "__main__":
    # 测试
    try:
        print("测试获取 tenant_access_token...")
        token = feishu_client._get_tenant_access_token()
        print(f"✅ 获取成功: {token[:20]}...")
        
        print("\n测试读取员工信息表...")
        employees = feishu_client.get_employee_records()
        print(f"✅ 读取成功: 共 {len(employees)} 条记录")
        if employees:
            print(f"示例: {employees[0].get('fields', {}).get('发起人', 'N/A')}")
        
        print("\n测试读取请假记录表...")
        leaves = feishu_client.get_leave_records()
        print(f"✅ 读取成功: 共 {len(leaves)} 条记录")
        
    except Exception as e:
        print(f"❌ 错误: {e}")
