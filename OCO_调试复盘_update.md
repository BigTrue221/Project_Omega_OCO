
### 第八阶段：LangGraph 异步 SQLite 初始化问题（2026-04-16 更新）

**问题现象**：通过飞书发送测试消息时，LangGraph 节点执行抛出运行时错误：
```
任务执行失败：object str can't be used in 'await' expression
```

**排查过程**：
1. 定位到错误发生在 `Project_Omega_OCO/core/graph.py` 中的 `AsyncSqliteSaver` 初始化。
2. 发现原有代码为 `self._memory = AsyncSqliteSaver(self.checkpoint_db_path)`，其中传入了一个字符串路径。
3. 根据 `langgraph.checkpoint.sqlite.aio` 的要求，`AsyncSqliteSaver` 必须接收一个已经建立的 `aiosqlite.Connection` 对象，而不能直接接收字符串路径。

**修复方案**：
修改 `graph.py`，先使用 `await aiosqlite.connect()` 建立连接，再将连接对象传给 `AsyncSqliteSaver`：
```python
import aiosqlite
self._conn = await aiosqlite.connect(self.checkpoint_db_path)
self._memory = AsyncSqliteSaver(self._conn)
```

### 第九阶段：MCP 客户端上下文管理的致命崩溃（2026-04-16 更新）

**问题现象**：在修复上述问题后，运行 `test_oco_end_to_end.py` 进行端到端测试时，程序在连接第二个 MCP 服务器（`internet_tools`）时没有任何报错直接退出（Exit Code 0）。

**排查过程**：
1. 逐步追踪发现，程序并非正常结束，而是遭遇了未被 `except Exception` 捕获的致命异常，最终导致 `asyncio.run()` 终止。
2. 深入测试发现，使用官方 `mcp` 库的 `stdio_client` 时，如果配合 `contextlib.AsyncExitStack` 来管理多个服务器的上下文生命周期，极易触发 `anyio` 内部的任务组（TaskGroup）状态冲突。
3. 具体的底层错误为：`RuntimeError: Attempted to exit a cancel scope that isn't the current tasks's current cancel scope`。当 `AsyncExitStack` 尝试以 LIFO 顺序关闭由 `anyio` 创建的子进程上下文时，如果事件循环的 TaskGroup 栈不匹配，就会抛出该错误，并迅速演变为 `SystemExit` 或未捕获异常导致父进程直接崩溃。

**修复方案**：
彻底放弃在 `OCO_MCPClient` 中使用 `AsyncExitStack`，改为显式手动调用异步生成器的 `__aenter__` 和 `__aexit__` 方法来管理 `stdio_client` 和 `ClientSession`。
```python
# 修复后的连接逻辑
ctx = stdio_client(server_params)
read, write = await ctx.__aenter__()
session = ClientSession(read, write)
await session.__aenter__()

# 修复后的清理逻辑
await session.__aexit__(None, None, None)
await ctx.__aexit__(None, None, None)
```
此方案完美绕过了 `anyio` 的 TaskGroup 生命周期校验问题，支持了多个 MCP 服务器的稳定并发连接。测试脚本 `test_oco_end_to_end.py` 最终成功跑通了整个 OCO 认知闭环。
