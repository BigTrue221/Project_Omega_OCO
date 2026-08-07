# -*- coding: utf-8 -*-
"""
OCO Cognitive Graph Topology
认知闭环拓扑实现：将 Planner, Executor, Critic, Aggregator 串联为自适应循环。
"""

from typing import Dict, Any, Literal, Optional
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

try:
    # 尝试相对导入（优先）
    from .state import OmegaState
    from ..nodes.planner import AdaptivePlanner
    from ..nodes.executor import Executor
    from ..nodes.critic import CriticNode
    from ..nodes.aggregator import Aggregator
    from ..mcp.client import OCO_MCPClient
    from ..memory.vector_store import OCO_VectorStore
except ImportError:
    try:
        # 尝试 Project_Omega_OCO 直接导入
        from Project_Omega_OCO.core.state import OmegaState
        from Project_Omega_OCO.nodes.planner import AdaptivePlanner
        from Project_Omega_OCO.nodes.executor import Executor
        from Project_Omega_OCO.nodes.critic import CriticNode
        from Project_Omega_OCO.nodes.aggregator import Aggregator
        from Project_Omega_OCO.mcp.client import OCO_MCPClient
        from Project_Omega_OCO.memory.vector_store import OCO_VectorStore
    except ImportError:
        # 尝试绝对导入（从 AI_Ori 目录运行时）
        from AI_Ori.Project_Omega_OCO.core.state import OmegaState
        from AI_Ori.Project_Omega_OCO.nodes.planner import AdaptivePlanner
        from AI_Ori.Project_Omega_OCO.nodes.executor import Executor
        from AI_Ori.Project_Omega_OCO.nodes.critic import CriticNode
        from AI_Ori.Project_Omega_OCO.nodes.aggregator import Aggregator
        from AI_Ori.Project_Omega_OCO.mcp.client import OCO_MCPClient
        from AI_Ori.Project_Omega_OCO.memory.vector_store import OCO_VectorStore

class OmegaCognitiveGraph:
    def __init__(self, mcp_client: OCO_MCPClient, vector_store: Optional[OCO_VectorStore] = None, checkpoint_db_path: str = "checkpoints.sqlite"):
        self.mcp_client = mcp_client
        self.vector_store = vector_store
        self.checkpoint_db_path = checkpoint_db_path
        self._memory = None
        self._app = None
        
        # 1. 初始化节点实例
        # Planner 现在支持可选的 Vector Store 用于 L3 记忆检索
        self.planner = AdaptivePlanner(mcp_client, vector_store)
        self.executor = Executor(mcp_client)
        self.critic = CriticNode()
        self.aggregator = Aggregator()
        
        # 2. 构建状态图 (延迟编译，避免同步初始化 AsyncSqliteSaver)
        workflow = StateGraph(OmegaState)
        
        # 添加节点
        workflow.add_node("planner", self.planner)
        workflow.add_node("executor", self.executor)
        workflow.add_node("critic", self.critic)
        workflow.add_node("aggregator", self.aggregator)
        
        # 3. 定义边 (Edges)
        workflow.add_edge(START, "planner")
        workflow.add_edge("planner", "executor")
        workflow.add_edge("executor", "critic")
        
        # 4. 定义条件边 (Conditional Edge)
        # 根据 Critic 的判断决定是返回 Planner 重新规划，还是进入 Aggregator 汇总
        workflow.add_conditional_edges(
            "critic",
            self._route_after_critic,
            {
                "replan": "planner",
                "finalize": "aggregator"
            }
        )
        
        workflow.add_edge("aggregator", END)
        
        # 5. 延迟编译图 (在异步上下文中初始化 AsyncSqliteSaver)
        self._workflow = workflow
        
    async def _ensure_initialized(self):
        """初始化 AsyncSqliteSaver 和编译图 (异步版本)"""
        if self._app is None:
            import aiosqlite
            self._conn = await aiosqlite.connect(self.checkpoint_db_path, timeout=60.0)
            # 开启 WAL 模式以提高并发性，减少 locked 问题
            await self._conn.execute("PRAGMA journal_mode=WAL")
            # 使用 AsyncSqliteSaver 支持异步操作
            self._memory = AsyncSqliteSaver(self._conn)
            self._app = self._workflow.compile(checkpointer=self._memory)
            print(f"[Graph] AsyncSqliteSaver initialized with {self.checkpoint_db_path}")
    
    @property
    def memory(self):
        """惰性获取 memory"""
        return self._memory
    
    @property
    def app(self):
        """惰性获取 app"""
        return self._app

    def _route_after_critic(self, state: OmegaState) -> Literal["replan", "finalize"]:
        """
        路由逻辑：
        - 如果 is_final 为 True -> finalize
        - 否则 -> replan
        """
        if state.get("is_final", False):
            return "finalize"
        return "replan"

    async def run(self, goal: str, thread_id: str = "default_thread", context: Dict[str, Any] = None, progress_callback=None):
        """
        执行入口
        :param thread_id: L2 记忆隔离标识，用于断点续传与状态恢复
        :param progress_callback: 进度回调函数，签名：callback(stage: str, detail: str, progress: float)
        """
        import time
        start_time = time.time()
        
        print(f"[Graph][TIMING] 开始执行认知图，goal={goal[:50]}...")
        
        # 确保初始化 AsyncSqliteSaver
        await self._ensure_initialized()
        
        # 检查该 thread_id 是否已有状态
        config = {"configurable": {"thread_id": thread_id}}
        state_snapshot = await self.app.aget_state(config)
        
        if state_snapshot.values:
            print(f"[Graph][TIMING] 恢复已有状态，thread_id={thread_id}")
            if progress_callback:
                progress_callback("resuming", "恢复已有会话状态", 0.3)
            invoke_start = time.time()
            from .context import progress_callback_var
            token = progress_callback_var.set(progress_callback)
            try:
                # A checkpoint is a durable conversation/workspace, not a
                # substitute for the next user turn.  For an explicit
                # continuation ("继续", "好的"), inject the new goal and
                # restart the graph from Planner.  The old result set remains
                # available to Planner through the checkpoint reducer.
                route_metadata = ((context or {}).get("route") or {}).get("metadata") or {}
                is_continuation_turn = route_metadata.get("is_new_task") is False
                if is_continuation_turn:
                    previous_context = state_snapshot.values.get("context") or {}
                    continuation_input = {
                        "goal": goal,
                        "context": {
                            **previous_context,
                            **(context or {}),
                            "previous_goal": state_snapshot.values.get("goal", ""),
                            "continuation": True,
                        },
                        "current_plan": [],
                        "plan_version": 0,
                        "error_count": 0,
                        "is_final": False,
                    }
                    final_state = await self.app.ainvoke(continuation_input, config=config)
                else:
                    # Preserve historical replay semantics for callers that
                    # intentionally invoke a completed thread without route
                    # metadata (for example persistence/replay tooling).
                    final_state = await self.app.ainvoke(None, config=config)
            finally:
                progress_callback_var.reset(token)
            print(f"[Graph][TIMING] 恢复状态执行完成，耗时：{time.time() - invoke_start:.2f}秒")
        else:
            print(f"[Graph][TIMING] 开始新会话，thread_id={thread_id}")
            initial_state = {
                "goal": goal,
                "context": context or {},
                "plan_version": 0,
                "cognitive_trace": [],
                "subtask_results": [],
                "error_count": 0,
                "is_final": False
            }
            invoke_start = time.time()
            from .context import progress_callback_var
            token = progress_callback_var.set(progress_callback)
            try:
                final_state = await self.app.ainvoke(initial_state, config=config)
            finally:
                progress_callback_var.reset(token)
            print(f"[Graph][TIMING] 新会话执行完成，耗时：{time.time() - invoke_start:.2f}秒")
        
        total_time = time.time() - start_time
        print(f"[Graph][TIMING] 认知图执行完成，总耗时：{total_time:.2f}秒")
        
        return final_state
