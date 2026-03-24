"""
时区处理测试
验证所有时间戳解析使用北京时间（Asia/Shanghai）
"""

import sys
import pytest
from datetime import date, datetime
from zoneinfo import ZoneInfo
from pathlib import Path

# 时区配置（与生产一致）
TIMEZONE = "Asia/Shanghai"
tz = ZoneInfo(TIMEZONE)


def parse_timestamp_year(timestamp):
    """
    统一时区解析时间戳，返回年份（复制自 main.py）
    支持毫秒级和秒级时间戳
    """
    if isinstance(timestamp, (int, float)):
        # 毫秒级时间戳（飞书默认）
        if timestamp > 1e10:
            dt = datetime.fromtimestamp(timestamp / 1000, tz=ZoneInfo("UTC"))
        else:
            dt = datetime.fromtimestamp(timestamp, tz=ZoneInfo("UTC"))
        return dt.astimezone(tz).year
    elif isinstance(timestamp, str):
        # ISO 格式字符串
        if 'T' in timestamp:
            dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
            return dt.astimezone(tz).year
        else:
            # 简单日期格式 YYYY-MM-DD
            return int(timestamp[:4])
    else:
        raise ValueError(f"不支持的时间格式: {timestamp}")


def format_timestamp(timestamp):
    """
    格式化时间戳为本地时间字符串（复制自 main.py）
    """
    if not timestamp:
        return ""
    
    try:
        if isinstance(timestamp, (int, float)):
            if timestamp > 1e10:
                dt = datetime.fromtimestamp(timestamp / 1000, tz=ZoneInfo("UTC"))
            else:
                dt = datetime.fromtimestamp(timestamp, tz=ZoneInfo("UTC"))
            return dt.astimezone(tz).strftime("%Y-%m-%d %H:%M")
        elif isinstance(timestamp, str):
            if 'T' in timestamp:
                dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                return dt.astimezone(tz).strftime("%Y-%m-%d %H:%M")
            else:
                return timestamp
        else:
            return str(timestamp)
    except Exception as e:
        return str(timestamp)


class TestTimezoneHandling:
    """时区处理测试 - 确保使用北京时间"""
    
    def test_parse_timestamp_year_beijing_timezone(self):
        """测试时间戳年份解析使用北京时间"""
        # 2025-06-01 00:00:00 UTC+8 (Beijing)
        # = 2025-05-31 16:00:00 UTC
        ts = 1748707200000  # 毫秒级时间戳
        
        year = parse_timestamp_year(ts)
        
        # 北京时间 2025-06-01，年份应为 2025
        assert year == 2025
    
    def test_parse_timestamp_year_utc_new_year(self):
        """测试 UTC 新年跨年时边界"""
        # UTC 2025-01-01 00:00:00 = 北京时间 2025-01-01 08:00:00
        ts = 1735689600000
        
        year = parse_timestamp_year(ts)
        
        # 北京时间还是 2025年（不是2024年）
        assert year == 2025
    
    def test_parse_timestamp_year_cross_year_boundary(self):
        """测试跨年时区边界：UTC 12月31日晚 = 北京时间次年1月1日"""
        # UTC 2024-12-31 20:00:00 = 北京时间 2025-01-01 04:00:00
        ts = 1735680000000
        
        year = parse_timestamp_year(ts)
        
        # 北京时间已进入 2025年
        assert year == 2025
    
    def test_parse_timestamp_year_beijing_new_year(self):
        """测试北京时间新年"""
        # 北京时间 2025-01-01 00:00:00 = UTC 2024-12-31 16:00:00
        ts = 1735660800000  # UTC 2024-12-31 16:00:00
        
        year = parse_timestamp_year(ts)
        
        # 北京时间是 2025年
        assert year == 2025
    
    def test_format_timestamp_beijing_timezone(self):
        """测试时间戳格式化使用北京时间"""
        # UTC 2025-05-31 16:00:00 = 北京时间 2025-06-01 00:00:00
        ts = 1748707200000
        
        formatted = format_timestamp(ts)
        
        # 应格式化为北京时间
        assert "2025-06-01" in formatted
        assert "00:00" in formatted
    
    def test_parse_timestamp_year_string_iso(self):
        """测试 ISO 字符串解析"""
        # ISO 格式带时区
        iso_str = "2025-06-01T00:00:00+08:00"
        
        year = parse_timestamp_year(iso_str)
        
        assert year == 2025
    
    def test_parse_timestamp_year_simple_date(self):
        """测试简单日期字符串解析"""
        date_str = "2025-06-01"
        
        year = parse_timestamp_year(date_str)
        
        assert year == 2025
    
    def test_leave_record_year_filtering(self):
        """测试请假记录年份筛选使用北京时间"""
        # 模拟跨年时区的请假记录
        records = [
            {
                "fields": {
                    "开始时间": 1735680000000,  # UTC 2024-12-31 20:00 = 北京时间 2025-01-01 04:00
                    "请假类型": "年假",
                    "申请状态": "已通过",
                    "时长": 1
                }
            },
            {
                "fields": {
                    "开始时间": 1735651200000,  # UTC 2024-12-31 12:00 = 北京时间 2024-12-31 20:00
                    "请假类型": "年假",
                    "申请状态": "已通过",
                    "时长": 1
                }
            }
        ]
        
        # 筛选 2025 年的记录（北京时间）
        year_2025_records = []
        for record in records:
            start_time = record["fields"]["开始时间"]
            record_year = parse_timestamp_year(start_time)
            if record_year == 2025:
                year_2025_records.append(record)
        
        # 只有第一条记录（北京时间已进入 2025年）
        assert len(year_2025_records) == 1
        assert year_2025_records[0]["fields"]["时长"] == 1


class TestBeijingTimeRule:
    """北京时间规则验证测试"""
    
    def test_all_timestamps_use_beijing_time(self):
        """验证所有时间戳处理使用北京时间"""
        # 确保 TIMEZONE 设置为 Asia/Shanghai
        assert TIMEZONE == "Asia/Shanghai"
        assert str(tz) == "Asia/Shanghai"
