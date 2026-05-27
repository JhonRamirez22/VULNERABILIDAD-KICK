#!/bin/bash
# Kick Viewer Bot - Orquestación Inteligente v2.0
# Controla proxy_rotator, reintentos automáticos, y estadísticas

set -e

# Colores
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CHANNEL="${1:-https://kick.com/tanizen}"
VIEWERS="${2:-500}"
LOGDIR="$SCRIPT_DIR/logs"

# Crear directorio de logs
mkdir -p "$LOGDIR"

echo -e "${GREEN}╔════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║ KICK VIEWER BOT v2.0 - Orquestación Inteligente║${NC}"
echo -e "${GREEN}╚════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "🎯 Canal: ${YELLOW}$CHANNEL${NC}"
echo -e "👥 Viewers: ${YELLOW}$VIEWERS${NC}"
echo -e "📁 Logs: ${YELLOW}$LOGDIR${NC}"
echo ""

# 1. Verificar dependencias
echo -e "${YELLOW}[1/4] Verificando dependencias...${NC}"
command -v node >/dev/null 2>&1 || { echo -e "${RED}❌ Node.js no instalado${NC}"; exit 1; }
command -v python3 >/dev/null 2>&1 || { echo -e "${RED}❌ Python3 no instalado${NC}"; exit 1; }

python3 -c "import curl_cffi" 2>/dev/null || { echo -e "${RED}❌ curl_cffi no instalado. Ejecuta: pip install curl_cffi${NC}"; exit 1; }
test -f "$SCRIPT_DIR/kick-websocket.js" || { echo -e "${RED}❌ kick-websocket.js no encontrado${NC}"; exit 1; }
test -f "$SCRIPT_DIR/proxy_rotator.py" || { echo -e "${RED}❌ proxy_rotator.py no encontrado${NC}"; exit 1; }
test -f "$SCRIPT_DIR/upstreams.txt" || { echo -e "${RED}❌ upstreams.txt no encontrado${NC}"; exit 1; }

echo -e "${GREEN}✅ Todas las dependencias OK${NC}"
echo ""

# 2. Iniciar proxy_rotator si no está corriendo
echo -e "${YELLOW}[2/4] Iniciando servicio de proxies...${NC}"
if ! lsof -Pi :1080 -sTCP:LISTEN -t >/dev/null 2>&1; then
    echo "  🔄 Lanzando proxy_rotator.py..."
    nohup python3 "$SCRIPT_DIR/proxy_rotator.py" --socks5-port 1080 --upstream-file "$SCRIPT_DIR/upstreams.txt" > "$LOGDIR/proxy-rotator.log" 2>&1 &
    sleep 3
    
    # Verificar que está escuchando
    if lsof -Pi :1080 -sTCP:LISTEN -t >/dev/null 2>&1; then
        echo -e "${GREEN}✅ Puerto 1080 (SOCKS5) activo${NC}"
    else
        echo -e "${RED}❌ No se pudo iniciar proxy_rotator. Ver: tail -f $LOGDIR/proxy-rotator.log${NC}"
        exit 1
    fi
else
    echo -e "${GREEN}✅ Puerto 1080 (SOCKS5) ya activo${NC}"
fi
echo ""

# 3. Iniciar monitor de proxy (para reiniciar si se cae)
echo -e "${YELLOW}[3/4] Activando monitor de proxies...${NC}"
if ! pgrep -f "proxy-monitor.sh" >/dev/null; then
    nohup "$SCRIPT_DIR/proxy-monitor.sh" > "$LOGDIR/proxy-monitor.log" 2>&1 &
    echo -e "${GREEN}✅ Monitor de proxies ejecutándose${NC}"
else
    echo -e "${GREEN}✅ Monitor de proxies ya activo${NC}"
fi
echo ""

# 4. Iniciar el bot
echo -e "${YELLOW}[4/4] Iniciando bot de viewers...${NC}"
echo ""

cd "$SCRIPT_DIR"
node kick-websocket.js "$CHANNEL" "$VIEWERS" 2>&1 | tee "$LOGDIR/bot-$(date +%Y%m%d_%H%M%S).log"
