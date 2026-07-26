# -*- coding: utf-8 -*-
"""
Video MCP Server
视频创作领域的 MCP Server，提供视频脚本生成和分镜创建能力。

这是 OCO 统一架构的领域扩展验证原型，证明新领域只需添加 MCP Server 即可集成。

架构：
OCO Planner → MCP Client → Video MCP Server → 视频创作工具
"""

import os
import sys
import json
import logging
from typing import Dict, Any, List
from pathlib import Path
from pydantic import BaseModel

# 添加项目根目录到路径
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

try:
    from mcp.server.fastmcp import FastMCP
    from AI_Ori.Project_Omega_OCO.core.llm import LLMClient
    MCP_AVAILABLE = True
except ImportError as e:
    MCP_AVAILABLE = False
    FastMCP = None
    LLMClient = None
    print(f"⚠️ 导入失败：{e}")

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

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("Video_MCP_Server")


# ==========================================
# MCP 工具输入模型定义
# ==========================================

class GenerateScriptInput(BaseModel):
    """生成视频脚本的输入参数"""
    topic: str  # 视频主题
    style: str = "documentary"  # 风格：documentary, vlog, tutorial, short_video
    duration: int = 180  # 目标时长（秒）
    language: str = "zh-CN"  # 语言

class CreateStoryboardInput(BaseModel):
    """创建分镜的输入参数"""
    script: str  # 视频脚本
    shots: int = 10  # 分镜数量


class GenerateThumbnailInput(BaseModel):
    """生成缩略图描述的输入参数"""
    topic: str  # 视频主题
    style: str = "clickbait"  # 风格：clickbait, minimalist, artistic


# ==========================================
# Video MCP Server 主类
# ==========================================

class VideoMCPServer:
    """
    Video MCP Server
    
    提供视频创作相关的 MCP 工具：
    1. generate_script: 生成视频脚本
    2. create_storyboard: 创建分镜
    3. generate_thumbnail: 生成缩略图描述
    """
    
    def __init__(self):
        if not MCP_AVAILABLE:
            raise ImportError("请先安装 mcp 库：pip install mcp")
        
        self.mcp = FastMCP("Video_Creator")
        self.llm = LLMClient()
        self._setup_tools()
    
    def _setup_tools(self):
        """定义并注册视频创作工具"""
        
        @self.mcp.tool()
        async def generate_script(input: GenerateScriptInput) -> str:
            """
            生成视频脚本
            
            根据主题、风格和时长生成完整的视频脚本，
            包含开场、主体内容、结尾等部分。
            """
            logger.info(f"[Video MCP] 生成脚本：{input.topic[:50]}...")
            
            try:
                # 构建系统提示
                style_prompts = {
                    "documentary": "你是一个专业的纪录片编剧。请生成一个结构严谨、信息丰富的纪录片脚本。",
                    "vlog": "你是一个受欢迎的 Vlogger。请生成一个亲切自然、有个人风格的 Vlog 脚本。",
                    "tutorial": "你是一个专业的教程创作者。请生成一个步骤清晰、易于理解的教程脚本。",
                    "short_video": "你是一个短视频创作者。请生成一个节奏快、吸引力强的短视频脚本。"
                }
                
                system_prompt = f"""{style_prompts.get(input.style, style_prompts['documentary'])}

请根据以下要求生成视频脚本：
- 主题：{input.topic}
- 目标时长：{input.duration}秒
- 语言：{input.language}

【脚本结构要求】
1. 开场（Hook）- 前 5-10 秒，吸引观众注意力
2. 引入（Intro）- 介绍主题和背景
3. 主体内容（Body）- 核心信息/故事
4. 结尾（Outro）- 总结和号召行动

【输出格式】
使用 JSON 格式输出：
{{
    "title": "视频标题",
    "hook": "开场白",
    "intro": "引入部分",
    "body": ["主体内容段落 1", "主体内容段落 2", ...],
    "outro": "结尾部分",
    "call_to_action": "号召行动"
}}
"""
                
                user_prompt = f"请为主题「{input.topic}」生成一个{input.duration}秒的视频脚本。"
                
                # 调用 LLM 生成脚本
                result = self.llm.chat(system_prompt, user_prompt)
                
                # 尝试解析 JSON
                try:
                    # 提取 JSON 部分
                    import re
                    json_match = re.search(r'\{.*\}', result, re.DOTALL)
                    if json_match:
                        script_data = json.loads(json_match.group(0))
                    else:
                        script_data = {"raw_script": result}
                except json.JSONDecodeError:
                    script_data = {"raw_script": result}
                
                logger.info(f"[Video MCP] 脚本生成成功")
                return json.dumps(script_data, ensure_ascii=False, indent=2)
                
            except Exception as e:
                logger.error(f"[Video MCP] 脚本生成失败：{e}")
                return json.dumps({
                    "success": False,
                    "error": str(e),
                    "message": f"视频脚本生成失败：{str(e)}"
                }, ensure_ascii=False, indent=2)
        
        @self.mcp.tool()
        async def create_storyboard(input: CreateStoryboardInput) -> str:
            """
            创建分镜
            
            根据视频脚本生成详细的分镜描述，
            包含画面、台词、时长等信息。
            """
            logger.info(f"[Video MCP] 创建分镜：{input.shots}个镜头")
            
            try:
                system_prompt = f"""你是一个专业的分镜师。请根据视频脚本生成详细的分镜描述。

【分镜格式要求】
每个分镜包含：
- shot_number: 镜头编号
- visual: 画面描述
- audio: 台词/音效
- duration: 时长（秒）
- camera: 镜头运动（可选）

请生成 {input.shots} 个分镜，使用 JSON 格式输出。
"""
                
                user_prompt = f"""根据以下脚本创建分镜：

{input.script}

请生成 {input.shots} 个详细的分镜描述。"""
                
                # 调用 LLM 生成分镜
                result = self.llm.chat(system_prompt, user_prompt)
                
                # 尝试解析 JSON
                try:
                    import re
                    json_match = re.search(r'\[.*\]|\{.*\}', result, re.DOTALL)
                    if json_match:
                        storyboard_data = json.loads(json_match.group(0))
                    else:
                        storyboard_data = {"raw_storyboard": result}
                except json.JSONDecodeError:
                    storyboard_data = {"raw_storyboard": result}
                
                logger.info(f"[Video MCP] 分镜创建成功")
                return json.dumps(storyboard_data, ensure_ascii=False, indent=2)
                
            except Exception as e:
                logger.error(f"[Video MCP] 分镜创建失败：{e}")
                return json.dumps({
                    "success": False,
                    "error": str(e),
                    "message": f"分镜创建失败：{str(e)}"
                }, ensure_ascii=False, indent=2)
        
        @self.mcp.tool()
        async def generate_thumbnail(input: GenerateThumbnailInput) -> str:
            """
            生成缩略图描述
            
            根据视频主题生成吸引人的缩略图设计描述，
            可用于 AI 图像生成工具。
            """
            logger.info(f"[Video MCP] 生成缩略图描述：{input.topic[:50]}...")
            
            try:
                style_prompts = {
                    "clickbait": "生成一个高点击率的 YouTube 风格缩略图描述，包含夸张的表情、醒目的文字和对比强烈的颜色。",
                    "minimalist": "生成一个简约风格的缩略图描述，使用干净的布局和有限的颜色。",
                    "artistic": "生成一个艺术风格的缩略图描述，注重美学和创意表达。"
                }
                
                system_prompt = f"""{style_prompts.get(input.style, style_prompts['clickbait'])}

请生成一个详细的缩略图设计描述，包括：
- 主要视觉元素
- 文字内容（标题）
- 颜色方案
- 构图建议

使用 JSON 格式输出。
"""
                
                user_prompt = f"为视频主题「{input.topic}」生成缩略图设计描述。"
                
                # 调用 LLM 生成缩略图描述
                result = self.llm.chat(system_prompt, user_prompt)
                
                # 尝试解析 JSON
                try:
                    import re
                    json_match = re.search(r'\{.*\}', result, re.DOTALL)
                    if json_match:
                        thumbnail_data = json.loads(json_match.group(0))
                    else:
                        thumbnail_data = {"raw_description": result}
                except json.JSONDecodeError:
                    thumbnail_data = {"raw_description": result}
                
                logger.info(f"[Video MCP] 缩略图描述生成成功")
                return json.dumps(thumbnail_data, ensure_ascii=False, indent=2)
                
            except Exception as e:
                logger.error(f"[Video MCP] 缩略图描述生成失败：{e}")
                return json.dumps({
                    "success": False,
                    "error": str(e),
                    "message": f"缩略图描述生成失败：{str(e)}"
                }, ensure_ascii=False, indent=2)
    
    def run(self):
        """启动 MCP Server"""
        logger.info("🎬 Video MCP Server 启动中...")
        logger.info("📚 可用工具:")
        logger.info("  - generate_script: 生成视频脚本")
        logger.info("  - create_storyboard: 创建分镜")
        logger.info("  - generate_thumbnail: 生成缩略图描述")
        self.mcp.run()


if __name__ == "__main__":
    server = VideoMCPServer()
    server.run()
