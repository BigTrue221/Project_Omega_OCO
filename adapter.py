# -*- coding: utf-8 -*-
"""
OCO Cognitive Loop Adapter
OCO 认知闭环适配器

本模块提供了 OCO 认知闭环的同步调用接口，封装了异步的 OmegaCognitiveGraph。
主要功能：
1. MCP 客户端的初始化
2. OmegaCognitiveGraph 的初始化
3. 异步调用的同步包装
4. 错误处理和降级
5. L3 长期记忆 (Vector Store) 的初始化
"""

import asyncio
import logging
import os
import threading
from typing import Dict, Any, Optional, List
from pathlib import Path

# --- Global Background Event Loop ---
_global_loop: Optional[asyncio.AbstractEventLoop] = None
_global_loop_thread: Optional[threading.Thread] = None
_global_loop_lock = threading.Lock()

def _start_background_loop(loop: asyncio.AbstractEventLoop) -> None:
    asyncio.set_event_loop(loop)
    try:
        loop.run_forever()
    except Exception as e:
        logging.getLogger("OCO_Adapter").error(f"[OCO Adapter] Background loop crashed: {e}")

def get_global_loop() -> asyncio.AbstractEventLoop:
    global _global_loop, _global_loop_thread
    with _global_loop_lock:
        if _global_loop is None or _global_loop.is_closed():
            _global_loop = asyncio.new_event_loop()
            _global_loop_thread = threading.Thread(
                target=_start_background_loop, 
                args=(_global_loop,), 
                daemon=True,
                name="OCO_Background_Loop"
            )
            _global_loop_thread.start()
        return _global_loop
# ------------------------------------

# 导入 OCO 核心组件
# 支持三种导入方式：
# 1. 相对导入（当 adapter.py 作为模块被导入时）
# 2. Project_Omega_OCO 直接导入（当 Project_Omega_OCO 在 sys.path 中时）
# 3. 绝对导入（当从 AI_Ori 目录运行时）
IMPORT_ERROR_MSG = None
try:
    # 尝试相对导入（优先）
    from .core.graph import OmegaCognitiveGraph
    from .mcp.client import OCO_MCPClient, MCPServerConfig
    OCO_CORE_AVAILABLE = True
except ImportError as e1:
    try:
        # 尝试 Project_Omega_OCO 直接导入（当 Project_Omega_OCO 在 sys.path 中时）
        from Project_Omega_OCO.core.graph import OmegaCognitiveGraph
        from Project_Omega_OCO.mcp.client import OCO_MCPClient, MCPServerConfig
        OCO_CORE_AVAILABLE = True
    except ImportError as e2:
        try:
            # 尝试绝对导入（从 AI_Ori 目录运行时）
            from AI_Ori.Project_Omega_OCO.core.graph import OmegaCognitiveGraph
            from AI_Ori.Project_Omega_OCO.mcp.client import OCO_MCPClient, MCPServerConfig
            OCO_CORE_AVAILABLE = True
            IMPORT_ERROR_MSG = None
        except ImportError as e3:
            OCO_CORE_AVAILABLE = False
            IMPORT_ERROR_MSG = f"Import failures:\n1. {e1}\n2. {e2}\n3. {e3}"
            logging.warning(f"[OCO Adapter] 核心组件不可用：\n{IMPORT_ERROR_MSG}")
            OmegaCognitiveGraph = None
            OCO_MCPClient = None
            MCPServerConfig = None

# 尝试导入 Vector Store (可选)
try:
    # 尝试相对导入（优先）
    from .memory.vector_store import OCO_VectorStore
    VECTOR_STORE_AVAILABLE = True
except ImportError:
    try:
        # 尝试 Project_Omega_OCO 直接导入
        from Project_Omega_OCO.memory.vector_store import OCO_VectorStore
        VECTOR_STORE_AVAILABLE = True
    except ImportError:
        try:
            # 尝试绝对导入（从 AI_Ori 目录运行时）
            from AI_Ori.Project_Omega_OCO.memory.vector_store import OCO_VectorStore
            VECTOR_STORE_AVAILABLE = True
        except ImportError as e:
            VECTOR_STORE_AVAILABLE = False
            logging.warning(f"[OCO Adapter] Vector Store 不可用：{e}")
            OCO_VectorStore = None

logger = logging.getLogger("OCO_Adapter")


class OCOCognitiveLoopAdapter:
    """
    OCO 认知闭环适配器
    
    提供同步调用接口，封装异步的 OmegaCognitiveGraph。
    """
    
    def __init__(self, checkpoint_db_path: str = "checkpoints.sqlite",
                 vector_store_path: str = "./chroma_db",
                 enable_vector_store: bool = True):
        """
        初始化适配器
        
        Args:
            checkpoint_db_path: Checkpoint 数据库路径
            vector_store_path: Vector Store 持久化路径
            enable_vector_store: 是否启用 Vector Store (L3 记忆)
        """
        self.mcp_client: Optional[OCO_MCPClient] = None
        self.vector_store: Optional[OCO_VectorStore] = None
        self.cognitive_graph: Optional[OmegaCognitiveGraph] = None
        self.checkpoint_db_path = checkpoint_db_path
        self.vector_store_path = vector_store_path
        self.enable_vector_store = enable_vector_store
        self.initialized = False
        self.mcp_server_configs: List[MCPServerConfig] = []  # 存储 MCP 服务器配置
        self.mcp_connected = False  # MCP 连接状态
        
        if not OCO_CORE_AVAILABLE:
            logger.error("[OCO Adapter] 核心组件不可用，适配器无法初始化")
            return
        
        try:
            # 初始化 MCP 客户端
            self.mcp_client = OCO_MCPClient()
            
            # 配置 MCP 服务器（只存储配置，不连接）
            self._configure_mcp_servers()
            
            # 初始化 Vector Store (L3 长期记忆)
            if enable_vector_store and VECTOR_STORE_AVAILABLE:
                try:
                    self.vector_store = OCO_VectorStore(
                        collection_name="oco_long_term_memory",
                        persist_directory=vector_store_path
                    )
                    logger.info(f"[OCO Adapter] Vector Store 初始化成功：{vector_store_path}")
                except Exception as e:
                    logger.warning(f"[OCO Adapter] Vector Store 初始化失败：{e}，将不使用 L3 记忆")
                    self.vector_store = None
            elif enable_vector_store:
                logger.warning("[OCO Adapter] Vector Store 未安装，将不使用 L3 记忆")
            
            # 初始化认知图 (传入 MCP 客户端和 Vector Store)
            self.cognitive_graph = OmegaCognitiveGraph(self.mcp_client, self.vector_store)
            
            self.initialized = True
            logger.info(f"[OCO Adapter] 初始化成功，配置了 {len(self.mcp_server_configs)} 个 MCP 服务器")
            
        except Exception as e:
            logger.error(f"[OCO Adapter] 初始化失败：{e}")
            self.initialized = False
    
    def _configure_mcp_servers(self):
        """
        配置 MCP 服务器
        
        这里配置可用的 MCP 服务器，包括：
        1. Novel MCP Server - 小说创作相关工具
        2. Internet MCP Server - 互联网搜索工具
        3. Harness MCP Server - Harness Agent 封装
        
        注意：这里只存储配置，实际连接在 _connect_mcp_servers() 中异步执行
        """
        if not self.mcp_client:
            return
        
        # 获取项目根目录
        oco_root = Path(__file__).resolve().parent
        ai_ori_root = oco_root.parent
        
        # 配置 MCP 服务器
        # 注意：服务运行在 WSL 中，直接使用 python3 启动 MCP 服务器
        # 使用绝对路径确保在 WSL 环境中能找到脚本
        
        # 获取 MCP 运行路径。保留历史 WSL 默认值，同时允许发布版通过环境变量覆盖。
        mcp_project_root = os.getenv("OCO_MCP_PROJECT_ROOT", str(ai_ori_root))
        venv_python = os.getenv("OCO_MCP_PYTHON", "python3")
        
        # 配置 Novel MCP Server (从 Project_Omega/mcp_servers 加载)
        novel_server_path = ai_ori_root / "Project_Omega" / "mcp_servers" / "novel_mcp_server.py"
        if novel_server_path.exists() or os.getenv("OCO_MCP_NOVEL_SERVER"):
            novel_server = os.getenv("OCO_MCP_NOVEL_SERVER", str(novel_server_path))
            novel_config = MCPServerConfig(
                name="novel_tools",
                command=venv_python,
                args=[novel_server],
                env={"PYTHONPATH": mcp_project_root}
            )
            self.mcp_server_configs.append(novel_config)
            logger.info(f"[OCO Adapter] 配置 Novel MCP Server: {novel_server}")
        
        # 配置 Internet MCP Server
        internet_server_path = oco_root / "mcp" / "servers" / "internet_server.py"
        if internet_server_path.exists():
            internet_config = MCPServerConfig(
                name="internet_tools",
                command=venv_python,
                args=[os.getenv("OCO_MCP_INTERNET_SERVER", str(internet_server_path))],
                env={"PYTHONPATH": mcp_project_root}
            )
            self.mcp_server_configs.append(internet_config)
            logger.info(f"[OCO Adapter] 配置 Internet MCP Server: {internet_config.args[0]}")
        
        # 配置 Harness MCP Server (Harness Agent)
        harness_server_path = oco_root / "mcp" / "servers" / "harness_mcp_server.py"
        if harness_server_path.exists():
            harness_config = MCPServerConfig(
                name="harness_agent",
                command=venv_python,
                args=[os.getenv("OCO_MCP_HARNESS_SERVER", str(harness_server_path))],
                env={"PYTHONPATH": mcp_project_root}
            )
            self.mcp_server_configs.append(harness_config)
            logger.info(f"[OCO Adapter] 配置 Harness MCP Server: {harness_config.args[0]}")
    
    async def _connect_mcp_servers(self):
        """
        异步连接所有配置的 MCP 服务器
        
        Returns:
            bool: 是否至少有一个服务器连接成功
        """
        if not self.mcp_client or not self.mcp_server_configs:
            logger.warning("[OCO Adapter] 没有配置的 MCP 服务器")
            return False
        
        if self.mcp_connected:
            logger.info("[OCO Adapter] MCP 服务器已连接，跳过连接")
            return True
        
        success_count = 0
        for config in self.mcp_server_configs:
            try:
                result = await self.mcp_client.add_server(config)
                if result:
                    success_count += 1
                    logger.info(f"[OCO Adapter] MCP 服务器 {config.name} 连接成功")
                else:
                    logger.warning(f"[OCO Adapter] MCP 服务器 {config.name} 连接失败")
            except Exception as e:
                logger.error(f"[OCO Adapter] 连接 MCP 服务器 {config.name} 时出错：{e}")
        
        if success_count > 0:
            self.mcp_connected = True
            logger.info(f"[OCO Adapter] MCP 连接完成，{success_count}/{len(self.mcp_server_configs)} 个服务器连接成功")
        
        return success_count > 0
    
    async def _run_with_mcp_connection(self, goal: str, thread_id: str, context: Dict[str, Any], progress_callback=None) -> Dict[str, Any]:
        """
        异步执行 OCO 认知闭环，包括 MCP 服务器连接
        
        Args:
            goal: 目标/任务描述
            thread_id: 线程 ID
            context: 上下文信息
            progress_callback: 进度回调函数，签名：callback(stage: str, detail: str, progress: float)
        
        Returns:
            Dict[str, Any]: 执行结果
        """
        import time
        total_start = time.time()
        
        logger.info(f"[OCO Adapter][TIMING] 开始执行任务：{goal[:50]}...")
        logger.info(f"[OCO Adapter][TIMING] MCP 连接状态：{self.mcp_connected}")
        
        # 报告初始进度
        if progress_callback:
            progress_callback("initializing", "正在初始化 OCO 认知闭环...", 0.05)
        
        # 1. 先连接 MCP 服务器（如果尚未连接）
        mcp_start = time.time()
        if not self.mcp_connected:
            logger.info("[OCO Adapter][TIMING] 正在连接 MCP 服务器...")
            if progress_callback:
                progress_callback("connecting_mcp", "正在连接 MCP 工具服务器...", 0.1)
            mcp_connected = await self._connect_mcp_servers()
            mcp_elapsed = time.time() - mcp_start
            logger.info(f"[OCO Adapter][TIMING] MCP 连接完成，耗时：{mcp_elapsed:.2f}秒")
            if not mcp_connected:
                logger.warning("[OCO Adapter] 所有 MCP 服务器连接失败，将继续执行但不使用 MCP 工具")
        else:
            logger.info("[OCO Adapter][TIMING] MCP 服务器已连接，跳过连接")
            
        # 增加自检机制：如果未获取到任何工具，且任务明显复杂，主动报错截断，避免 Planner 陷入死循环
        has_tools = self.mcp_client and len(self.mcp_client.available_tools) > 0
        if not has_tools and len(goal) > 15 and any(kw in goal for kw in ["写", "生成", "代码", "分析", "总结", "大纲"]):
            error_msg = "系统自检未通过：未获取到任何可用的后台工具（MCP Servers 未就绪），为避免陷入执行死循环，已主动中断任务。请检查工具服务配置。"
            logger.error(f"[OCO Adapter] 严重错误：{error_msg}")
            if progress_callback:
                progress_callback("failed", "执行已中断：工具服务未就绪", 1.0)
            return {
                "success": False,
                "error": "能力缺失：无可用 MCP 工具",
                "response": error_msg
            }
        
        # 2. 执行认知图
        graph_start = time.time()
        logger.info(f"[OCO Adapter][TIMING] 开始执行认知图...")
        if progress_callback:
            progress_callback("starting", "正在启动认知图执行...", 0.2)
        result = await self.cognitive_graph.run(goal, thread_id, context, progress_callback=progress_callback)
        graph_elapsed = time.time() - graph_start
        total_elapsed = time.time() - total_start
        logger.info(f"[OCO Adapter][TIMING] 认知图执行完成，耗时：{graph_elapsed:.2f}秒")
        logger.info(f"[OCO Adapter][TIMING] 总耗时：{total_elapsed:.2f}秒")
        
        # 报告完成
        if progress_callback:
            progress_callback("completed", "任务执行完成", 1.0)
        
        return result
    
    def run(self, goal: str, thread_id: str, context: Dict[str, Any] = None, timeout: int = 600, progress_callback=None) -> Dict[str, Any]:
        """
        同步调用 OCO 认知闭环
        
        Args:
            goal: 目标/任务描述
            thread_id: 线程 ID（用于状态隔离）
            context: 上下文信息
            timeout: 超时时间（秒）
            progress_callback: 进度回调函数，签名：callback(stage: str, detail: str, progress: float)
        
        Returns:
            Dict[str, Any]: 执行结果
        """
        if not self.initialized or not self.cognitive_graph:
            logger.error("[OCO Adapter] 适配器未初始化，无法执行")
            return {
                "success": False,
                "error": "OCO 认知闭环未初始化",
                "response": "系统暂时无法处理复杂任务，请稍后再试。"
            }
        
        logger.info(f"[OCO Adapter] 开始执行任务：{goal[:50]}...")
        
        # 使用全局后台事件循环来执行任务，避免每次创建销毁引发 MCP 资源泄漏
        try:
            loop = get_global_loop()
            future = asyncio.run_coroutine_threadsafe(
                asyncio.wait_for(
                    self._run_with_mcp_connection(goal, thread_id, context or {}, progress_callback=progress_callback),
                    timeout=timeout
                ),
                loop
            )
            result = future.result()
            
            # 构建响应
            response = self._build_response(result)
            
            logger.info(f"[OCO Adapter] 任务执行完成")
            return {
                "success": True,
                "response": response,
                "state": result
            }
            
        except asyncio.TimeoutError:
            logger.error(f"[OCO Adapter] 执行超时（{timeout} 秒）")
            return {
                "success": False,
                "error": f"执行超时（{timeout} 秒）",
                "response": "任务执行超时，请尝试简化任务或稍后再试。"
            }
        except Exception as e:
            logger.error(f"[OCO Adapter] 执行失败：{e}")
            import traceback
            traceback.print_exc()
            return {
                "success": False,
                "error": str(e),
                "response": f"任务执行失败：{str(e)}"
            }
    
    def _build_response(self, state: Dict[str, Any]) -> str:
        """
        从状态构建响应文本
        
        Args:
            state: OmegaState
        
        Returns:
            str: 响应文本
        """
        # 如果上下文中存在 Aggregator 生成的最终总结，优先使用它
        context = state.get("context", {})
        if "final_response" in context and context["final_response"]:
            return context["final_response"]
            
        response_parts = []
        
        # 添加目标
        goal = state.get("goal", "")
        if goal:
            response_parts.append(f"**任务**: {goal}")
        
        # 添加子任务结果
        subtask_results = state.get("subtask_results", [])
        if subtask_results:
            response_parts.append("\n**执行结果**:")
            for result in subtask_results:
                if hasattr(result, 'result'):
                    response_parts.append(f"- {result.result}")
                else:
                    response_parts.append(f"- {result}")
        
        # 添加认知追踪（可选，用于调试）
        cognitive_trace = state.get("cognitive_trace", [])
        if cognitive_trace and len(cognitive_trace) > 0:
            response_parts.append("\n**认知轨迹**:")
            for trace in cognitive_trace[-3:]:  # 只显示最后 3 条
                response_parts.append(f"  - {trace}")
        
        # 添加错误信息
        error_count = state.get("error_count", 0)
        if error_count > 0:
            response_parts.append(f"\n⚠️ 执行过程中遇到 {error_count} 个错误，已尝试自动恢复。")
        
        return "\n\n".join(response_parts) if response_parts else "任务已完成。"
    
    def get_state(self, thread_id: str) -> Optional[Dict[str, Any]]:
        """
        获取指定线程的状态
        
        Args:
            thread_id: 线程 ID
        
        Returns:
            Optional[Dict[str, Any]]: 状态，如果不存在则返回 None
        """
        if not self.initialized or not self.cognitive_graph:
            return None
        
        loop = get_global_loop()
        
        try:
            future = asyncio.run_coroutine_threadsafe(
                self.cognitive_graph.app.aget_state({"configurable": {"thread_id": thread_id}}),
                loop
            )
            state_snapshot = future.result(timeout=10)
            return state_snapshot.values if state_snapshot.values else None
        except Exception as e:
            logger.error(f"[OCO Adapter] 获取状态失败：{e}")
            return None
    
    def close(self):
        """
        关闭适配器，释放资源
        """
        if self.mcp_client:
            try:
                loop = get_global_loop()
                future = asyncio.run_coroutine_threadsafe(self.mcp_client.disconnect_all(), loop)
                future.result(timeout=5)
            except Exception as e:
                logger.warning(f"[OCO Adapter] 关闭 MCP 客户端失败：{e}")
        
        self.initialized = False
        logger.info("[OCO Adapter] 已关闭")


# 全局适配器实例
_adapter_instance: Optional[OCOCognitiveLoopAdapter] = None


def get_oco_adapter() -> Optional[OCOCognitiveLoopAdapter]:
    """
    获取全局 OCO 适配器实例
    
    Returns:
        Optional[OCOCognitiveLoopAdapter]: 适配器实例
    """
    global _adapter_instance
    
    if _adapter_instance is None:
        _adapter_instance = OCOCognitiveLoopAdapter()
    
    return _adapter_instance


def run_oco_cognitive_loop(goal: str, thread_id: str, context: Dict[str, Any] = None, progress_callback=None) -> Dict[str, Any]:
    """
    便捷函数：运行 OCO 认知闭环
    
    Args:
        goal: 目标/任务描述
        thread_id: 线程 ID
        context: 上下文信息
        progress_callback: 进度回调函数，签名：callback(stage: str, detail: str, progress: float)
    
    Returns:
        Dict[str, Any]: 执行结果
    """
    adapter = get_oco_adapter()
    
    if not adapter or not adapter.initialized:
        logger.warning("[OCO] 适配器未初始化，返回占位响应")
        error_msg = IMPORT_ERROR_MSG if not OCO_CORE_AVAILABLE else "初始化失败，请检查日志"
        return {
            "success": False,
            "error": "OCO 认知闭环未初始化",
            "response": f"[OCO 认知闭环] 任务已接收（thread_id: {thread_id}）。\n\n系统正在调试中，请稍后重试。\n(诊断信息: {error_msg})"
        }
    
    return adapter.run(goal, thread_id, context, progress_callback=progress_callback)
