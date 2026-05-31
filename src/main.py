"""
Rokid 眼镜 → Hermes Agent 桥接服务
====================================
接收 Rokid 灵珠平台的 SSE 请求，通过 Hermes Gateway API 流式转发。

功能：
  1. HTTP 连接池复用（全局 client，避免每次请求重新握手）
  2. 连接 keepalive（减少 TLS 开销）
  3. 多轮对话上下文（最近 N 轮，按 user_id 隔离）
  4. 图片识别（眼镜拍照 → base64 → 视觉模型）
  5. 语音适配（自动去 markdown，回复精简口语化）
  6. 自动重试（Gateway 失败时重试）
  7. SSE 心跳保活（防止 Cloudflare 100s 超时断连）
  8. 会话持久化（对话自动写入 Hermes session DB）
  9. 记忆提取（可选，对话结束后自动提取用户偏好写入记忆系统）

灵珠平台协议：
  GET  /health        → 健康检查
  POST /api/sse       → 接收用户语音文本/图片，返回 AI 回复（SSE 流式）
"""

import json
import os
import re
import base64
import asyncio
import logging
import time
import httpx
from collections import defaultdict
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Header
from fastapi.responses import StreamingResponse, JSONResponse
from typing import Optional, Union, Dict, List
from dotenv import load_dotenv
from session_store import store_conversation

# 可选：记忆提取（设 ENABLE_MEMORY_EXTRACTOR=true 启用）
_memory_extractor = None
if os.getenv("ENABLE_MEMORY_EXTRACTOR", "false").lower() == "true":
    try:
        from memory_extractor import extract_and_store
        _memory_extractor = extract_and_store
    except ImportError:
        pass

# 加载 .env 文件
load_dotenv()

# ── 配置 ──────────────────────────────────────────────
ROKID_AK = os.getenv("ROKID_AK", "").strip()             # 灵珠平台的鉴权密钥
PORT = int(os.getenv("BRIDGE_PORT", "8900"))              # 桥接服务端口
HERMES_GATEWAY_URL = os.getenv("HERMES_GATEWAY_URL", "http://localhost:8642")
HERMES_MODEL = os.getenv("HERMES_MODEL", "mimo-v2.5")
HERMES_API_KEY = os.getenv("HERMES_API_KEY", "").strip()  # Gateway API key
MAX_IMAGE_SIZE = 5 * 1024 * 1024  # 5MB
MAX_HISTORY_ROUNDS = 5            # 保留最近 5 轮对话（10 条消息）
SSE_HEARTBEAT_INTERVAL = 30       # SSE 心跳间隔（秒）
MAX_RETRIES = 1                   # Gateway 失败重试次数

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("rokid-bridge")


# ── 全局 HTTP 连接池（复用 + keepalive）───────
_global_client: Optional[httpx.AsyncClient] = None


async def get_client() -> httpx.AsyncClient:
    """获取全局复用的 HTTP 客户端"""
    global _global_client
    if _global_client is None or _global_client.is_closed:
        _global_client = httpx.AsyncClient(
            timeout=httpx.Timeout(120.0, connect=10.0),
            limits=httpx.Limits(
                max_connections=20,
                max_keepalive_connections=10,
                keepalive_expiry=60.0,
            ),
        )
    return _global_client


@asynccontextmanager
async def lifespan(app):
    """应用生命周期管理"""
    yield
    global _global_client
    if _global_client and not _global_client.is_closed:
        await _global_client.aclose()


app = FastAPI(title="Rokid → Hermes Bridge", lifespan=lifespan)

# 按 user_id 隔离对话历史
_conversation_history: Dict[str, List[dict]] = defaultdict(list)


def get_history(user_id: str) -> list:
    return _conversation_history[user_id]


def add_to_history(user_id: str, role: str, content):
    """添加消息到历史，超过限制自动丢弃最早的"""
    history = _conversation_history[user_id]
    history.append({"role": role, "content": content})
    max_messages = MAX_HISTORY_ROUNDS * 2
    while len(history) > max_messages:
        history.pop(0)


def clear_history(user_id: str):
    """清空用户对话历史"""
    _conversation_history.pop(user_id, None)


# ── 语音适配：去除 markdown 格式 ───────────────
def strip_markdown_for_voice(text: str) -> str:
    if not text:
        return text
    text = re.sub(r'```[\s\S]*?```', lambda m: m.group(0).strip('`\n'), text)
    text = re.sub(r'`([^`]+)`', r'\1', text)
    text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)
    text = re.sub(r'\*(.+?)\*', r'\1', text)
    text = re.sub(r'__(.+?)__', r'\1', text)
    text = re.sub(r'_(.+?)_', r'\1', text)
    text = re.sub(r'^#{1,6}\s+', '', text, flags=re.MULTILINE)
    text = re.sub(r'^[\s]*[-*+]\s+', '', text, flags=re.MULTILINE)
    text = re.sub(r'^[\s]*\d+\.\s+', '', text, flags=re.MULTILINE)
    text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)
    text = re.sub(r'!\[([^\]]*)\]\([^)]+\)', r'（图片：\1）', text)
    text = re.sub(r'^[\s]*>\s?', '', text, flags=re.MULTILINE)
    text = re.sub(r'^[-*_]{3,}\s*$', '', text, flags=re.MULTILINE)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


# ── 健康检查 ──────────────────────────────────
@app.get("/health")
@app.get("/api/health")
async def health():
    return {
        "status": "ok",
        "service": "hermes-bridge",
        "version": "2.0.0",
        "active_sessions": len(_conversation_history),
    }


# ── 验证 AK ──────────────────────────────────
def verify_ak(authorization: Optional[str], api_key: Optional[str], body: dict) -> bool:
    if not ROKID_AK:
        return True
    if authorization:
        token = authorization.replace("Bearer ", "").strip()
        if token == ROKID_AK:
            return True
    if api_key and api_key.strip() == ROKID_AK:
        return True
    body_key = body.get("api_key") or body.get("ak") or body.get("apikey")
    if body_key and body_key.strip() == ROKID_AK:
        return True
    return False


# ── 下载图片并转 base64 ──────────────────────
async def download_image_as_base64(url: str) -> Optional[str]:
    try:
        client = await get_client()
        response = await client.get(url, follow_redirects=True)
        if response.status_code != 200:
            logger.warning(f"图片下载失败: {url} -> {response.status_code}")
            return None
        content_type = response.headers.get("content-type", "image/jpeg")
        if ";" in content_type:
            content_type = content_type.split(";")[0].strip()
        image_data = response.content
        if len(image_data) > MAX_IMAGE_SIZE:
            logger.warning(f"图片过大: {len(image_data)} bytes")
            return None
        b64 = base64.b64encode(image_data).decode("utf-8")
        return f"data:{content_type};base64,{b64}"
    except Exception as e:
        logger.error(f"图片下载失败: {url} -> {e}")
        return None


# ── 构建用户消息内容（支持文本+图片）──────────
async def build_user_content(body: dict) -> Union[str, list]:
    raw_messages = body.get("message", [])
    if not isinstance(raw_messages, list) or len(raw_messages) == 0:
        return body.get("text") or body.get("query") or body.get("content") or body.get("input") or ""

    text_parts = []
    image_parts = []

    for msg in raw_messages:
        if not isinstance(msg, dict):
            continue
        msg_type = msg.get("type", "text")

        if msg_type == "text":
            text = msg.get("text", "") or msg.get("content", "")
            if text:
                text_parts.append(text)
        elif msg_type == "image":
            image_url = msg.get("image_url", "")
            if image_url:
                if image_url.startswith("http"):
                    data_url = await download_image_as_base64(image_url)
                    if data_url:
                        image_parts.append({"type": "image_url", "image_url": {"url": data_url}})
                        logger.info(f"图片已下载并转 base64: {len(data_url)} chars")
                elif image_url.startswith("data:"):
                    image_parts.append({"type": "image_url", "image_url": {"url": image_url}})

    if not image_parts:
        return "\n".join(text_parts) if text_parts else ""

    content = []
    if text_parts:
        content.append({"type": "text", "text": "\n".join(text_parts)})
    else:
        content.append({"type": "text", "text": "请描述这张图片"})
    content.extend(image_parts)
    return content


# ── 格式化灵珠 SSE 响应 ──────────────────────
def format_lingzhu_sse(data: dict) -> str:
    return f"event:message\ndata:{json.dumps(data, ensure_ascii=False)}\n\n"


# ── 从灵珠 metadata 构建上下文信息 ───────────
def build_context_from_metadata(metadata: dict) -> str:
    parts = []
    if metadata.get("current_time"):
        parts.append(f"当前时间: {metadata['current_time']}")
    if metadata.get("location"):
        parts.append(f"位置: {metadata['location']}")
    if metadata.get("weather"):
        parts.append(f"天气: {metadata['weather']}")
    if metadata.get("battery"):
        parts.append(f"电量: {metadata['battery']}%")
    if metadata.get("latitude") and metadata.get("longitude"):
        parts.append(f"坐标: {metadata['latitude']}, {metadata['longitude']}")
    if metadata.get("language"):
        parts.append(f"语言: {metadata['language']}")
    return "\n".join(parts) if parts else ""


# ── 带重试和心跳的 Gateway 流式调用 ──────────
async def call_gateway_with_retry(messages: list, message_id: str, agent_id: str):
    last_error = None
    for attempt in range(1 + MAX_RETRIES):
        try:
            client = await get_client()
            async with client.stream(
                "POST",
                f"{HERMES_GATEWAY_URL}/v1/chat/completions",
                json={"model": HERMES_MODEL, "messages": messages, "stream": True},
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {HERMES_API_KEY}" if HERMES_API_KEY else "",
                },
            ) as response:
                if response.status_code != 200:
                    error_text = await response.aread()
                    raise Exception(f"Gateway {response.status_code}: {error_text[:200]}")

                last_content_time = time.time()
                async for line in response.aiter_lines():
                    now = time.time()
                    if now - last_content_time > SSE_HEARTBEAT_INTERVAL:
                        yield format_lingzhu_sse({
                            "role": "agent", "type": "answer", "answer_stream": "",
                            "message_id": message_id, "agent_id": agent_id, "is_finish": False,
                        }), True
                        last_content_time = now

                    if not line.startswith("data: "):
                        continue
                    data_str = line[6:]
                    if data_str == "[DONE]":
                        continue

                    try:
                        chunk = json.loads(data_str)
                        delta = chunk.get("choices", [{}])[0].get("delta", {})
                        content = delta.get("content", "")
                        if content:
                            last_content_time = now
                            yield format_lingzhu_sse({
                                "role": "agent", "type": "answer", "answer_stream": content,
                                "message_id": message_id, "agent_id": agent_id, "is_finish": False,
                            }), False
                    except json.JSONDecodeError:
                        continue
            return
        except Exception as e:
            last_error = e
            if attempt < MAX_RETRIES:
                logger.warning(f"Gateway 调用失败(第{attempt+1}次)，1秒后重试: {e}")
                await asyncio.sleep(1)
            else:
                logger.error(f"Gateway 调用失败(已重试{MAX_RETRIES}次): {e}")

    yield format_lingzhu_sse({
        "role": "agent", "type": "answer",
        "answer_stream": "抱歉，服务暂时不可用，请稍后再试。",
        "message_id": message_id, "agent_id": agent_id, "is_finish": True,
    }), False


# ── 语音友好系统提示 ──────────────────────────
VOICE_SYSTEM_PROMPT = """你是一个通过 AR 眼镜语音交互的 AI 助手。请记住以下回复规范：

1. 回复要简短精炼，适合语音播放，一般不超过 3-5 句话
2. 不要使用 markdown 格式（不要用 **加粗**、# 标题、- 列表、```代码块``` 等）
3. 如果需要列举，用"第一、第二、第三"或"首先、其次、最后"这种口语化表达
4. 不要说"根据您提供的信息"之类的废话，直接回答
5. 如果有图片，直接描述你看到的内容，不要说"我看到您发送了一张图片"
6. 保持自然对话的语气，像朋友聊天一样
7. 用户的输入来自语音识别（STT），可能包含错别字或误识别。遇到明显不通顺或不合理的内容时，请根据上下文推测用户的真实意图，自然地回答，不要指出识别错误或反问"你是不是想说XXX"
"""


# ── SSE 主接口 ────────────────────────────────
@app.post("/api/sse")
@app.post("/sse")
async def rokid_sse(
    request: Request,
    authorization: Optional[str] = Header(None),
    api_key: Optional[str] = Header(None),
):
    try:
        body = await request.json()
    except Exception:
        body = {}

    logger.info(f"收到请求: body={json.dumps(body, ensure_ascii=False)[:500]}")

    if not verify_ak(authorization, api_key, body):
        return JSONResponse({"error": "unauthorized"}, status_code=401)

    message_id = body.get("message_id", "unknown")
    agent_id = body.get("agent_id", "unknown")
    user_id = body.get("user_id", "default")
    user_content = await build_user_content(body)

    if isinstance(user_content, str) and not user_content:
        return JSONResponse({"error": "empty text"}, status_code=400)
    elif isinstance(user_content, list) and len(user_content) == 0:
        return JSONResponse({"error": "empty content"}, status_code=400)

    if isinstance(user_content, str):
        logger.info(f"用户[{user_id}]: {user_content[:100]}, message_id={message_id}")
    else:
        img_count = sum(1 for p in user_content if p.get("type") == "image_url")
        txt_preview = next((p["text"][:50] for p in user_content if p.get("type") == "text"), "")
        logger.info(f"用户[{user_id}]: {img_count}张图片, 文本={txt_preview}, message_id={message_id}")

    # 检查清除上下文指令
    if isinstance(user_content, str):
        clear_keywords = ["清除记忆", "重新开始", "清空对话", "忘记之前"]
        for kw in clear_keywords:
            if kw in user_content:
                clear_history(user_id)
                logger.info(f"用户[{user_id}] 清除了对话历史")

    # 构建消息列表
    messages = []
    metadata = body.get("metadata", {})
    context_info = build_context_from_metadata(metadata)

    system_parts = [VOICE_SYSTEM_PROMPT]
    if context_info:
        system_parts.append(f"[设备信息]\n{context_info}")

    messages.append({"role": "system", "content": "\n\n".join(system_parts)})

    history = get_history(user_id)
    messages.extend(history)
    messages.append({"role": "user", "content": user_content})
    add_to_history(user_id, "user", user_content)

    async def event_stream():
        yield ": keepalive\n\n"
        full_response = ""

        try:
            async for sse_chunk, is_heartbeat in call_gateway_with_retry(messages, message_id, agent_id):
                if not is_heartbeat:
                    try:
                        data_line = sse_chunk.split("data:", 1)[1].strip()
                        chunk_data = json.loads(data_line)
                        text = chunk_data.get("answer_stream", "")
                        if text:
                            full_response += text
                    except Exception:
                        pass
                yield sse_chunk

            if full_response:
                add_to_history(user_id, "assistant", full_response)

            # 异步写入 Hermes session DB
            user_text_preview = ""
            if isinstance(user_content, str):
                user_text_preview = user_content
            elif isinstance(user_content, list):
                user_text_preview = next((p["text"] for p in user_content if p.get("type") == "text"), "")

            if user_text_preview and full_response:
                asyncio.create_task(store_conversation(
                    user_id=user_id, user_msg=user_text_preview,
                    assistant_msg=full_response, model=HERMES_MODEL,
                ))

                # 可选：记忆提取
                if _memory_extractor:
                    asyncio.create_task(_memory_extractor(
                        user_msg=user_text_preview,
                        assistant_msg=full_response,
                        user_id=user_id,
                    ))

            yield format_lingzhu_sse({
                "role": "agent", "type": "answer", "answer_stream": "",
                "message_id": message_id, "agent_id": agent_id, "is_finish": True,
            })

        except Exception as e:
            logger.error(f"流式处理异常: {e}")
            yield format_lingzhu_sse({
                "role": "agent", "type": "answer",
                "answer_stream": "抱歉，出了点问题，请再说一次。",
                "message_id": message_id, "agent_id": agent_id, "is_finish": True,
            })

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )


if __name__ == "__main__":
    import uvicorn
    logger.info(f"🚀 Rokid → Hermes Bridge 启动 on port {PORT}")
    logger.info(f"   Gateway: {HERMES_GATEWAY_URL}")
    logger.info(f"   Model: {HERMES_MODEL}")
    logger.info(f"   多轮上下文: 最近 {MAX_HISTORY_ROUNDS} 轮")
    logger.info(f"   SSE 心跳: {SSE_HEARTBEAT_INTERVAL}s")
    logger.info(f"   重试次数: {MAX_RETRIES}")
    logger.info(f"   记忆提取: {'启用' if _memory_extractor else '禁用'}")
    uvicorn.run(app, host="0.0.0.0", port=PORT)
