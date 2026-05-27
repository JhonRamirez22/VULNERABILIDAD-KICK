#!/bin/bash

echo "🚀 KICK VIEWER BOT v16.0 — Setup Automático"
echo "=============================================="

# 1. Crear directorio de logs
echo "📁 Creando directorio de logs..."
mkdir -p logs

# 2. Instalar dependencias Node.js
echo "📦 Instalando dependencias Node.js..."
npm install ws

# 3. Instalar PM2 globalmente
echo "🔧 Instalando PM2..."
npm install -g pm2

# 4. Instalar dependencias Python
echo "🐍 Instalando dependencias Python..."
pip install curl_cffi fastapi uvicorn redis requests --break-system-packages 2>/dev/null || \
pip install curl_cffi fastapi uvicorn redis requests

# 5. Descargar lista de proxies
echo "🌐 Descargando lista de proxies SOCKS5..."
curl -s "https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/socks5.txt" | \
  awk '{print "socks5://" $0}' > upstreams.txt

echo "✅ Proxies descargados: $(wc -l < upstreams.txt) proxies"

# 6. Verificar puertos
echo ""
echo "🔌 Verificando puertos disponibles..."
if lsof -i :1080 > /dev/null 2>&1; then
    echo "⚠️  Puerto 1080 en uso. Liberando..."
    kill -9 $(lsof -t -i:1080) 2>/dev/null || true
fi

if lsof -i :8765 > /dev/null 2>&1; then
    echo "⚠️  Puerto 8765 en uso. Liberando..."
    kill -9 $(lsof -t -i:8765) 2>/dev/null || true
fi

# 7. Crear permisos de ejecución
chmod +x token_server.py proxy_checker.py proxy_rotator.py kick-websocket-v16.js

echo ""
echo "✅ Setup completado exitosamente!"
echo ""
echo "📋 Próximos pasos:"
echo ""
echo "Opción A — Iniciar manualmente en múltiples terminales:"
echo "  Terminal 1: python3 token_server.py"
echo "  Terminal 2: python3 proxy_checker.py"
echo "  Terminal 3: python3 proxy_rotator.py --socks5-port 1080 --upstream-file upstreams.txt"
echo "  Terminal 4: node kick-websocket-v16.js https://kick.com/tanizen 500"
echo ""
echo "Opción B — Iniciar con PM2 (Recomendado):"
echo "  pm2 start ecosystem.config.js"
echo "  pm2 logs"
echo ""
echo "🎯 Para ver el README completo:"
echo "  cat README_v16.md"
echo ""
