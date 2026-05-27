#!/bin/bash

# KICK VIEWER BOT v16.0 — LAUNCHER INTEGRADO
# Inicia todos los servicios necesarios automáticamente

set -e

echo "╔════════════════════════════════════════════════════╗"
echo "║  KICK VIEWER BOT v16.0 — ENTERPRISE LAUNCHER      ║"
echo "╚════════════════════════════════════════════════════╝"
echo ""

# Verificar argumentos
CHANNEL_URL="${1:-https://kick.com/tanizen}"
VIEWERS="${2:-500}"
CLUSTERS="${3:-1}"

echo "📊 Configuración:"
echo "  • Channel: $CHANNEL_URL"
echo "  • Viewers: $VIEWERS"
echo "  • Clusters: $CLUSTERS"
echo ""

# Función para limpiar al salir
cleanup() {
    echo ""
    echo "🛑 Deteniendo servicios..."
    kill $TOKEN_SERVER_PID 2>/dev/null || true
    kill $PROXY_CHECKER_PID 2>/dev/null || true
    kill $PROXY_ROTATOR_PID 2>/dev/null || true
    wait 2>/dev/null || true
    echo "✅ Servicios detenidos."
}

trap cleanup EXIT

# 1. Token Server
echo "🚀 [1/4] Iniciando Token Server en puerto 8765..."
nohup python3 token_server.py > logs/token-server.log 2>&1 &
TOKEN_SERVER_PID=$!
sleep 2

# Verificar que está vivo
if ! curl -s http://127.0.0.1:8765/health > /dev/null 2>&1; then
    echo "❌ Token Server no respondió. Revisando logs..."
    tail -n 20 logs/token-server.log
    exit 1
fi
echo "✅ Token Server activo (PID: $TOKEN_SERVER_PID)"

# 2. Proxy Checker
echo "🚀 [2/4] Iniciando Proxy Checker..."
nohup python3 proxy_checker.py > logs/proxy-checker.log 2>&1 &
PROXY_CHECKER_PID=$!
sleep 1
echo "✅ Proxy Checker activo (PID: $PROXY_CHECKER_PID)"

# 3. Proxy Rotator
echo "🚀 [3/4] Iniciando Proxy Rotator en puerto 1080..."
if lsof -i :1080 > /dev/null 2>&1; then
    echo "  ⚠️  Liberando puerto 1080..."
    kill -9 $(lsof -t -i:1080) 2>/dev/null || true
    sleep 1
fi

nohup python3 proxy_rotator.py --socks5-port 1080 --upstream-file upstreams.txt > logs/proxy-rotator.log 2>&1 &
PROXY_ROTATOR_PID=$!
sleep 2

# Verificar que proxy rotator está escuchando
if ! lsof -i :1080 > /dev/null 2>&1; then
    echo "❌ Proxy Rotator no vinculó puerto 1080. Revisando logs..."
    tail -n 20 logs/proxy-rotator.log
    exit 1
fi
echo "✅ Proxy Rotator activo en :1080 (PID: $PROXY_ROTATOR_PID)"

# 4. Bot principal (usando versión anterior que funciona)
echo "🚀 [4/4] Iniciando Bot Principal..."
echo ""

if [ "$CLUSTERS" -gt 1 ]; then
    echo "📈 Modo clustering: $CLUSTERS instancias paralelas"
    node kick-websocket.js "$CHANNEL_URL" "$VIEWERS" --clusters "$CLUSTERS"
else
    node kick-websocket.js "$CHANNEL_URL" "$VIEWERS"
fi
