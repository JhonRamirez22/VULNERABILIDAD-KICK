# 🎯 KICK VIEWER BOT v16.0 — ENTERPRISE

**Herramienta avanzada para boost de viewers en Kick.com con arquitectura escalable.**

## ⚡ Características v16.0

✅ **Token API Server (FastAPI)** — Reemplaza `spawnSync`, generando tokens bajo demanda  
✅ **Proxy Checker Inteligente** — Valida proxies en background constantemente  
✅ **Proxy Rotator SOCKS5** — Enruta 10,000+ conexiones simultáneas  
✅ **Clustering Automático** — Múltiples instancias Node.js paralelas  
✅ **Ping/Pong RFC 6455** — Compatible con Cloudflare y Pusher  
✅ **Humanización Adaptativa** — Comportamiento realista de usuarios  
✅ **PM2 Integration** — Monitoreo y reinicio automático  

---

## 📋 Requisitos Previos

```bash
# Node.js v18+
node --version

# Python 3.9+
python3 --version

# Paquetes Python
pip install curl_cffi fastapi uvicorn redis requests --break-system-packages

# Paquetes Node.js
npm install ws
npm install -g pm2
```

---

## 🚀 Instalación Rápida

### 1. Crear directorio de logs
```bash
mkdir -p logs
```

### 2. Descargar proxies vivos
```bash
curl -s "https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/socks5.txt" | awk '{print "socks5://" $0}' > upstreams.txt
```

### 3. Verificar puerto 1080
```bash
lsof -i :1080  # Debe estar libre
```

---

## 🎮 Uso

### Opción A: Modo Simple (1 instancia)
```bash
# Terminal 1: Iniciar Token Server
python3 token_server.py

# Terminal 2: Iniciar Proxy Checker
python3 proxy_checker.py

# Terminal 3: Iniciar Proxy Rotator
python3 proxy_rotator.py --socks5-port 1080 --upstream-file upstreams.txt

# Terminal 4: Iniciar Bot
node kick-websocket-v16.js https://kick.com/tanizen 500
```

### Opción B: Modo Clustering (Recomendado) — PM2
```bash
# Iniciar TODO automáticamente
pm2 start ecosystem.config.js

# Ver estado de procesos
pm2 monit

# Ver logs en tiempo real
pm2 logs

# Detener
pm2 stop all
pm2 delete all
```

### Opción C: Clustering Manual
```bash
# 4 instancias del bot, 2,000 viewers cada una (8,000 total)
node kick-websocket-v16.js https://kick.com/canal 2000 --clusters 4
```

---

## 📊 Dashboard en Vivo

El bot mostrará automáticamente:
```
╔════════════════════════════════════════════════════╗
║   KICK VIEWER BOT v16.0 — ENTERPRISE              ║
╠════════════════════════════════════════════════════╣
║ Stream: tanizen                    
║ Target: 5000 viewers                              ║
╠════════════════════════════════════════════════════╣
║ ViewerWS :  3240 / 5000            
║ PusherWS :  3240                                   ║
║ Uptime   :  145s                                   ║
╚════════════════════════════════════════════════════╝
```

---

## 🔧 Componentes

### `token_server.py`
- **Puerto:** `http://127.0.0.1:8765`
- **Endpoints:**
  - `GET /token?channel=tanizen` → Obtiene 1 token
  - `GET /batch-tokens?channel=tanizen&count=50` → Obtiene múltiples tokens en paralelo
  - `GET /health` → Verificar salud del servidor

### `proxy_checker.py`
- Valida proxies vivos cada 5 minutos
- Elimina proxies muertos de forma automática
- Guarda lista viva en `upstreams.txt.alive`

### `proxy_rotator.py`
- SOCKS5 local en puerto 1080
- Rotación round-robin de proxies upstream
- Reintentos automáticos en proxies fallidos

### `kick-websocket-v16.js`
- Motor principal del bot
- Conexión ViewerWS + PusherWS por cada viewer
- Manejo de ping/pong nativos
- Clustering automático

---

## ⚙️ Configuración Avanzada

### Aumentar listeners máximos (más de 10,000 viewers)
```bash
ulimit -n 65536
```

### Usar más instancias de clustering
Editar `ecosystem.config.js`:
```javascript
{
  name: 'kick-bot-cluster',
  instances: 8,  // Cambiar a 8 núcleos
  args: 'https://kick.com/canal 10000',
}
```

### Cambiar intervalo de validación de proxies
En `proxy_checker.py`:
```python
CHECK_INTERVAL = 120  # Validar cada 2 minutos en vez de 5
```

---

## 🐛 Troubleshooting

### Error: "Failed to connect to 127.0.0.1 port 1080"
```bash
# Reiniciar proxy rotator
pkill -f proxy_rotator.py
nohup python3 proxy_rotator.py --socks5-port 1080 --upstream-file upstreams.txt &
```

### Error: "No se obtuvieron tokens"
```bash
# Verificar que Token Server esté activo
curl http://127.0.0.1:8765/health

# Si no responde, iniciar:
python3 token_server.py
```

### Proxies muertos
```bash
# Regenerar lista
curl -s "https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/socks5.txt" | \
  awk '{print "socks5://" $0}' > upstreams.txt

# El proxy_checker.py automáticamente validará la nueva lista
```

### RAM alta / Proceso lento
```bash
# Reducir instancias clustering
# o 
# Aumentar tiempo de stagger en kick-websocket-v16.js:
# const staggerDelay = this.viewerCount > 1000 ? 500 : 200;
```

---

## 📈 Performance Tips

1. **Usar proxies residenciales premium** — Los proxies gratuitos tienen baja disponibilidad
2. **Ejecutar en servidor con >16GB RAM** — Necesario para 50,000+ viewers
3. **Múltiples máquinas** — Distribuir instancias en 3-4 máquinas para máximo rendimiento
4. **Monitorear upstreams.txt** — Mantener >100 proxies vivos activos
5. **Usar PM2 con persistencia** — Permite reinicio automático en caso de crash

---

## 📝 Logs

```bash
# Ver todos los logs en tiempo real
pm2 logs

# Log específico del bot
tail -f logs/kick-bot-out.log

# Log de errores
tail -f logs/kick-bot-error.log

# Log del token server
tail -f logs/token-server-out.log
```

---

## ⚖️ Legal Disclaimer

Esta herramienta es **solo con propósitos educativos**. El uso para fraude, violación de términos de servicio o actividades ilícitas es responsabilidad del usuario.

---

## 🎉 Versión 16.0 vs Anteriores

| Característica | v14.0 | v15.0 | **v16.0** |
|---|---|---|---|
| Token Gen | spawnSync | spawnSync | **API Server** |
| Proxies | Estático | Estático | **Validación en tiempo real** |
| Max Viewers | 10k | 10k | **50k+** |
| Overhead CPU | Alto | Alto | **Bajo** |
| Clustering | No | No | **Sí (4+ instancias)** |
| Ping/Pong RFC6455 | No | Parcial | **Completo** |

---

**v16.0 — Enterprise Edition**  
*Última actualización: Abril 2026*
