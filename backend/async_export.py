"""
异步导出模块 - v1.5 大文件导出支持
使用 Redis 队列 + 后台 Worker
"""

import os
import json
import uuid
import threading
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Callable
from dataclasses import dataclass, asdict
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class ExportStatus(Enum):
    """导出任务状态"""
    PENDING = "pending"         # 等待中
    PROCESSING = "processing"   # 处理中
    COMPLETED = "completed"     # 完成
    FAILED = "failed"           # 失败
    EXPIRED = "expired"         # 已过期


@dataclass
class ExportTask:
    """导出任务"""
    id: str
    year: int
    user_id: str
    user_name: str
    status: str
    progress: int              # 0-100
    total_count: int           # 总员工数
    processed_count: int       # 已处理数
    file_path: Optional[str]   # 导出文件路径
    file_size: Optional[int]   # 文件大小（字节）
    error_message: Optional[str]
    created_at: str
    completed_at: Optional[str]
    download_url: Optional[str]


class AsyncExportManager:
    """异步导出管理器"""
    
    def __init__(self, cache=None, max_workers: int = 2):
        self.cache = cache
        self.max_workers = max_workers
        self.workers: List[threading.Thread] = []
        self.running = False
        self.task_expire_hours = 24  # 任务24小时后过期
        
        # 启动后台 Worker
        self._start_workers()
    
    def _get_task_key(self, task_id: str) -> str:
        """生成任务缓存 key"""
        return f"export:task:{task_id}"
    
    def _get_queue_key(self) -> str:
        """生成队列 key"""
        return "export:queue"
    
    def create_task(self, year: int, user_id: str, user_name: str) -> str:
        """
        创建导出任务
        
        Returns:
            任务 ID
        """
        task_id = str(uuid.uuid4())[:8]  # 短ID便于使用
        
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
        # 简单实现：扫描所有任务（生产环境可用索引优化）
        tasks = []
        # 这里简化处理，实际可以用 Redis 的 scan 或维护用户任务列表
        return tasks
    
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
                    time.sleep(1)  # 没有任务，等待1秒
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
        """处理导出任务"""
        from export import generate_export_data, generate_csv, generate_excel
        from feishu_client import feishu_client
        from leave_calculator import calculator
        from adjustment_db import db
        from config import TIMEZONE
        from datetime import date
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
                        
                        # 计算年假（复用现有逻辑）
                        previous_year = year - 1
                        # 简化处理，实际需要完整计算逻辑
                        
                        all_data.append({
                            "姓名": employee_name,
                            "工号": fields.get("工号", ""),
                            "年份": year,
                            # ... 其他字段
                        })
                    except Exception as e:
                        logger.error(f"处理员工 {employee_name} 失败: {e}")
                
                # 更新进度
                processed = min(i + batch_size, total)
                progress = int(processed / total * 100)
                self.update_task(task_id, processed_count=processed, progress=progress)
                
                # 避免占用过多CPU
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


# ==================== 使用示例 ====================

if __name__ == "__main__":
    print("测试异步导出模块...")
    
    from cache import MemoryCache
    
    cache = MemoryCache()
    manager = AsyncExportManager(cache, max_workers=1)
    
    # 创建任务
    task_id = manager.create_task(2026, "user_001", "HR小王")
    print(f"✓ 创建任务: {task_id}")
    
    # 查询任务
    task = manager.get_task(task_id)
    print(f"✓ 任务状态: {task['status']}")
    
    # 等待处理（实际会后台处理）
    time.sleep(2)
    
    # 查询进度
    task = manager.get_task(task_id)
    print(f"✓ 当前进度: {task['progress']}%")
    
    manager.stop()
    print("\n✓ 测试完成")
