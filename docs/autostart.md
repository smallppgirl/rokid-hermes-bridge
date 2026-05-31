# 开机自启动

## macOS (launchd)

创建 `~/Library/LaunchAgents/com.hermes.rokid-bridge.plist`：

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.hermes.rokid-bridge</string>
    <key>ProgramArguments</key>
    <array>
        <string>/bin/bash</string>
        <string>-c</string>
        <string>cd $HOME/hermes-bridge && source .env 2>/dev/null; export $(grep -v '^#' .env | xargs) 2>/dev/null; exec /usr/bin/python3 src/main.py</string>
    </array>
    <key>WorkingDirectory</key>
    <string>$HOME/hermes-bridge</string>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <dict>
        <key>SuccessfulExit</key>
        <false/>
    </dict>
    <key>StandardOutPath</key>
    <string>$HOME/.hermes/logs/rokid-bridge.log</string>
    <key>StandardErrorPath</key>
    <string>$HOME/.hermes/logs/rokid-bridge.log</string>
</dict>
</plist>
```

```bash
mkdir -p ~/.hermes/logs
launchctl load ~/Library/LaunchAgents/com.hermes.rokid-bridge.plist
```

管理命令：
- 查看状态：`launchctl list | grep rokid`
- 停止：`launchctl unload ~/Library/LaunchAgents/com.hermes.rokid-bridge.plist`
- 启动：`launchctl load ~/Library/LaunchAgents/com.hermes.rokid-bridge.plist`

## Linux (systemd)

创建 `/etc/systemd/system/hermes-bridge.service`：

```ini
[Unit]
Description=Hermes Bridge for Rokid
After=network.target

[Service]
Type=simple
User=yourusername
WorkingDirectory=/home/yourusername/hermes-bridge
ExecStart=/usr/bin/python3 src/main.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable hermes-bridge
sudo systemctl start hermes-bridge
```
