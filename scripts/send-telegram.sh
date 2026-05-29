#!/usr/bin/env bash

source /home/ubuntu/paos/paos-runtime/.env

MESSAGE="$1"

curl -s -X POST "https://api.telegram.org/bot$TELEGRAM_BOT_TOKEN/sendMessage" \
-d chat_id="$TELEGRAM_CHAT_ID" \
-d text="$MESSAGE"
