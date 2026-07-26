# -*- coding: utf-8 -*-
"""
MCP 工具调用日志模块
记录所有 MCP 工具调用的详细信息，包括请求参数、响应结果、执行时间等。

功能：
1. 记录工具调用的完整上下文
2. 支持日志查询和统计
3. 提供性能分析数据
"""

import json
import time
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, asdict
import uuid


@dataclass
class ToolCallLog:
    """工具调用日志条目"""
    call_id: str
    tool_name: str
    server_name: str
    request_params: Dict[str, Any]
    response: Dict[str, Any]
    start_time: float
    end_time: float
    duration_ms: float
    status: str  # 'success', 'error', 'timeout'
    error_message: Optional[str] = None
    caller_info: Optional[Dict[str, Any]] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return asdict(self)
    
    def to_json(self) -> str:
        """转换为 JSON 字符串"""
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)


class ToolCallLogger:
    """
    MCP 工具调用日志记录器
    
    功能：
    1. 记录每次工具调用的详细信息
    2. 支持日志持久化到文件
    3. 提供日志查询和统计功能
    """
    
    def __init__(self, log_dir: Optional[str] = None):
        """
        初始化日志记录器
        
        Args:
            log_dir: 日志存储目录，默认为项目 logs 目录
        """
        self.project_root = Path(__file__).parent.parent.parent.parent
        self.log_dir = Path(log_dir) if log_dir else self.project_root / "logs" / "mcp_tool_calls"
        self.log_dir.mkdir(parents=True, exist_ok=True)
        
        # 日志文件路径
        today = datetime.now().strftime("%Y-%m-%d")
        self.log_file = self.log_dir / f"tool_calls_{today}.jsonl"
        
        # 内存缓存（用于快速查询）
        self.memory_cache: List[ToolCallLog] = []
        self.max_cache_size = 10000
        
        # 配置日志
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        self.logger = logging.getLogger("MCP_ToolCallLogger")
        
        self.logger.info(f"[ToolCallLogger] 初始化完成，日志文件：{self.log_file}")
    
    def log_call(
        self,
        tool_name: str,
        server_name: str,
        request_params: Dict[str, Any],
        response: Dict[str, Any],
        start_time: float,
        status: str = 'success',
        error_message: Optional[str] = None,
        caller_info: Optional[Dict[str, Any]] = None
    ) -> ToolCallLog:
        """
        记录工具调用
        
        Args:
            tool_name: 工具名称
            server_name: MCP 服务器名称
            request_params: 请求参数
            response: 响应结果
            start_time: 调用开始时间戳
            status: 调用状态 ('success', 'error', 'timeout')
            error_message: 错误消息（如果有）
            caller_info: 调用者信息（可选）
            
        Returns:
            ToolCallLog: 创建的日志条目
        """
        end_time = time.time()
        duration_ms = (end_time - start_time) * 1000
        
        # 创建日志条目
        log_entry = ToolCallLog(
            call_id=str(uuid.uuid4()),
            tool_name=tool_name,
            server_name=server_name,
            request_params=request_params,
            response=response,
            start_time=start_time,
            end_time=end_time,
            duration_ms=duration_ms,
            status=status,
            error_message=error_message,
            caller_info=caller_info
        )
        
        # 写入文件（JSONL 格式）
        self._write_to_file(log_entry)
        
        # 添加到内存缓存
        self._add_to_cache(log_entry)
        
        # 打印日志
        status_icon = '✓' if status == 'success' else '✗'
        self.logger.info(
            f"{status_icon} [{server_name}] {tool_name} - "
            f"duration: {duration_ms:.2f}ms, status: {status}"
        )
        
        if error_message:
            self.logger.error(f"    Error: {error_message}")
        
        return log_entry
    
    def _write_to_file(self, log_entry: ToolCallLog):
        """写入日志文件"""
        try:
            with open(self.log_file, 'a', encoding='utf-8') as f:
                f.write(log_entry.to_json() + '\n')
        except Exception as e:
            self.logger.error(f"[ToolCallLogger] 写入日志文件失败：{e}")
    
    def _add_to_cache(self, log_entry: ToolCallLog):
        """添加到内存缓存"""
        self.memory_cache.append(log_entry)
        
        # 限制缓存大小
        if len(self.memory_cache) > self.max_cache_size:
            self.memory_cache = self.memory_cache[-self.max_cache_size:]
    
    def get_recent_calls(
        self,
        limit: int = 100,
        tool_name: Optional[str] = None,
        status: Optional[str] = None
    ) -> List[ToolCallLog]:
        """
        获取最近的工具调用记录
        
        Args:
            limit: 返回记录数量限制
            tool_name: 按工具名称过滤（可选）
            status: 按状态过滤（可选）
            
        Returns:
            List[ToolCallLog]: 过滤后的日志列表
        """
        result = self.memory_cache[-limit:]
        
        if tool_name:
            result = [log for log in result if log.tool_name == tool_name]
        
        if status:
            result = [log for log in result if log.status == status]
        
        return result
    
    def get_statistics(self) -> Dict[str, Any]:
        """
        获取工具调用统计信息
        
        Returns:
            Dict[str, Any]: 统计信息字典
        """
        if not self.memory_cache:
            return {
                "total_calls": 0,
                "success_rate": 0,
                "avg_duration_ms": 0,
                "calls_by_tool": {},
                "calls_by_status": {}
            }
        
        total = len(self.memory_cache)
        success_count = sum(1 for log in self.memory_cache if log.status == 'success')
        
        # 按工具统计
        calls_by_tool = {}
        for log in self.memory_cache:
            tool_name = log.tool_name
            if tool_name not in calls_by_tool:
                calls_by_tool[tool_name] = {'count': 0, 'total_duration': 0}
            calls_by_tool[tool_name]['count'] += 1
            calls_by_tool[tool_name]['total_duration'] += log.duration_ms
        
        # 计算平均耗时
        for tool_name in calls_by_tool:
            count = calls_by_tool[tool_name]['count']
            calls_by_tool[tool_name]['avg_duration_ms'] = \
                calls_by_tool[tool_name]['total_duration'] / count
            del calls_by_tool[tool_name]['total_duration']
        
        # 按状态统计
        calls_by_status = {}
        for log in self.memory_cache:
            status = log.status
            calls_by_status[status] = calls_by_status.get(status, 0) + 1
        
        return {
            "total_calls": total,
            "success_rate": success_count / total if total > 0 else 0,
            "avg_duration_ms": sum(log.duration_ms for log in self.memory_cache) / total,
            "calls_by_tool": calls_by_tool,
            "calls_by_status": calls_by_status
        }
    
    def export_report(self, output_path: Optional[str] = None) -> str:
        """
        导出日志报告
        
        Args:
            output_path: 输出文件路径（可选）
            
        Returns:
            str: 报告内容
        """
        stats = self.get_statistics()
        
        report = []
        report.append("=" * 60)
        report.append("MCP 工具调用日志报告")
        report.append("=" * 60)
        report.append(f"生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        report.append("")
        
        report.append("【总体统计】")
        report.append(f"  总调用次数：{stats['total_calls']}")
        report.append(f"  成功率：{stats['success_rate']:.2%}")
        report.append(f"  平均耗时：{stats['avg_duration_ms']:.2f}ms")
        report.append("")
        
        report.append("【按状态分布】")
        for status, count in stats['calls_by_status'].items():
            report.append(f"  {status}: {count}")
        report.append("")
        
        report.append("【按工具统计】")
        for tool_name, data in stats['calls_by_tool'].items():
            report.append(f"  {tool_name}:")
            report.append(f"    调用次数：{data['count']}")
            report.append(f"    平均耗时：{data['avg_duration_ms']:.2f}ms")
        report.append("")
        
        report_text = '\n'.join(report)
        
        # 写入文件
        if output_path:
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(report_text)
            self.logger.info(f"[ToolCallLogger] 报告已导出到：{output_path}")
        
        return report_text


# 全局日志记录器实例
_global_logger: Optional[ToolCallLogger] = None


def get_logger() -> ToolCallLogger:
    """获取全局日志记录器实例"""
    global _global_logger
    if _global_logger is None:
        _global_logger = ToolCallLogger()
    return _global_logger


def reset_logger():
    """重置全局日志记录器（用于测试）"""
    global _global_logger
    _global_logger = None
