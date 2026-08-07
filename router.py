# -*- coding: utf-8 -*-
"""
OCO Router - 认知闭环路由模块

本模块实现了 OCO 架构中的路由决策逻辑，负责：
1. 检测任务类型（简单/复杂）
2. 检测是否为新任务
3. 生成/恢复 thread_id
4. 决定使用传统路径还是 OCO 认知闭环
"""

import hashlib
import time
import logging
from dataclasses import dataclass
from enum import Enum
from typing import Optional, Dict, Any

logger = logging.getLogger("OCO_Router")


class TaskComplexity(Enum):
    """任务复杂度枚举"""
    SIMPLE = "simple"      # 简单任务：直接响应
    MEDIUM = "medium"      # 中等复杂度：可能需要多步
    COMPLEX = "complex"    # 复杂任务：需要认知闭环


class RoutePath(Enum):
    """路由路径枚举"""
    LEGACY = "legacy"          # 传统路径：处理简单任务
    OCO = "oco"            # OCO 认知闭环：处理复杂任务
    HARNESS = "harness"        # Harness 路径：特定 Agent 任务


@dataclass
class RouteDecision:
    """路由决策结果"""
    path: RoutePath           # 路由路径
    thread_id: Optional[str]  # thread_id（OCO 路径需要）
    complexity: TaskComplexity  # 任务复杂度
    reasoning: str            # 决策理由
    metadata: Dict[str, Any]  # 额外元数据


class OCORouter:
    """
    OCO 统一架构路由决策器
    
    核心功能：
    1. thread_id 管理
    2. 路由决策（所有任务路由到 OCO）
    
    OCO 统一架构原则：
    - 所有任务统一路由到 OCO 认知闭环
    - 由 OCO Planner 根据任务类型选择 MCP 工具
    - 移除硬编码的路由规则
    """
    
    def __init__(self, session_metadata_getter=None):
        """
        初始化路由器
        
        Args:
            session_metadata_getter: 获取会话元数据的回调函数
        """
        self.session_metadata_getter = session_metadata_getter
    
    def assess_complexity(self, message: str) -> TaskComplexity:
        """
        评估任务复杂度
        """
        # 简单任务关键词
        simple_keywords = ["你好", "hi", "hello", "在吗", "是谁", "天气", "谢谢", "早安", "晚安", "再见", "拜拜", "哈喽"]
        
        # 复杂任务关键词 (主要是依赖外部 MCP 工具的长线任务)
        complex_keywords = [
            "小说", "大纲", "章节", "故事", "创作", 
            "架构", "设计", "系统", "规划", "分析",
            "代码", "开发", "项目", "黑进", "攻击",
            "调用", "读取", "工具", "文件", "总结", "目录", "设定"
        ]
        
        message_lower = message.lower().strip()
        
        # 1. 检查简单任务
        if len(message_lower) < 15 and any(k in message_lower for k in simple_keywords):
            return TaskComplexity.SIMPLE
            
        # 2. 检查复杂任务
        if any(k in message_lower for k in complex_keywords):
            return TaskComplexity.COMPLEX
            
        # 3. 基于长度的评估 (如果既不是寒暄，也不是复杂任务，就判定为 SIMPLE，交给大模型自由回答)
        if len(message_lower) > 300:
            return TaskComplexity.COMPLEX
            
        # 默认：普通对话、自由任务等不涉及专业 MCP 工具的请求，统统走 LEGACY 快速问答路径
        return TaskComplexity.SIMPLE
        
    def route(self, message: str, sender_id: str, context: Dict[str, Any] = None) -> RouteDecision:
        """
        路由决策主入口
        """
        context = context or {}
        
        complexity = self.assess_complexity(message)
        
        # Continuation acknowledgements are short, but must not fall out of
        # the OCO thread merely because they do not contain a complex-task
        # keyword.  This is what makes "继续"/"好的" useful after a long task.
        if (
            complexity == TaskComplexity.SIMPLE
            and context.get("thread_id")
            and self._is_continuation_message(message)
        ):
            return RouteDecision(
                path=RoutePath.OCO,
                thread_id=context["thread_id"],
                complexity=complexity,
                reasoning="续传确认消息，恢复当前 OCO thread",
                metadata={"is_new_task": False},
            )

        # 简单任务：使用传统路径（快速响应）
        if complexity == TaskComplexity.SIMPLE:
            return RouteDecision(
                path=RoutePath.LEGACY,
                thread_id=None,
                complexity=complexity,
                reasoning="简单任务，使用传统处理路径以提供快速响应",
                metadata={}
            )
        
        # 复杂/中等任务：使用 OCO 认知闭环
        is_new_task = self.detect_new_task(message, context)
        
        if is_new_task:
            thread_id = self.generate_thread_id(sender_id, message)
            reasoning = f"新任务 (复杂度: {complexity.value})，启动 OCO 认知闭环（新 thread_id）"
        else:
            thread_id = self.recover_thread_id(sender_id, context)
            reasoning = f"续传任务 (复杂度: {complexity.value})，恢复 OCO 认知闭环（原有 thread_id）"
        
        return RouteDecision(
            path=RoutePath.OCO,
            thread_id=thread_id,
            complexity=complexity,
            reasoning=reasoning,
            metadata={"is_new_task": is_new_task}
        )
    
    def _is_continuation_message(self, message: str) -> bool:
        """Return whether a short message explicitly continues a task."""
        continuation_keywords = {
            "好的", "好", "行", "可以", "继续", "接着", "然后",
            "y", "yes", "yeah", "ok", "okay", "嗯", "对", "是的",
        }
        return message.lower().strip() in continuation_keywords

    def detect_new_task(self, message: str, context: Dict[str, Any]) -> bool:
        """
        检测是否为新任务
        
        判断逻辑：
        1. 检查消息是否包含续传关键词（确认/继续类）
        2. 检查上下文是否有进行中的任务
        3. 检查消息是否包含新任务关键词
        4. 检查消息是否与当前任务相关
        
        Args:
            message: 用户消息
            context: 上下文信息
        
        Returns:
            bool: 是否为新任务
        """
        # 续传/确认关键词（表示继续当前任务）
        continuation_keywords = [
            "好的", "好", "行", "可以", "继续", "接着", "然后",
            "y", "yes", "yeah", "ok", "okay",
            "嗯", "对", "是的",
        ]
        
        # 检查是否为续传/确认消息
        message_lower = message.lower().strip()
        for keyword in continuation_keywords:
            if message_lower == keyword or keyword in message:
                logger.info(f"[New Task Detection] 检测到续传关键词：{keyword}")
                return False
        
        # 新任务关键词
        new_task_keywords = [
            "新", "新的", "另一个", "另外", "换一个",
            "开始", "启动", "创建",
            "写一个", "创作一个", "设计一个",
        ]
        
        # 检查是否包含新任务关键词
        for keyword in new_task_keywords:
            if keyword in message:
                logger.info(f"[New Task Detection] 检测到新任务关键词：{keyword}")
                return True
        
        # 检查上下文是否有进行中的任务
        current_task = context.get("current_task")
        if not current_task:
            # 没有进行中的任务，视为新任务
            logger.info("[New Task Detection] 无进行中的任务，视为新任务")
            return True
        
        # TODO: 实现消息与当前任务的相关性检查
        # 这里简化处理：如果消息长度较短，可能是对当前任务的反馈
        if len(message) < 20:
            logger.info("[New Task Detection] 消息较短，可能是对当前任务的反馈")
            return False
        
        # 默认视为新任务
        logger.info("[New Task Detection] 默认视为新任务")
        return True
    
    def generate_thread_id(self, sender_id: str, message: str) -> str:
        """
        生成新的 thread_id
        
        格式：{sender_id}_{timestamp}_{task_hash}
        
        Args:
            sender_id: 发送者 ID
            message: 用户消息（用于生成任务哈希）
        
        Returns:
            str: 新的 thread_id
        """
        timestamp = int(time.time())
        
        # 生成任务哈希（使用消息前 100 个字符）
        task_content = message[:100]
        task_hash = hashlib.md5(task_content.encode()).hexdigest()[:8]
        
        thread_id = f"{sender_id}_{timestamp}_{task_hash}"
        
        logger.info(f"[Thread ID] 生成新 thread_id: {thread_id}")
        return thread_id
    
    def recover_thread_id(self, sender_id: str, context: Dict[str, Any]) -> Optional[str]:
        """
        恢复原有的 thread_id
        
        Args:
            sender_id: 发送者 ID
            context: 上下文信息
        
        Returns:
            Optional[str]: 原有的 thread_id，如果不存在则返回 None
        """
        # 从上下文中获取
        thread_id = context.get("thread_id")
        if thread_id:
            logger.info(f"[Thread ID] 从上下文恢复 thread_id: {thread_id}")
            return thread_id
        
        # 从会话元数据中获取
        if self.session_metadata_getter:
            try:
                thread_id = self.session_metadata_getter(sender_id, "current_thread_id")
                if thread_id:
                    logger.info(f"[Thread ID] 从会话元数据恢复 thread_id: {thread_id}")
                    return thread_id
            except Exception as e:
                logger.warning(f"[Thread ID] 从会话元数据恢复失败：{e}")
        
        # 无法恢复，返回 None
        logger.warning("[Thread ID] 无法恢复 thread_id")
        return None


# 默认路由器实例
default_router = OCORouter()


def route_message(message: str, sender_id: str, context: Dict[str, Any] = None) -> RouteDecision:
    """
    便捷函数：路由决策
    
    Args:
        message: 用户消息
        sender_id: 发送者 ID
        context: 上下文信息
    
    Returns:
        RouteDecision: 路由决策结果
    """
    return default_router.route(message, sender_id, context or {})
