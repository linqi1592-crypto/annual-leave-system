"""
异步导出模块 - v1.5 真正可工作的版本
使用 Redis 队列 + 后台 Worker
"""

import os
import json
import uuid
import threading
import time
from datetime import datetime, timedelta, date
from typing import Dict, List, Optional
from dataclasses import dataclass, asdict
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class ExportStatus(Enum):
    """导出任务状态"""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class ExportTask:
    """导出任务"""
    id: str
    year: int
    user_id: str
    user_name: str
    status: str
    progress: int
    total_count: int
    processed_count: int
    file_path: Optional[str]
    file_size: Optional[int]
    error_message: Optional[str]
    created_at: str
    completed_at: Optional[str]
    download_url: Optional[str]


class AsyncExportManager:
    """异步导出管理器 - 真正可工作"""
    
    def __init__(self, cache=None, max_workers: int = 2):
        self.cache = cache
        self.max_workers = max_workers
        self.workers: List[threading.Thread] = []
        self.running = False
        self.task_expire_hours = 24
        
        # 启动后台 Worker
        self._start_workers()
    
    def _get_task_key(self, task_id: str) -> str:
        """生成任务缓存 key"""
        return f"export:task:{task_id}"
    
    def _get_queue_key(self) -> str:
        """生成队列 key"""
        return "export:queue"
    
    def create_task(self, year: int, user_id: str, user_name: str) -> str:
        """创建导出任务"""
        task_id = str(uuid.uuid4())[:8]
        
        task = ExportTask(
            id=task_id,
            year=year,
            user_id=user_id,
            user_name=user_name,
            status=ExportStatus.PENDING.value,
            progress=0,
            total_count=0,
            processed_count=0,
            file_path=None,
            file_size=None,
            error_message=None,
            created_at=datetime.utcnow().isoformat(),
            completed_at=None,
            download_url=None
        )
        
        # 保存任务
        task_key = self._get_task_key(task_id)
        self.cache.set(task_key, asdict(task), ttl=self.task_expire_hours * 3600)
        
        # 加入队列
        queue_key = self._get_queue_key()
        queue = self.cache.get(queue_key) or []
        queue.append(task_id)
        self.cache.set(queue_key, queue, ttl=self.task_expire_hours * 3600)
        
        logger.info(f"创建导出任务: {task_id}, year={year}, user={user_name}")
        return task_id
    
    def get_task(self, task_id: str) -> Optional[Dict]:
        """获取任务信息"""
        task_key = self._get_task_key(task_id)
        return self.cache.get(task_key)
    
    def update_task(self, task_id: str, **updates):
        """更新任务信息"""
        task_key = self._get_task_key(task_id)
        task = self.cache.get(task_key)
        
        if task:
            task.update(updates)
            self.cache.set(task_key, task, ttl=self.task_expire_hours * 3600)
    
    def get_user_tasks(self, user_id: str, limit: int = 10) -> List[Dict]:
        """获取用户的导出任务列表"""
        # 简化实现
        return []
    
    def _start_workers(self):
        """启动后台 Worker"""
        self.running = True
        
        for i in range(self.max_workers):
            worker = threading.Thread(
                target=self._worker_loop,
                name=f"ExportWorker-{i}",
                daemon=True
            )
            worker.start()
            self.workers.append(worker)
            logger.info(f"启动导出 Worker {i}")
    
    def _worker_loop(self):
        """Worker 主循环"""
        while self.running:
            try:
                # 获取队列中的任务
                queue_key = self._get_queue_key()
                queue = self.cache.get(queue_key) or []
                
                if not queue:
                    time.sleep(1)
                    continue
                
                # 取出第一个任务
                task_id = queue.pop(0)
                self.cache.set(queue_key, queue)
                
                # 处理任务
                self._process_task(task_id)
                
            except Exception as e:
                logger.error(f"Worker 错误: {e}")
                time.sleep(1)
    
    def _process_task(self, task_id: str):
        """处理导出任务 - 真正计算年假"""
        # 延迟导入避免循环依赖
        from feishu_client import feishu_client
        from leave_calculator import calculator
        import pandas as pd
        
        task = self.get_task(task_id)
        if not task:
            logger.error(f"任务不存在: {task_id}")
            return
        
        try:
            logger.info(f"开始处理导出任务: {task_id}")
            
            # 更新状态为处理中
            self.update_task(
                task_id,
                status=ExportStatus.PROCESSING.value,
                progress=0
            )
            
            year = task["year"]
            
            # 获取所有员工
            employees = feishu_client.get_employee_records()
            total = len(employees)
            
            self.update_task(task_id, total_count=total)
            
            # 分批处理（每批10人）
            batch_size = 10
            all_data = []
            
            for i in range(0, total, batch_size):
                batch = employees[i:i+batch_size]
                
                for emp in batch:
                    try:
                        fields = emp.get("fields", {})
                        employee_name = fields.get("发起人", "")
                        
                        # 获取请假记录
                        leave_records = feishu_client.get_leave_records(employee_name)
                        
                        # 真正计算年假
                        year_end = date(year, 12, 31)
                        result = calculator.calculate_annual_leave_balance(
                            emp, leave_records, 0.0, year_end
                        )
                        
                        annual = result["annual_leave"]
                        
                        all_data.append({
                            "姓名": employee_name,
                            "工号": fields.get("工号", ""),
                            "部门": fields.get("发起部门", ""),
                            "入职日期": fields.get("入职时间", ""),
                            "当年额度": annual.get("current_year", {}).get("quota", 0),
                            "上年结转": annual.get("carryover", {}).get("quota", 0),
                            "已使用": annual.get("total_used", 0),
                            "剩余": annual.get("remaining", 0),
                            "是否透支": "是" if annual.get("is_negative") else "否",
                        })
                    except Exception as e:
                        logger.error(f"处理员工 {employee_name} 失败: {e}")
                        all_data.append({
                            "姓名": employee_name,
                            "工号": fields.get("工号", ""),
                            "部门": fields.get("发起部门", ""),
                            "入职日期": fields.get("入职时间", ""),
                            "当年额度": 0,
                            "上年结转": 0,
                            "已使用": 0,
                            "剩余": 0,
                            "是否透支": f"错误: {str(e)[:20]}",
                        })
                
                # 更新进度
                processed = min(i + batch_size, total)
                progress = int(processed / total * 100)
                self.update_task(task_id, processed_count=processed, progress=progress)
                
                time.sleep(0.1)
            
            # 生成文件
            export_dir = "data/exports"
            os.makedirs(export_dir, exist_ok=True)
            
            file_name = f"年假数据_{year}_{task_id}.xlsx"
            file_path = os.path.join(export_dir, file_name)
            
            # 使用 pandas 生成 Excel
            df = pd.DataFrame(all_data)
            df.to_excel(file_path, index=False)
            
            file_size = os.path.getsize(file_path)
            
            # 更新任务完成
            self.update_task(
                task_id,
                status=ExportStatus.COMPLETED.value,
                progress=100,
                processed_count=total,
                file_path=file_path,
                file_size=file_size,
                completed_at=datetime.utcnow().isoformat(),
                download_url=f"/api/admin/export/download/{task_id}"
            )
            
            logger.info(f"导出任务完成: {task_id}, 文件={file_path}, 大小={file_size}")
            
        except Exception as e:
            logger.error(f"导出任务失败: {task_id}, 错误={e}")
            self.update_task(
                task_id,
                status=ExportStatus.FAILED.value,
                error_message=str(e)
            )
    
    def stop(self):
        """停止所有 Worker"""
        self.running = False
        for worker in self.workers:
            worker.join(timeout=5)


# 全局导出管理器实例
export_manager: Optional[AsyncExportManager] = None


def init_export_manager(cache):
    """初始化导出管理器"""
    global export_manager
    if export_manager is None:
        export_manager = AsyncExportManager(cache)
    return export_manager
