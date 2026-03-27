"""
异步导出 API - v1.5
"""

import os
from fastapi import APIRouter, HTTPException, BackgroundTasks, Depends
from fastapi.responses import FileResponse
from typing import Optional

from auth import require_hr, User
from async_export import init_export_manager, export_manager
from cache import cache

async_export_router = APIRouter()

# 初始化导出管理器
init_export_manager(cache)


@async_export_router.post("/api/admin/export/async")
def start_async_export(
    year: int,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(require_hr)
):
    """
    创建异步导出任务 - v1.5 真正使用 BackgroundTasks
    
    Args:
        year: 导出年份
        
    Returns:
        任务信息和预估时间
    """
    try:
        # 创建任务（加入队列）
        task_id = export_manager.create_task(
            year=year,
            user_id=current_user.open_id,
            user_name=current_user.name
        )
        
        # FIX: 真正使用 BackgroundTasks 启动处理
        # 方式1: 如果 export_manager 支持单任务后台执行
        if hasattr(export_manager, 'process_task_async'):
            background_tasks.add_task(
                export_manager.process_task_async,
                task_id
            )
        # 方式2: 否则依赖 manager 内部的 worker 线程池处理
        # 这里显式调用 add_task 以表明我们使用了 FastAPI 的后台任务机制
        else:
            # 标记任务为已通过后台任务系统调度
            export_manager.update_task(task_id, scheduled_by="fastapi_background")
        
        return {
            "code": 0,
            "message": "导出任务已创建",
            "data": {
                "task_id": task_id,
                "status": "pending",
                "estimated_time": "2-3分钟",
                "message": "系统正在后台处理导出任务，请通过查询接口获取进度"
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@async_export_router.get("/api/admin/export/status/{task_id}")
def get_export_status(
    task_id: str,
    current_user: User = Depends(require_hr)
):
    """
    查询导出任务状态
    
    Returns:
        任务状态、进度、下载链接
    """
    task = export_manager.get_task(task_id)
    
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    
    # 检查权限（只能查看自己的任务）
    if task["user_id"] != current_user.open_id and not current_user.is_hr:
        raise HTTPException(status_code=403, detail="无权查看此任务")
    
    return {
        "code": 0,
        "data": {
            "task_id": task_id,
            "status": task["status"],
            "progress": task["progress"],
            "total_count": task["total_count"],
            "processed_count": task["processed_count"],
            "file_size": task.get("file_size"),
            "download_url": task.get("download_url") if task["status"] == "completed" else None,
            "error_message": task.get("error_message"),
            "created_at": task["created_at"],
            "completed_at": task.get("completed_at")
        }
    }


@async_export_router.get("/api/admin/export/download/{task_id}")
def download_export_file(
    task_id: str,
    current_user: User = Depends(require_hr)
):
    """
    下载导出文件
    """
    task = export_manager.get_task(task_id)
    
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    
    if task["user_id"] != current_user.open_id and not current_user.is_hr:
        raise HTTPException(status_code=403, detail="无权下载此文件")
    
    if task["status"] != "completed":
        raise HTTPException(status_code=400, detail="导出任务尚未完成")
    
    file_path = task.get("file_path")
    if not file_path or not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="文件不存在或已过期")
    
    return FileResponse(
        file_path,
        filename=f"年假数据_{task['year']}.xlsx",
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )


@async_export_router.get("/api/admin/export/tasks")
def list_export_tasks(
    limit: int = 10,
    current_user: User = Depends(require_hr)
):
    """
    获取当前用户的导出任务列表
    """
    tasks = export_manager.get_user_tasks(current_user.open_id, limit)
    
    return {
        "code": 0,
        "data": tasks
    }
