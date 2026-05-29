#!/usr/bin/env bash
set -e

echo "== SYSTEM =="
hostname
uptime
free -h
df -h /

echo
echo "== DOCKER =="
docker ps

echo
echo "== PAOS REPO =="
cd /home/ubuntu/paos/personal-context
git status --short
git branch --show-current
