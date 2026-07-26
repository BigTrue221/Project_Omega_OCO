# -*- coding: utf-8 -*-
"""
Adaptive Planner Node
自适应规划节点：负责将最终目标分解为可执行的子任务序列。

增强功能：集成 L3 长期记忆检索，在规划前注入相关知识。
"""

import json
import time
from typing import Dict, Any, List, Optional

# 使用灵活的导入方式，支持多种运行环境
try:
    # 尝试相对导入（优先）
    from ..core.state import OmegaState, SubTaskResult
    from ..mcp.client import OCO_MCPClient
    from ..core.llm import LLMClient
    from ..memory.vector_store import OCO_VectorStore
except ImportError:
    try:
        # 尝试 Project_Omega_OCO 直接导入
        from Project_Omega_OCO.core.state import OmegaState, SubTaskResult
        from Project_Omega_OCO.mcp.client import OCO_MCPClient
        from Project_Omega_OCO.core.llm import LLMClient
        from Project_Omega_OCO.memory.vector_store import OCO_VectorStore
    except ImportError:
        # 尝试绝对导入（从 AI_Ori 目录运行时）
        from AI_Ori.Project_Omega_OCO.core.state import OmegaState, SubTaskResult
        from AI_Ori.Project_Omega_OCO.mcp.client import OCO_MCPClient
        from AI_Ori.Project_Omega_OCO.core.llm import LLMClient
        from AI_Ori.Project_Omega_OCO.memory.vector_store import OCO_VectorStore

class AdaptivePlanner:
    def __init__(self, mcp_client: OCO_MCPClient, vector_store: Optional[OCO_VectorStore] = None):
        self.mcp_client = mcp_client
        self.llm = LLMClient()
        self.vector_store = vector_store

    async def __call__(self, state: OmegaState) -> Dict[str, Any]:
        """
        规划逻辑：
        1. 从 L3 长期记忆检索相关知识 (如果可用)
        2. 获取当前可用工具列表 (MCP Discovery)
        3. 根据 goal、已有结果和检索到的知识，生成/更新 current_plan
        4. 增加 plan_version
        """
        import time
        node_start = time.time()
        
        goal = state.get("goal", "No goal defined")
        results = state.get("subtask_results", [])
        plan_version = state.get("plan_version", 0)
        
        try:
            from ..core.context import progress_callback_var
            progress_callback = progress_callback_var.get()
        except Exception:
            try:
                from Project_Omega_OCO.core.context import progress_callback_var
                progress_callback = progress_callback_var.get()
            except Exception:
                progress_callback = None
        
        # 报告进度：Planner 开始
        if progress_callback:
            progress_callback("planning", "正在分析任务并生成执行计划...", 0.3)
        
        print(f"[Planner][TIMING] 开始执行 Planner 节点，goal={goal[:50]}...")
        
        # 1. 从 L3 长期记忆检索相关知识
        relevant_knowledge = ""
        l3_start = time.time()
        if self.vector_store:
            try:
                print(f"[Planner][TIMING] 正在从 L3 记忆检索相关知识...")
                if progress_callback:
                    progress_callback("planning", "正在检索相关知识...", 0.35)
                query_results = await self.vector_store.query(goal, top_k=3)
                if query_results:
                    knowledge_parts = []
                    for entry, score in query_results:
                        knowledge_parts.append(f"- [{score:.2f}] {entry.content}")
                    relevant_knowledge = "\n".join(knowledge_parts)
                    print(f"[Planner][TIMING] 检索到 {len(query_results)} 条相关知识")
            except Exception as e:
                print(f"[Planner][TIMING] 警告：L3 记忆检索失败：{e}")
        l3_elapsed = time.time() - l3_start
        print(f"[Planner][TIMING] L3 记忆检索完成，耗时：{l3_elapsed:.2f}秒")
        
        # 2. 动态发现可用能力
        mcp_start = time.time()
        print(f"[Planner][TIMING] 正在获取可用工具列表...")
        if progress_callback:
            progress_callback("planning", "正在发现可用工具...", 0.4)
        
        tools_dict = self.mcp_client.get_available_tools()
        available_tools = [{"name": t.name, "description": t.description} for t in tools_dict.values()]
        
        tools_desc = "\n".join([f"- {t['name']}: {t['description']}" for t in available_tools])
        mcp_elapsed = time.time() - mcp_start
        print(f"[Planner][TIMING] 获取到 {len(available_tools)} 个可用工具，耗时：{mcp_elapsed:.2f}秒")

        # 3. 真实 LLM 规划过程 (注入 L3 知识)
        llm_start = time.time()
        print(f"[Planner][TIMING] 正在调用 LLM 生成计划...")
        if progress_callback:
            progress_callback("planning", "正在调用 LLM 生成执行计划...", 0.5)
        
        system_prompt = f"""你是一个高级任务规划与调度器（Planner）。你的核心职责是“拆解任务并调度工具”，而不是“亲自执行任务”。

【核心规范】
1. 复杂任务必须拆解：对于小说创作、代码编写、长文本生成等复杂任务，你必须将其拆解为多个步骤，并调用对应的专业工具（如大纲生成、章节撰写等）来完成。
2. 严禁越俎代庖：绝对不允许在未经工具调用的情况下，直接生成长篇小说、代码或最终交付物。你只能做计划！
3. 能力边界约束：你只能使用下方的【可用工具列表】中列出的真实工具。如果你发现完成目标所需的能力不在列表中，必须触发“能力缺失”异常。

【可用工具列表】
{tools_desc}

【输出格式】
输出必须是 JSON 格式，包含 'plan' 字段，其值为任务列表。每个任务包含:
- task_id: 唯一标识
- description: 任务描述
- tool: 工具名称（必须从可用工具列表中严格选择，不得捏造。如果能力缺失，固定填写 "CAPABILITY_MISSING"）
- params: 参数字典（如果是 CAPABILITY_MISSING，请在 params 中提供 "required_capability" 和 "reason" 字段说明缺少什么工具）
"""
        
        # 构建用户提示，包含 L3 知识
        user_prompt_parts = [f"目标：{goal}"]
        if relevant_knowledge:
            knowledge_section = f"\n相关知识点 (来自长期记忆):\n{relevant_knowledge}"
            user_prompt_parts.append(knowledge_section)
        user_prompt_parts.append(f"\n当前已完成结果：{results}")
        user_prompt_parts.append("\n请生成接下来的执行计划。")
        user_prompt = "\n".join(user_prompt_parts)
        
        new_plan = self.llm.generate_json(system_prompt, user_prompt).get("plan", [])
        llm_elapsed = time.time() - llm_start
        print(f"[Planner][TIMING] LLM 生成计划完成，耗时：{llm_elapsed:.2f}秒")
        
        node_elapsed = time.time() - node_start
        print(f"[Planner][TIMING] Planner 节点执行完成，总耗时：{node_elapsed:.2f}秒")
        
        # 报告进度：Planner 完成
        if progress_callback:
            progress_callback("planning", f"计划生成完成，共 {len(new_plan)} 个任务", 0.6)
        
        return {
            "current_plan": new_plan,
            "plan_version": plan_version + 1,
            "cognitive_trace": [f"Planner generated plan v{plan_version + 1} for goal: {goal}"]
        }
