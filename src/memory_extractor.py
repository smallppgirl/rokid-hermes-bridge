"""
通用记忆提取模块（可选）
=========================
从对话中自动提取值得记住的信息，写入记忆系统。

支持后端：
- mnemosyne（默认）：通过 Mnemosyne Python API 存储

启用方式：在 .env 中设置 ENABLE_MEMORY_EXTRACTOR=true
"""

import os
import json
import logging
import asyncio
import httpx
from typing import Protocol, Dict, List
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger("memory-extractor")

# ── 配置 ──────────────────────────────────────────────
HERMES_GATEWAY_URL = os.getenv("HERMES_GATEWAY_URL", "http://localhost:8642")
HERMES_MODEL = os.getenv("HERMES_MODEL", "mimo-v2.5")
HERMES_API_KEY = os.getenv("HERMES_API_KEY", "").strip()
MEMORY_BACKEND = os.getenv("MEMORY_BACKEND", "mnemosyne").lower()


# ── 后端抽象 ──────────────────────────────────────────
class MemoryBackend(Protocol):
    def store(self, content: str, source: str, importance: float, session_id: str) -> bool: ...


class MnemosyneBackend:
    """Mnemosyne 后端 —— 通过官方 Python API 存储"""
    def store(self, content: str, source: str = "rokid-glasses",
              importance: float = 0.8, session_id: str = "default") -> bool:
        try:
            from mnemosyne import remember
            remember(content, source=source, importance=importance, scope="global",
                     metadata={"session_id": session_id})
            logger.info(f"记忆已写入 Mnemosyne: {content[:60]}...")
            return True
        except Exception as e:
            logger.error(f"写入 Mnemosyne 失败: {e}")
            return False


BACKENDS: Dict[str, type] = {"mnemosyne": MnemosyneBackend}


def _get_backend() -> MemoryBackend:
    cls = BACKENDS.get(MEMORY_BACKEND)
    if cls is None:
        logger.warning(f"未知后端 '{MEMORY_BACKEND}'，回退到 mnemosyne")
        cls = MnemosyneBackend
    return cls()


# ── 记忆提取提示 ──────────────────────────────────────
MEMORY_EXTRACTION_PROMPT = """你是一个记忆提取器。你的任务是从对话中提取值得长期记住的信息。

规则：
1. 只提取**持久性事实**——用户的身份、偏好、习惯、重要关系、长期目标等
2. 不要提取临时性信息（如"今天天气"、"帮我查个东西"）
3. 不要提取 AI 自己的回复内容
4. 每条记忆用一句话概括，简洁明确
5. 如果对话中没有值得记住的信息，返回空数组 []

输出格式（严格 JSON）：
{"memories": ["记忆1", "记忆2"]}

只输出 JSON，不要输出其他内容。"""


async def _call_llm_for_extraction(user_msg: str, assistant_msg: str) -> List[str]:
    """调用 LLM 提取记忆"""
    prompt = f"以下是用户和 AI 助手的对话：\n\n用户：{user_msg}\nAI：{assistant_msg}\n\n请提取值得长期记住的用户信息。"
    try:
        client = httpx.AsyncClient(timeout=httpx.Timeout(30.0))
        try:
            headers = {"Content-Type": "application/json"}
            if HERMES_API_KEY:
                headers["Authorization"] = f"Bearer {HERMES_API_KEY}"
            response = await client.post(
                f"{HERMES_GATEWAY_URL}/v1/chat/completions",
                json={
                    "model": HERMES_MODEL,
                    "messages": [
                        {"role": "system", "content": MEMORY_EXTRACTION_PROMPT},
                        {"role": "user", "content": prompt},
                    ],
                    "temperature": 0.1, "max_tokens": 200,
                },
                headers=headers,
            )
            if response.status_code != 200:
                logger.error(f"LLM 调用失败: {response.status_code}")
                return []
            result = response.json()
            content = result["choices"][0]["message"]["content"].strip()
            if content.startswith("```"):
                content = content.split("```")[1]
                if content.startswith("json"):
                    content = content[4:]
                content = content.strip()
            data = json.loads(content)
            return [m for m in data.get("memories", []) if m and isinstance(m, str)]
        finally:
            await client.aclose()
    except Exception as e:
        logger.error(f"记忆提取失败: {e}")
        return []


async def extract_and_store(user_msg: str, assistant_msg: str, user_id: str = "default") -> List[str]:
    """从对话中提取记忆并通过配置的后端存储"""
    try:
        memories = await _call_llm_for_extraction(user_msg, assistant_msg)
        if not memories:
            return []
        backend = _get_backend()
        session_id = f"rokid:{user_id}"
        stored = []
        for memory in memories:
            if backend.store(memory, source="rokid-glasses", importance=0.8, session_id=session_id):
                stored.append(memory)
        if stored:
            logger.info(f"从眼镜对话中提取了 {len(stored)} 条记忆（后端: {MEMORY_BACKEND}）")
        return stored
    except Exception as e:
        logger.error(f"记忆提取流程异常: {e}")
        return []
