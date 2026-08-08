# -*- coding: utf-8 -*-
"""
LLM Interface
统一 LLM 调用接口：负责与底层模型通信，提供结构化输出支持。
"""

import os
import json
import logging
from pathlib import Path
import subprocess
from typing import Dict, Any, List, Optional

logger = logging.getLogger("OCO_LLM")


def _load_dotenv_if_present() -> None:
    """Load optional project settings without overriding shell variables."""
    env_path = Path(__file__).resolve().parent.parent / ".env"
    if not env_path.is_file():
        return
    try:
        for raw in env_path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value
    except OSError as exc:
        logger.warning("Failed to read .env: %s", exc)


_load_dotenv_if_present()


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or not str(raw).strip():
        return default
    try:
        return int(str(raw).strip())
    except ValueError:
        logger.warning("Invalid int for %s=%r, using default %s", name, raw, default)
        return default


class LLMClient:
    """
    OCO 统一 LLM 客户端
    支持本地模型与云端模型切换，确保输出格式可控。
    """
    def __init__(self):
        # 从环境变量加载配置
        self.api_key = os.getenv("OPENROUTER_API_KEY")
        self.model = os.getenv("OPENROUTER_MODEL", "google/gemini-2.0-flash-001")
        # llama.cpp remains the default; Ollama is an explicit opt-in backend.
        self.local_provider = os.getenv("OCO_LOCAL_LLM_PROVIDER", "llama.cpp").strip().lower()
        self.local_url = os.getenv("OCO_LOCAL_LLM_URL", "http://127.0.0.1:8081/v1/chat/completions")
        default_model = "dolphin3-mistral-32k:latest" if self.local_provider == "ollama" else "qwen"
        self.local_model = os.getenv("OCO_LOCAL_LLM_MODEL", default_model)
        # These knobs belong exclusively to Ollama; llama.cpp keeps its
        # original request shape and 120-second timeout.
        self.ollama_num_ctx = _env_int("OCO_OLLAMA_NUM_CTX", 2048)
        self.ollama_timeout = _env_int("OCO_OLLAMA_TIMEOUT", 300)
        self.cloud_url = os.getenv("OPENROUTER_API_URL", "https://openrouter.ai/api/v1/chat/completions")

    @staticmethod
    def _is_ollama_native(url: str) -> bool:
        value = (url or "").lower()
        return "/api/chat" in value or value.rstrip("/").endswith("/api/generate")

    def _local_request_config(self):
        native = self.local_provider in {"ollama", "ollama-native"} or self._is_ollama_native(self.local_url)
        model = self.local_model
        # Ollama accepts the model name without the provider prefix.
        if native and model.startswith("ollama/"):
            model = model[len("ollama/") :]
        return self.local_url, model, native

    def _curl_post(self, url: str, headers: Dict[str, str], data: Dict[str, Any], timeout: int = 60, max_retries: int = 2) -> Optional[str]:
        """
        使用 curl 执行 POST 请求，保持与 bot_server 一致。
        
        Args:
            url: 请求 URL
            headers: 请求头
            data: 请求数据
            timeout: 超时时间（秒），默认 60 秒
            max_retries: 最大重试次数，默认 2 次
        """
        json_data = json.dumps(data)
        
        for attempt in range(max_retries + 1):
            cmd = ["curl", "-s", "-X", "POST", url]
            for k, v in headers.items():
                cmd.extend(["-H", f"{k}: {v}"])
            
            cmd.extend(["-d", "@-"])
            
            try:
                logger.info(f"[LLM][CURL] 尝试 {attempt + 1}/{max_retries + 1}，URL={url}, timeout={timeout}s")
                result = subprocess.run(
                    cmd,
                    input=json_data,
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                    encoding='utf-8'
                )
                if result.returncode == 0:
                    logger.info(f"[LLM][CURL] 请求成功")
                    return result.stdout
                else:
                    logger.error(f"[LLM][CURL] 请求失败，returncode={result.returncode}: {result.stderr}")
                    if attempt < max_retries:
                        logger.info(f"[LLM][CURL] 等待 2 秒后重试...")
                        import time
                        time.sleep(2)
                        continue
                    return None
            except subprocess.TimeoutExpired:
                logger.error(f"[LLM][CURL] 请求超时（{timeout}秒），尝试 {attempt + 1}/{max_retries + 1}")
                if attempt < max_retries:
                    logger.info(f"[LLM][CURL] 等待 2 秒后重试...")
                    import time
                    time.sleep(2)
                    continue
                return None
            except Exception as e:
                logger.error(f"[LLM][CURL] 异常：{e}")
                return None
        
        return None

    def chat(self, system_prompt: str, user_prompt: str, response_format: str = "text") -> str:
        """
        通用聊天接口（同步版本）
        """
        use_cloud = os.getenv("USE_CLOUD_LLM", "false").lower() == "true"
        
        if use_cloud:
            url = self.cloud_url
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            model = self.model
            native_ollama = False
            timeout = 120
        else:
            url, model, native_ollama = self._local_request_config()
            headers = {"Content-Type": "application/json"}
            timeout = self.ollama_timeout if native_ollama else 120

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]

        data = {
            "model": model,
            "messages": messages
        }

        if not use_cloud and native_ollama:
            data["options"] = {"num_ctx": self.ollama_num_ctx}
            data["stream"] = False
            logger.info(
                "[LLM] local provider=ollama model=%s num_ctx=%s timeout=%ss url=%s",
                model, self.ollama_num_ctx, timeout, url,
            )
        elif not use_cloud:
            logger.info(
                "[LLM] local provider=%s model=%s timeout=%ss url=%s",
                self.local_provider, model, timeout, url,
            )

        if response_format == "json_object":
            if native_ollama:
                data["format"] = "json"
            else:
                data["response_format"] = {"type": "json_object"}

        response_text = self._curl_post(url, headers, data, timeout=timeout)
        if not response_text:
            return "Error: No response from LLM"

        try:
            res = json.loads(response_text)
            if native_ollama or ("message" in res and "choices" not in res):
                content = (res.get("message") or {}).get("content")
            else:
                content = res["choices"][0]["message"]["content"]
            if content is None:
                return "Error: Empty content from LLM"
            return content
        except Exception as e:
            logger.error(f"Failed to parse LLM response: {e}")
            return f"Error: {str(e)}"

    def generate_json(self, system_prompt: str, user_prompt: str) -> Dict[str, Any]:
        """
        强制生成 JSON 格式的响应（同步版本）
        """
        content = self.chat(system_prompt, user_prompt, response_format="json_object")
        try:
            import re
            content = content.strip()
            if content.startswith('```json'): content = content[7:]
            if content.startswith('```'): content = content[3:]
            if content.endswith('```'): content = content[:-3]
            content = content.strip()
            json_match = re.search(r'\{.*\}', content, re.DOTALL)
            if json_match:
                return json.loads(json_match.group(0))
            return json.loads(content)
        except Exception as e:
            logger.error(f"JSON parse error: {e}")
            return {}
