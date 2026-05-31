     1|# 眼镜发了消息但没收到回复 — 诊断流程
     2|
     3|## 症状
     4|
     5|用户对着眼镜说话，眼镜有反应（显示发送中），但没有收到 AI 回复。可能等了很久也没反应，或者提示"AI 助手异常"。
     6|
     7|## 快速诊断（3步定位）
     8|
     9|### 1. 桥接服务是否收到消息？
    10|
    11|```bash
    12|tail -50 $HOME/.hermes/logs/bridge.error.log | grep "用户\["
    13|```
    14|
    15|- **有记录** → 桥接收到了消息，继续步骤 2
    16|- **无记录** → 消息没到达桥接，检查：
    17|  - Cloudflare Tunnel 是否运行：`curl https://your-domain.com/health`
    18|  - 桥接服务是否运行：`curl http://localhost:8900/health`
    19|  - 灵珠平台配置是否正确（URL、AK）
    20|
    21|### 2. Gateway 是否处理了请求？
    22|
    23|```bash
    24|# 查看 bridge.error.log 中对应的 HTTP 状态
    25|tail -50 $HOME/.hermes/logs/bridge.error.log | grep "httpx"
    26|```
    27|
    28|- **HTTP/1.1 200 OK** → Gateway 接受了请求，继续步骤 3
    29|- **HTTP/1.1 401 Unauthorized** → Gateway API key 问题，检查：
    30|  - 桥接服务的 `.env` 中是否配置了 `HERMES_API_KEY`
    31|  - `HERMES_API_KEY` 是否与 `~/.hermes/.env` 中的 `API_SERVER_KEY` 一致
    32|  - 代码中是否使用了 `load_dotenv()` 和 `.strip()`
    33|  - Gateway 日志：`grep "Invalid API key" $HOME/.hermes/logs/gateway.log`
    34|- **其他状态码或无记录** → Gateway 有问题：
    35|  - Gateway 是否运行：`curl http://localhost:8642/health`
    36|  - 检查 gateway.error.log
    37|
    38|### 3. 模型提供商是否正常响应？
    39|
    40|```bash
    41|# 查看 Gateway 日志中的模型错误
    42|grep -i "error\|warn\|timeout\|RemoteProtocol\|stream drop" $HOME/.hermes/logs/gateway.log | tail -20
    43|```
    44|
    45|常见模型提供商错误模式：
    46|
    47|| 错误 | 含义 | 影响 |
    48||------|------|------|
    49|| `RemoteProtocolError after 180s` | 模型 API 流式连接在 180 秒后断开 | 回复丢失，用户无响应 |
    50|| `No response from provider for 180s` | 模型 API 完全无响应 | 超时后 Gateway 放弃 |
    51|| `ReadError` / `Bad file descriptor` | 网络连接异常中断 | 请求失败 |
    52|| `stream drop` | 流式传输中途断开 | 可能只收到部分回复 |
    53|
    54|**关键判断**：如果 Gateway 日志有大量 `RemoteProtocolError` 或 `stream drop`，说明是 **模型提供商不稳定**，不是桥接或网络问题。
    55|
    56|## 实际案例（2026-05-27）
    57|
    58|**现象**：用户在眼镜上说英语，没收到回复。
    59|
    60|**诊断过程**：
    61|1. bridge.error.log 显示 `Can you speak English?` 被收到，HTTP 200 OK
    62|2. session-store 显示回复已写入：`Sure! I can speak English. From now on I'll respon...`
    63|3. gateway.log 显示大量 `xiaomi stream drop (RemoteProtocolError) after 180s`
    64|
    65|**结论**：MiMo 模型 API 连接不稳定，部分请求的流式回复在传输过程中断开。桥接服务本身正常，但模型提供商的问题导致回复丢失。
    66|
    67|**修复**：换用更稳定的模型提供商，或等待小米修复 API 稳定性。
    68|
    69|## 交叉验证时间线
    70|
    71|当难以判断问题出在哪一层时，用时间线交叉验证：
    72|
    73|```bash
    74|# 桥接收到消息的时间
    75|grep "用户\[" $HOME/.hermes/logs/bridge.error.log | tail -5
    76|
    77|# Gateway 处理请求的时间（注意：Gateway 不一定记录桥接的请求）
    78|grep "2026-05-27 HH:MM" $HOME/.hermes/logs/gateway.log
    79|
    80|# 模型错误的时间
    81|grep -i "error\|stream drop" $HOME/.hermes/logs/gateway.log | tail -10
    82|```
    83|
    84|如果桥接显示 HTTP 200 但 Gateway 日志同一时间段有模型错误 → 模型提供商问题。
    85|如果桥接显示 HTTP 200 且 Gateway 无错误 → 检查 SSE 响应是否完整返回给眼镜（可能是 Cloudflare 超时）。
    86|
    87|## 各层服务状态快速检查
    88|
    89|```bash
    90|# 一键检查所有服务
    91|launchctl list | grep hermes
    92|# com.hermes.bridge    → 桥接服务
    93|# ai.hermes.gateway    → Gateway
    94|# com.hermes.cloudflared → Cloudflare Tunnel
    95|
    96|# 各服务详细状态
    97|launchctl list com.hermes.bridge
    98|launchctl list ai.hermes.gateway
    99|
   100|# 健康检查
   101|curl -s http://localhost:8900/health    # 桥接
   102|curl -s http://localhost:8642/health    # Gateway
   103|curl -s https://your-domain.com/health  # 公网
   104|```
   105|
   106|## launchctl 退出码含义
   107|
   108|| 退出码 | 含义 |
   109||--------|------|
   110|| 0 | 正常运行 |
   111|| -15 (SIGTERM) | 被终止（可能是手动停止或重启） |
   112|| 19200 | 异常退出（需要查看 error log） |
   113|