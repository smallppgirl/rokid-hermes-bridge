     1|# 灵珠平台 SSE 协议参考
     2|
     3|> 来源：OpenClaw 灵珠插件源码 + 实际抓包验证
     4|> GitHub: https://github.com/EndlessJour9527/openclaw-lingzhu-skill
     5|
     6|## 请求格式
     7|
     8|灵珠平台发送的 POST body：
     9|
    10|```json
    11|{
    12|  "message_id": "1779620196",
    13|  "agent_id": "35e651b2bb2e485788faa43054d07170",
    14|  "user_id": "11424EE94DDC4DC9A47B81A1216B79BC",
    15|  "third_agent_id": "hermes-harry",
    16|  "message": [
    17|    {"role": "user", "type": "text", "text": "你好", "image_url": null}
    18|  ],
    19|  "metadata": {
    20|    "language": "zh-CN",
    21|    "location": "中国广东省广州市番禺区",
    22|    "current_time": "2026-05-24 19:09:03",
    23|    "latitude": "22.96892",
    24|    "longitude": "113.30107",
    25|    "weather": "多云，31度",
    26|    "battery": "97",
    27|    "running_app": []
    28|  }
    29|}
    30|```
    31|
    32|### 关键字段
    33|
    34|| 字段 | 类型 | 必须 | 说明 |
    35||------|------|------|------|
    36|| `message_id` | string | ✅ | 消息唯一 ID，响应中必须原样返回 |
    37|| `agent_id` | string | ✅ | 智能体 ID，响应中必须原样返回 |
    38|| `user_id` | string | ❌ | 用户 ID |
    39|| `third_agent_id` | string | ❌ | 自定义智能体 ID |
    40|| `message` | array | ✅ | 消息数组，至少一条 |
    41|| `message[].role` | string | ✅ | `"user"` 或 `"agent"` |
    42|| `message[].type` | string | ✅ | `"text"` 或 `"image"` |
    43|| `message[].text` | string | ✅ | 文本内容 |
    44|| `message[].image_url` | string | ❌ | 图片 URL（拍照场景） |
    45|| `metadata` | object | ❌ | 设备上下文信息 |
    46|
    47|## 响应格式
    48|
    49|### SSE 事件格式
    50|
    51|```
    52|event:message
    53|data:{json}\n\n
    54|```
    55|
    56|⚠️ **必须是 `event:message` 开头**，不是 `data:` 开头。
    57|
    58|### 响应数据结构
    59|
    60|```typescript
    61|interface LingzhuSSEData {
    62|  role: "agent";                    // 固定值
    63|  type: "answer" | "tool_call" | "follow_up";
    64|  answer_stream?: string;           // 文本内容
    65|  message_id: string;               // 必须和请求中一致
    66|  agent_id: string;                 // 必须和请求中一致
    67|  is_finish: boolean;               // 是否是最后一个 chunk
    68|  follow_up?: string[];             // 跟进建议（可选）
    69|  tool_call?: LingzhuToolCall;      // 工具调用（可选）
    70|}
    71|```
    72|
    73|### 流式响应示例
    74|
    75|```
    76|: keepalive
    77|
    78|event:message
    79|data:{"role":"agent","type":"answer","answer_stream":"你好","message_id":"123","agent_id":"456","is_finish":false}
    80|
    81|event:message
    82|data:{"role":"agent","type":"answer","answer_stream":"！","message_id":"123","agent_id":"456","is_finish":false}
    83|
    84|event:message
    85|data:{"role":"agent","type":"answer","answer_stream":"有什么可以帮你的？","message_id":"123","agent_id":"456","is_finish":false}
    86|
    87|event:message
    88|data:{"role":"agent","type":"answer","answer_stream":"","message_id":"123","agent_id":"456","is_finish":true}
    89|```
    90|
    91|### 保活机制
    92|
    93|SSE 连接期间定期发送注释保持连接：
    94|```
    95|: keepalive\n\n
    96|```
    97|
    98|## 鉴权
    99|
   100|灵珠平台通过 `Authorization` header 发送 Bearer token：
   101|```
   102|Authorization: Bearer ***
   103|```
   104|
   105|## 响应头
   106|
   107|```http
   108|Content-Type: text/event-stream
   109|Cache-Control: no-cache
   110|Connection: keep-alive
   111|X-Accel-Buffering: no
   112|```
   113|
   114|`X-Accel-Buffering: no` 很重要，防止 Cloudflare/Nginx 缓冲 SSE 流。
   115|
   116|## 工具调用（高级）
   117|
   118|灵珠平台支持设备工具调用，如拍照、导航、日程等：
   119|
   120|```json
   121|{
   122|  "role": "agent",
   123|  "type": "tool_call",
   124|  "message_id": "123",
   125|  "agent_id": "456",
   126|  "is_finish": false,
   127|  "tool_call": {
   128|    "handling_required": true,
   129|    "command": "take_photo",
   130|    "action": "capture"
   131|  }
   132|}
   133|```
   134|
   135|支持的命令：`take_photo`, `take_navigation`, `control_calendar`, `send_notification`, `speak_tts` 等。
   136|
   137|## 常见错误
   138|
   139|1. **返回 405 Method Not Allowed**：SSE 端点只接受 POST，不接受 GET
   140|2. **眼镜无响应**：检查 `event:message` 格式是否正确（不是 `data:`）
   141|3. **眼镜提示重启 App**：响应格式不匹配，检查 `is_finish` 是否正确发送
   142|4. **AK 验证失败**：确认 Bearer token 格式和灵珠平台配置一致
   143|