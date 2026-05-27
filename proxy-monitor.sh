#!/bin/bash
# Monitor proxy_rotator.py y reinicia si muere
# Uso: ./proxy-monitor.sh &

while true; do
    if ! lsof -Pi :1080 -sTCP:LISTEN -t >/dev/null 2>&1; then
        echo "[$(date)] ⚠️  Puerto 1080 no responde. Relanzando proxy_rotator.py..."
        nohup python3 proxy_rotator.py --socks5-port 1080 --upstream-file upstreams.txt > proxy.log 2>&1 &
        sleep 2
    fi
    sleep 10
done
