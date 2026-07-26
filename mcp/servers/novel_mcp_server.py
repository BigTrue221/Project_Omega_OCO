# -*- coding: utf-8 -*-
"""
Novel MCP Server - 纯 JSON-RPC 实现 (同步 I/O 版本)
"""
import sys
import json
import logging
import threading
import urllib.request
from typing import Dict, Any, Optional

# 延迟导入以防止干扰标准库 mcp
def get_logger():
    import importlib.util
    from pathlib import Path
    PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
    module_name = "tool_call_logger"
    file_path = str(PROJECT_ROOT / "Project_Omega_OCO" / "mcp" / "utils" / "tool_call_logger.py")
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.get_logger()

logging.basicConfig(level=logging.INFO, format='%(message)s', stream=sys.stderr)
logger = logging.getLogger("Novel_MCP_Server")


class LangGraphClient:
    def __init__(self, base_url: str = "http://127.0.0.1:5005"):
        self.base_url = base_url

    def _post(self, endpoint: str, data: Dict[str, Any], timeout: int = 300) -> Dict[str, Any]:
        try:
            url = f"{self.base_url}{endpoint}"
            payload = json.dumps(data).encode('utf-8')
            req = urllib.request.Request(url, data=payload, headers={'Content-Type': 'application/json'})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode('utf-8'))
        except Exception as e:
            return {"error": str(e)}

    def _get(self, endpoint: str, timeout: int = 30) -> Dict[str, Any]:
        try:
            url = f"{self.base_url}{endpoint}"
            with urllib.request.urlopen(url, timeout=timeout) as resp:
                return json.loads(resp.read().decode('utf-8'))
        except Exception as e:
            return {"error": str(e)}

    def create_session(self, topic: str, sender_id: str) -> str:
        result = self._post("/session/create", {"topic": topic, "sender_id": sender_id})
        return result.get("thread_id", str(result))

    def continue_session(self, thread_id: str, message: str, sender_id: str) -> Dict[str, Any]:
        return self._post(f"/session/{thread_id}/continue", {"message": message, "sender_id": sender_id})

    def get_state(self, thread_id: str) -> Dict[str, Any]:
        return self._get(f"/session/{thread_id}/state")

    def get_nodes(self) -> list:
        result = self._get("/nodes")
        if isinstance(result, list):
            return result
        return result.get("nodes", [])

    def goto_node(self, thread_id: str, node_name: str, data: Dict[str, Any] = None) -> Dict[str, Any]:
        return self._post(f"/session/{thread_id}/goto", {"node": node_name, "data": data or {}})


TOOLS = [
    {"name": "generate_outline", "description": "生成小说大纲（后台异步工具。调用成功返回 thread_id 后，任务即宣告成功完成，切勿等待或索要大纲文本！）", "inputSchema": {"type": "object", "properties": {"topic": {"type": "string"}, "style": {"type": "string"}, "chapters": {"type": "integer"}, "sender_id": {"type": "string"}}, "required": ["topic"]}},
    {"name": "write_chapter", "description": "写作指定章节（后台异步工具）", "inputSchema": {"type": "object", "properties": {"thread_id": {"type": "string"}, "chapter_index": {"type": "integer"}, "feedback": {"type": "string"}, "sender_id": {"type": "string"}}, "required": ["thread_id", "chapter_index"]}},
    {"name": "revise_chapter", "description": "修订章节", "inputSchema": {"type": "object", "properties": {"thread_id": {"type": "string"}, "chapter_index": {"type": "integer"}, "feedback": {"type": "string"}, "sender_id": {"type": "string"}}, "required": ["thread_id", "chapter_index", "feedback"]}},
    {"name": "review_chapter", "description": "审核章节", "inputSchema": {"type": "object", "properties": {"thread_id": {"type": "string"}, "chapter_index": {"type": "integer"}, "sender_id": {"type": "string"}}, "required": ["thread_id", "chapter_index"]}},
    {"name": "get_state", "description": "获取会话状态", "inputSchema": {"type": "object", "properties": {"thread_id": {"type": "string"}}, "required": ["thread_id"]}},
    {"name": "goto_node", "description": "跳转到指定节点", "inputSchema": {"type": "object", "properties": {"thread_id": {"type": "string"}, "node_name": {"type": "string"}, "data": {"type": "object"}}, "required": ["thread_id", "node_name"]}},
    {"name": "list_nodes", "description": "列出所有可用节点", "inputSchema": {"type": "object", "properties": {}}},
    {"name": "confirm_and_continue", "description": "确认并继续", "inputSchema": {"type": "object", "properties": {"thread_id": {"type": "string"}, "sender_id": {"type": "string"}}, "required": ["thread_id"]}}
]


class JSONRPCServer:
    def __init__(self, client: LangGraphClient):
        self.client = client
        self.protocol_version = "2024-11-05"

    def handle_request(self, request: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        method = request.get("method")
        req_id = request.get("id")

        if method == "initialize":
            result = {
                "protocolVersion": self.protocol_version,
                "capabilities": {
                    "logging": {},
                    "tools": {"listChanged": False},
                    "prompts": {"listChanged": False},
                    "resources": {"subscribe": False, "listChanged": False}
                },
                "serverInfo": {"name": "Novel_LangGraph", "version": "1.0.0"}
            }
            return {"jsonrpc": "2.0", "id": req_id, "result": result}

        elif method == "notifications/initialized":
            return None

        elif method == "tools/list":
            return {"jsonrpc": "2.0", "id": req_id, "result": {"tools": TOOLS}}

        elif method == "tools/call":
            params = request.get("params", {})
            tool_name = params.get("name")
            arguments = params.get("arguments", {})
            try:
                result = self.call_tool(tool_name, arguments)
                return {"jsonrpc": "2.0", "id": req_id, "result": {"content": [{"type": "text", "text": result}]}}
            except Exception as e:
                return {"jsonrpc": "2.0", "id": req_id, "result": {"content": [{"type": "text", "text": json.dumps({"error": str(e)})}], "isError": True}}

        elif method == "resources/list":
            return {"jsonrpc": "2.0", "id": req_id, "result": {"resources": []}}

        elif method == "ping":
            return {"jsonrpc": "2.0", "id": req_id, "result": None}

        return {"jsonrpc": "2.0", "id": req_id, "error": {"code": -32601, "message": f"Method not found: {method}"}}

    def call_tool(self, name: str, arguments: Dict[str, Any]) -> str:
        if name == "generate_outline":
            thread_id = self.client.create_session(arguments["topic"], arguments.get("sender_id", "default"))
            return json.dumps({"thread_id": thread_id, "status": "outline_generating"})
        elif name == "write_chapter":
            message = f"写第{arguments['chapter_index']}章" if not arguments.get("feedback") else arguments["feedback"]
            self.client.continue_session(arguments["thread_id"], message, arguments.get("sender_id", "default"))
            return json.dumps({"thread_id": arguments["thread_id"], "status": "chapter_writing"})
        elif name == "revise_chapter":
            self.client.continue_session(arguments["thread_id"], arguments["feedback"], arguments.get("sender_id", "default"))
            return json.dumps({"thread_id": arguments["thread_id"], "status": "chapter_revising"})
        elif name == "review_chapter":
            self.client.continue_session(arguments["thread_id"], f"审核第{arguments['chapter_index']}章", arguments.get("sender_id", "default"))
            return json.dumps({"thread_id": arguments["thread_id"], "status": "chapter_reviewing"})
        elif name == "get_state":
            state = self.client.get_state(arguments["thread_id"])
            return json.dumps(state, ensure_ascii=False)
        elif name == "goto_node":
            self.client.goto_node(arguments["thread_id"], arguments["node_name"], arguments.get("data", {}))
            return json.dumps({"status": "node_jumped"})
        elif name == "list_nodes":
            nodes = self.client.get_nodes()
            return json.dumps(nodes, ensure_ascii=False)
        elif name == "confirm_and_continue":
            self.client.continue_session(arguments["thread_id"], "y", arguments.get("sender_id", "default"))
            return json.dumps({"status": "continued"})
        else:
            return json.dumps({"error": f"未知工具: {name}"})


def main():
    client = LangGraphClient()
    server = JSONRPCServer(client)

    logger.info("✅ Novel MCP Server 初始化成功")
    logger.info("🚀 Novel MCP Server 启动中...")
    logger.info(f"🔗 LangGraph API: {client.base_url}")
    sys.stderr.flush()

    while True:
        try:
            line = sys.stdin.buffer.readline()
            if not line:
                break

            try:
                line_str = line.decode("utf-8")
                logger.info(f"收到请求: {line_str.strip()}")
                request = json.loads(line_str)
            except json.JSONDecodeError as e:
                logger.error(f"JSON 解析错误: {e}")
                continue

            response = server.handle_request(request)
            if response:
                response_str = json.dumps(response)
                logger.info(f"发送响应: {response_str}")
                response_line = (response_str + "\n").encode("utf-8")
                sys.stdout.buffer.write(response_line)
                sys.stdout.flush()

        except Exception as e:
            logger.error(f"处理请求时出错: {e}")


if __name__ == "__main__":
    main()