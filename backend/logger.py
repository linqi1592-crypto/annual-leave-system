"""
日志监控模块 - v1.4 稳定性优化
支持分级日志、结构化输出、飞书告警
"""

import logging
import json
import os
import sys
from datetime import datetime
from typing import Dict, Any, Optional
from enum import Enum
from logging.handlers import RotatingFileHandler, TimedRotatingFileHandler
import traceback


class LogLevel(Enum):
    """日志级别"""
    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class StructuredLogFormatter(logging.Formatter):
    """结构化日志格式化器 - 输出 JSON"""
    
    def format(self, record: logging.LogRecord) -> str:
        log_data = {
            "timestamp": datetime.utcnow().isoformat(),
            "level": record.levelname.lower(),
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }
        
        # 添加额外字段
        if hasattr(record, 'event'):
            log_data['event'] = record.event
        if hasattr(record, 'user_id'):
            log_data['user_id'] = record.user_id
        if hasattr(record, 'employee_id'):
            log_data['employee_id'] = record.employee_id
        if hasattr(record, 'duration_ms'):
            log_data['duration_ms'] = record.duration_ms
        if hasattr(record, 'cache_hit'):
            log_data['cache_hit'] = record.cache_hit
        
        # 添加异常信息
        if record.exc_info:
            log_data['exception'] = {
                'type': record.exc_info[0].__name__ if record.exc_info[0] else None,
                'message': str(record.exc_info[1]) if record.exc_info[1] else None,
                'traceback': traceback.format_exception(*record.exc_info)
            }
        
        return json.dumps(log_data, ensure_ascii=False, default=str)


class TextLogFormatter(logging.Formatter):
    """文本日志格式化器 - 人类可读"""
    
    def format(self, record: logging.LogRecord) -> str:
        # 基础格式
        base = f"{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} [{record.levelname}] {record.name}: {record.getMessage()}"
        
        # 添加上下文
        extras = []
        if hasattr(record, 'event'):
            extras.append(f"event={record.event}")
        if hasattr(record, 'user_id'):
            extras.append(f"user={record.user_id}")
        if hasattr(record, 'duration_ms'):
            extras.append(f"duration={record.duration_ms}ms")
        
        if extras:
            base += f" ({', '.join(extras)})"
        
        # 添加异常
        if record.exc_info:
            base += "\n" + "".join(traceback.format_exception(*record.exc_info))
        
        return base


class AlertManager:
    """告警管理器 - 飞书机器人通知"""
    
    def __init__(self, webhook_url: Optional[str] = None):
        self.webhook_url = webhook_url or os.getenv('FEISHU_ALERT_WEBHOOK')
        self.alert_cooldown = {}  # 冷却时间，避免重复告警
        self.cooldown_seconds = 300  # 5分钟冷却
    
    def should_alert(self, alert_key: str) -> bool:
        """检查是否应该发送告警（冷却机制）"""
        import time
        now = time.time()
        last_alert = self.alert_cooldown.get(alert_key, 0)
        
        if now - last_alert > self.cooldown_seconds:
            self.alert_cooldown[alert_key] = now
            return True
        return False
    
    def send_alert(self, level: str, title: str, message: str, details: Dict = None):
        """发送飞书告警"""
        if not self.webhook_url:
            return
        
        alert_key = f"{level}:{title}"
        if not self.should_alert(alert_key):
            return
        
        # 构建飞书消息
        color_map = {
            'error': 'red',
            'warning': 'orange',
            'critical': 'red'
        }
        
        card = {
            "msg_type": "interactive",
            "card": {
                "config": {"wide_screen_mode": True},
                "header": {
                    "title": {"tag": "plain_text", "content": f"🚨 {title}"},
                    "template": color_map.get(level, "blue")
                },
                "elements": [
                    {
                        "tag": "div",
                        "text": {"tag": "lark_md", "content": message}
                    }
                ]
            }
        }
        
        if details:
            detail_text = "\n".join([f"**{k}**: {v}" for k, v in details.items()])
            card["card"]["elements"].append({
                "tag": "div",
                "text": {"tag": "lark_md", "content": detail_text}
            })
        
        # 异步发送（不阻塞主流程）
        import threading
        threading.Thread(target=self._send_webhook, args=(card,), daemon=True).start()
    
    def _send_webhook(self, payload: Dict):
        """实际发送 webhook"""
        try:
            import requests
            response = requests.post(
                self.webhook_url,
                json=payload,
                timeout=5
            )
            response.raise_for_status()
        except Exception as e:
            logging.error(f"发送告警失败: {e}")


class MonitoredLogger:
    """监控日志器 - 自动告警"""
    
    def __init__(self, name: str):
        self.logger = logging.getLogger(name)
        self.alert_manager = AlertManager()
    
    def _log(self, level: int, msg: str, *args, **kwargs):
        """内部日志方法"""
        extra = kwargs.pop('extra', {})
        
        # 记录日志
        self.logger.log(level, msg, *args, extra=extra, **kwargs)
        
        # 错误级别触发告警
        if level >= logging.ERROR:
            alert_key = extra.get('event', 'unknown')
            self.alert_manager.send_alert(
                level='error' if level == logging.ERROR else 'critical',
                title=f"系统告警: {alert_key}",
                message=msg,
                details={
                    '时间': datetime.utcnow().isoformat(),
                    '模块': extra.get('module', 'unknown'),
                    '用户': extra.get('user_id', 'system')
                }
            )
    
    def debug(self, msg: str, *args, **kwargs):
        self._log(logging.DEBUG, msg, *args, **kwargs)
    
    def info(self, msg: str, *args, **kwargs):
        self._log(logging.INFO, msg, *args, **kwargs)
    
    def warning(self, msg: str, *args, **kwargs):
        self._log(logging.WARNING, msg, *args, **kwargs)
    
    def error(self, msg: str, *args, **kwargs):
        self._log(logging.ERROR, msg, *args, **kwargs)
    
    def critical(self, msg: str, *args, **kwargs):
        self._log(logging.CRITICAL, msg, *args, **kwargs)
    
    def api_call(self, endpoint: str, user_id: str, duration_ms: int, success: bool):
        """API 调用日志"""
        level = logging.INFO if success else logging.ERROR
        self._log(level, f"API调用: {endpoint}", extra={
            'event': 'api_call',
            'endpoint': endpoint,
            'user_id': user_id,
            'duration_ms': duration_ms,
            'success': success
        })
    
    def cache_access(self, key: str, hit: bool, duration_ms: int):
        """缓存访问日志"""
        self._log(logging.DEBUG, f"缓存{'命中' if hit else '未命中'}: {key}", extra={
            'event': 'cache_access',
            'cache_key': key,
            'cache_hit': hit,
            'duration_ms': duration_ms
        })
    
    def business_event(self, event: str, user_id: str, details: Dict):
        """业务事件日志"""
        self._log(logging.INFO, f"业务事件: {event}", extra={
            'event': event,
            'user_id': user_id,
            **details
        })


def setup_logging(
    log_level: str = "INFO",
    log_dir: str = "logs",
    enable_file: bool = True,
    enable_console: bool = True,
    enable_json: bool = True
) -> logging.Logger:
    """
    配置日志系统
    
    Args:
        log_level: 日志级别 DEBUG/INFO/WARNING/ERROR
        log_dir: 日志目录
        enable_file: 是否输出到文件
        enable_console: 是否输出到控制台
        enable_json: 是否使用 JSON 格式
    
    Returns:
        根日志器
    """
    # 创建日志目录
    os.makedirs(log_dir, exist_ok=True)
    
    # 根日志器
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, log_level.upper()))
    
    # 清除已有处理器
    root_logger.handlers = []
    
    # 格式器
    json_formatter = StructuredLogFormatter()
    text_formatter = TextLogFormatter(
        fmt='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # 控制台输出（文本格式，人类可读）
    if enable_console:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.DEBUG)
        console_handler.setFormatter(text_formatter)
        root_logger.addHandler(console_handler)
    
    # 文件输出（JSON格式，便于分析）
    if enable_file:
        # 主日志文件（轮转）
        main_handler = TimedRotatingFileHandler(
            filename=os.path.join(log_dir, "app.log"),
            when='midnight',
            interval=1,
            backupCount=30,
            encoding='utf-8'
        )
        main_handler.setLevel(logging.INFO)
        main_handler.setFormatter(json_formatter if enable_json else text_formatter)
        root_logger.addHandler(main_handler)
        
        # 错误日志（单独文件）
        error_handler = RotatingFileHandler(
            filename=os.path.join(log_dir, "error.log"),
            maxBytes=10 * 1024 * 1024,  # 10MB
            backupCount=10,
            encoding='utf-8'
        )
        error_handler.setLevel(logging.ERROR)
        error_handler.setFormatter(json_formatter if enable_json else text_formatter)
        root_logger.addHandler(error_handler)
        
        # API 调用日志
        api_handler = TimedRotatingFileHandler(
            filename=os.path.join(log_dir, "api.log"),
            when='midnight',
            interval=1,
            backupCount=7,
            encoding='utf-8'
        )
        api_handler.setLevel(logging.INFO)
        api_handler.setFormatter(json_formatter)
        # 添加过滤器，只记录 API 相关日志
        api_filter = logging.Filter()
        api_filter.filter = lambda record: getattr(record, 'event', '') == 'api_call'
        api_handler.addFilter(api_filter)
        root_logger.addHandler(api_handler)
    
    return root_logger


# 全局日志器实例
logger = MonitoredLogger("annual_leave")


# ==================== 使用示例 ====================

if __name__ == "__main__":
    # 初始化日志
    setup_logging(log_level="DEBUG", log_dir="logs")
    
    # 测试日志
    logger.info("系统启动", extra={'event': 'startup'})
    
    logger.api_call(
        endpoint="/api/leave/balance",
        user_id="user_001",
        duration_ms=50,
        success=True
    )
    
    logger.cache_access(
        key="balance:user_001:2026",
        hit=True,
        duration_ms=2
    )
    
    logger.business_event(
        event="create_adjustment",
        user_id="hr_001",
        details={'employee': '张三', 'amount': 1.5}
    )
    
    try:
        raise ValueError("测试异常")
    except:
        logger.error("发生错误", exc_info=True, extra={'event': 'error_test'})
    
    print("日志测试完成，请查看 logs/ 目录")
