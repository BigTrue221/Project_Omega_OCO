# OCO 架构修复行动指南：纠正 MCP 客户端与异步模式的反模式

> 本文档基于对 `OCO_调试复盘_20260409.md` 的深度评估，提供了一份详尽的行动指南，旨在纠正系统中存在的协议级偏差和 Python 异步编程隐患，恢复系统的标准化与稳定性。

## 一、 背景与现状分析

在之前的调试中，为了解决 `session.initialize()` 挂起的问题，系统做出了两项危险的架构妥协：
1. **废弃标准 MCP Client**：移除了官方 `mcp` 库，手写了 `simple_client.py`，放弃了 Pydantic 校验。这导致 `novel_mcp_server.py` 变成了不兼容标准 MCP 生态的“伪 MCP”。
2. **危险的异常捕获**：在 `bot_server.py` 等文件中使用了 `except BaseException:`，这会吞掉任务取消和进程退出信号，导致僵尸进程和内存泄漏。

**目标**：回退非标实现，修复真正的 Schema 错误，并加固异步代码。

---

## 二、 详细行动计划

### 步骤 1：回退并修复 Server 端数据结构

问题的根源在于 `novel_mcp_server.py` 返回的 JSON 缺少官方 `mcp` 库 Pydantic 模型所要求的必填字段。

**操作**：
1. **删除非标文件**：删除 `project_omega_oco/mcp/simple_client.py`。
2. **恢复官方依赖**：确保在虚拟环境中安装官方 `mcp` 库（如 `pip install mcp`）。
3. **修改 `client.py`**：将 `project_omega_oco/mcp/client.py` 回退到使用官方 `mcp.ClientSession` 和 `stdio_client` 的版本。如果需要，参考 `fastmcp` 兼容版本。
4. **修改 `novel_mcp_server.py`**：恢复使用官方 `mcp.server.Server` 框架。如果必须手写 JSON-RPC Server，必须严格对齐 `mcp` 协议规范。例如，在 `initialize` 响应中，必须包含：
   ```json
   {
     "jsonrpc": "2.0",
     "id": 1,
     "result": {
       "protocolVersion": "2024-11-05",
       "capabilities": {},
       "serverInfo": {
         "name": "novel_mcp_server",
         "version": "1.0.0"
       }
     }
   }
   ```

### 步骤 2：修复 `bot_server.py` 中的全局异常捕获

在 `bot_server.py` 的 `process_message_async` 函数中，使用了危险的 `except BaseException`，这会阻止正常的进程中断和任务取消。

**操作文件**：`d:\AI\AI_Ori\Project_Omega\cloud_brain\bot_server.py`

**修改内容**：
定位到文件第 937 行附近：
```python
# 修改前
    except BaseException as e:
        logging.error(f"Async processing failed for event {event_id}: {e}")
        if sender_id:
            reply_to_feishu(sender_id, f"Error processing request: {str(e)}")

# 修改后
    except asyncio.CancelledError:
        logging.warning(f"Async processing was cancelled for event {event_id}")
        # 如果当前在协程中，应该 raise 重新抛出；如果是普通线程（如当前代码），记录日志即可
    except Exception as e:
        logging.error(f"Async processing failed for event {event_id}: {e}")
        if sender_id:
            reply_to_feishu(sender_id, f"Error processing request: {str(e)}")
```
*(注：另外需全库搜索并替换所有其他的 `except BaseException:`)*

### 步骤 3：修复 `client.py` 中 `asyncio.create_task` 的内存泄漏隐患

在 `client.py` 的 `disconnect_all` 函数中，创建了 task 但没有等待，导致垃圾回收（GC）在任务执行中途将其杀掉。

**操作文件**：`d:\AI\AI_Ori\project_omega_oco\mcp\client.py`

**修改内容**：
定位到文件第 130 行附近的 `disconnect_all` 函数。
注意：由于我们计划在步骤 1 中重写 `client.py` 以使用官方库，这一步适用于重写后的代码。如果继续保留当前架构，应做如下修改：

```python
# 修改前 (client.py 第 134 行)
        for client in self.servers.values():
            try:
                loop.run_until_complete(client.disconnect())
            except Exception:
                pass

# 修改后 (推荐的异步清理模式，需结合外层异步调用)
# 如果 disconnect_all 被改为 async def：
    async def disconnect_all(self):
        tasks = []
        for client in self.servers.values():
            tasks.append(asyncio.create_task(client.disconnect()))
        
        if tasks:
            # 强引用等待所有清理任务完成，避免被 GC
            await asyncio.gather(*tasks, return_exceptions=True)
            
        self.servers.clear()
        # ... 清理其他字典 ...
```

---

## 三、 执行验证清单

执行完上述修改后，请进行以下验证：

- [ ] **服务启动测试**：启动 LangGraph API、MCP Server 和 Bot Server，确认无语法或模块导入错误。
- [ ] **MCP 握手测试**：触发一次飞书消息，观察 `bot_server` 日志，确认 `session.initialize()` 能够顺利通过，不再出现永久挂起或超时。
- [ ] **进程退出测试**：在 WSL/Tmux 中按 `Ctrl+C` 终止 `bot_server`，确认进程能迅速且彻底地退出，不留僵尸进程（因为 `BaseException` 已被移除）。
- [ ] **功能测试**：验证 OCO 认知闭环是否能正常调用小说生成等工具并返回结果给飞书。

## 四、 核心原则总结

1. **协议重于实现**：遇到 SDK 抛出的协议校验错误时，永远优先检查自身发送的数据是否符合 Schema，而不是去修改 SDK 绕过校验。
2. **敬畏异常层次**：永远不要使用 `except BaseException:` 除非你明确知道自己在编写最顶层的系统守护进程框架并打算手动处理退出信号。
3. **管理任务生命周期**：在 Python 3.11+ 中，必须对 `asyncio.create_task()` 创建的任务保持**强引用**，或者使用 `asyncio.TaskGroup`，绝不能即发即弃（Fire-and-forget）。
