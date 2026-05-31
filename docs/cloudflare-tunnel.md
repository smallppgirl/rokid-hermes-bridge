     1|     1|# Cloudflare Tunnel 部署 Web 服务
     2|     2|
     3|     3|> 经验来源：通过同一 tunnel 部署 your-nextjs-app（Next.js）到 your-app.your-domain.com
     4|     4|
     5|     5|## 概念
     6|     6|
     7|     7|一个 cloudflared tunnel 可以同时路由**多个子域名**到不同的本地端口。不需要为每个服务创建单独的 tunnel。
     8|     8|
     9|     9|```
    10|    10|域名 A → localhost:8900  (桥接服务)
    11|    11|域名 B → localhost:3080  (Next.js 网站)
    12|    12|域名 C → localhost:1337  (Strapi 后端)
    13|    13|```
    14|    14|
    15|    15|## 添加新域名到已有 tunnel
    16|    16|
    17|    17|### 1. 修改 config.yml
    18|    18|
    19|    19|在 `~/.cloudflared/config.yml` 的 ingress 中添加新路由：
    20|    20|
    21|    21|```yaml
    22|    22|ingress:
    23|    23|  - hostname: your-domain.com
    24|    24|    service: http://localhost:8900
    25|    25|  - hostname: your-app.your-domain.com
    26|    26|    service: http://localhost:3080
    27|    27|  # 一定要有兜底规则（404）
    28|    28|  - service: http_status:404
    29|    29|```
    30|    30|
    31|    31|⚠️ **顺序重要**：Cloudflare 按顺序匹配，兜底的 `http_status:404` 必须放最后。
    32|    32|
    33|    33|### 2. 添加 DNS 记录
    34|    34|
    35|    35|```bash
    36|    36|# 一条命令搞定（需要 tunnel ID + 域名）
    37|    37|cloudflared tunnel route dns <tunnel-id> <hostname>
    38|    38|# 例如：
    39|    39|cloudflared tunnel route dns your-tunnel-id your-app.your-domain.com
    40|    40|```
    41|    41|
    42|    42|### 3. 重启 tunnel
    43|    43|
    44|    44|```bash
    45|    45|# macOS launchd
    46|    46|launchctl kickstart -k gui/$(id -u)/com.hermes.cloudflared
    47|    47|```
    48|    48|
    49|    49|## Next.js 部署模式
    50|    50|
    51|    51|### 项目结构
    52|    52|
    53|    53|```
    54|    54|~/my-nextjs-site/
    55|    55|├── package.json
    56|    56|├── next.config.ts
    57|    57|├── deploy.sh          # 部署脚本
    58|    58|└── ...
    59|    59|```
    60|    60|
    61|    61|### 部署脚本模板 (deploy.sh)
    62|    62|
    63|    63|```bash
    64|    64|#!/bin/bash
    65|    65|set -e
    66|    66|cd ~/my-nextjs-site
    67|    67|
    68|    68|echo "📥 拉取最新代码..."
    69|    69|git pull origin main 2>&1 || git pull origin master 2>&1
    70|    70|
    71|    71|echo "📦 安装依赖..."
    72|    72|npm install --production=false 2>&1 | tail -3
    73|    73|
    74|    74|echo "🔨 构建..."
    75|    75|npm run build 2>&1 | tail -5
    76|    76|
    77|    77|echo "🔄 重启服务..."
    78|    78|launchctl kickstart -k gui/$(id -u)/com.mysite 2>&1
    79|    79|
    80|    80|sleep 2
    81|    81|STATUS=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:3000)
    82|    82|if [ "$STATUS" = "200" ]; then
    83|    83|    echo "✅ 部署成功！https://your-app.your-domain.com"
    84|    84|else
    85|    85|    echo "❌ 服务异常 HTTP $STATUS"
    86|    86|    exit 1
    87|    87|fi
    88|    88|```
    89|    89|
    90|    90|### LaunchAgent 模板 (com.xxx.site.plist)
    91|    91|
    92|    92|```xml
    93|    93|<?xml version="1.0" encoding="UTF-8"?>
    94|    94|<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
    95|    95|<plist version="1.0">
    96|    96|<dict>
    97|    97|    <key>Label</key>
    98|    98|    <string>com.xxx.site</string>
    99|    99|    <key>ProgramArguments</key>
   100|   100|    <array>
   101|   101|        <string>/opt/homebrew/bin/npx</string>
   102|   102|        <string>next</string>
   103|   103|        <string>start</string>
   104|   104|        <string>-p</string>
   105|   105|        <string>3000</string>
   106|   106|    </array>
   107|   107|    <key>WorkingDirectory</key>
   108|   108|    <string>/Users/USERNAME/my-nextjs-site</string>
   109|   109|    <key>EnvironmentVariables</key>
   110|   110|    <dict>
   111|   111|        <key>PORT</key><string>3000</string>
   112|   112|        <key>PATH</key><string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin</string>
   113|   113|        <key>NODE_ENV</key><string>production</string>
   114|   114|    </dict>
   115|   115|    <key>RunAtLoad</key><true/>
   116|   116|    <key>KeepAlive</key><true/>
   117|   117|    <key>StandardOutPath</key><string>/Users/USERNAME/.hermes/logs/site-stdout.log</string>
   118|   118|    <key>StandardErrorPath</key><string>/Users/USERNAME/.hermes/logs/site-stderr.log</string>
   119|   119|</dict>
   120|   120|</plist>
   121|   121|```
   122|   122|
   123|   123|### 启用服务
   124|   124|
   125|   125|```bash
   126|   126|# 创建日志目录
   127|   127|mkdir -p ~/.hermes/logs
   128|   128|
   129|   129|# 复制 plist 到 LaunchAgents
   130|   130|cp com.xxx.site.plist ~/Library/LaunchAgents/
   131|   131|
   132|   132|# 加载
   133|   133|launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.xxx.site.plist
   134|   134|```
   135|   135|
   136|   136|## 带后端的 Next.js + Strapi 模式
   137|   137|
   138|   138|如果网站需要后端 CMS（如 Strapi），需要额外处理：
   139|   139|
   140|   140|### 1. 后端也要走 tunnel
   141|   141|
   142|   142|```yaml
   143|   143|# config.yml
   144|   144|ingress:
   145|   145|  - hostname: api.your-app.your-domain.com
   146|   146|    service: http://localhost:1337
   147|   147|  - hostname: your-app.your-domain.com
   148|   148|    service: http://localhost:3080
   149|   149|```
   150|   150|
   151|   151|### 2. 前端的 API 地址必须用公网域名
   152|   152|
   153|   153|next.config.ts 中的 remotePatterns 不能用 `localhost`，因为浏览器在公网访问时，localhost 指的是用户自己的设备。
   154|   154|
   155|   155|```typescript
   156|   156|// ❌ 错误：浏览器会请求用户手机本地的 1337 端口
   157|   157|{ protocol: "http", hostname: "localhost", port: "1337" }
   158|   158|
   159|   159|// ✅ 正确：使用公网域名
   160|   160|{ protocol: "https", hostname: "api.your-app.your-domain.com" }
   161|   161|```
   162|   162|
   163|   163|## 常见坑
   164|   164|
   165|   165|1. **忘记兜底 404 规则**：没有 `http_status:404` 兜底会导致 Cloudflare 报错
   166|   166|2. **DNS 没加**：改了 config.yml 但没跑 `cloudflared tunnel route dns`，域名不通
   167|   167|3. **Tunnel 没重启**：改了 config 但没 kickstart cloudflared，新路由不生效
   168|   168|4. **Next.js 图片用 localhost**：公网用户访问时图片全部 404（见上方"带后端"章节）
   169|   169|5. **端口冲突**：多个服务用同一个端口，先用 `lsof -iTCP:端口号` 检查
   170|   170|