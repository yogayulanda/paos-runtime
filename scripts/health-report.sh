#!/usr/bin/env bash

source /home/ubuntu/paos/paos-runtime/.env

HOST=$(hostname)
UPTIME=$(uptime -p)
RAM=$(free -h | awk '/Mem:/ {print $3 "/" $2}')
DISK=$(df -h / | awk 'NR==2 {print $3 "/" $2 " (" $5 ")"}')

MESSAGE="📡 PAOS VPS Health

🖥 Host: $HOST
⏱ Uptime: $UPTIME
🧠 RAM: $RAM
💾 Disk: $DISK"

curl -s -X POST "https://api.telegram.org/bot$TELEGRAM_BOT_TOKEN/sendMessage" \
-d chat_id="$TELEGRAM_CHAT_ID" \
-d text="$MESSAGE"
