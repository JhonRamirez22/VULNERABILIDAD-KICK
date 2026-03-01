"""
kick_ws_connect.py — Conectar al viewer WS de Kick con el token obtenido
y enviar channel_handshake para contar como viewer

Flujo completo RE descubierto:
  1. curl_cffi (Chrome TLS) → GET kick.com/{canal} → cookies CF
  2. Misma sesión → GET websockets.kick.com/viewer/v1/token
     + X-CLIENT-TOKEN: e1393935a959b4020a4491574f6490129f678acdaa92760471263db43487f823
     → {data: {token: "JWT"}}
  3. WSS websockets.kick.com/viewer/v1/connect?token=JWT
  4. Send: {type: "channel_handshake", data: {message: {channelId: "54451863"}}}
  5. Ping cada 30s: {type: "ping"}
  6. Re-handshake cada 15s
"""
import json
import uuid
import time
import asyncio
import ssl
import sys
from curl_cffi import requests as cffi_requests

# Intentar importar websockets, si no está, usar ws nativo
try:
    import websockets
    HAS_WEBSOCKETS = True
except ImportError:
    HAS_WEBSOCKETS = False

CHANNEL_ID   = "54451863"
CHANNEL_SLUG = "jhonramirez22"
CLIENT_TOKEN = "e1393935a959b4020a4491574f6490129f678acdaa92760471263db43487f823"
WS_BASE_URL  = "wss://websockets.kick.com/viewer/v1/connect"
UA           = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"


def get_viewer_token():
    """Obtener el viewer JWT token usando curl_cffi (sin browser)"""
    session = cffi_requests.Session(impersonate="chrome131")
    
    # Paso 1: Establecer sesión CF
    session.get(
        f"https://kick.com/{CHANNEL_SLUG}",
        headers={
            "User-Agent": UA,
            "Accept": "text/html,*/*",
            "sec-fetch-dest": "document",
            "sec-fetch-mode": "navigate",
        },
        timeout=20,
    )
    
    # Paso 2: Obtener viewer token
    r = session.get(
        "https://websockets.kick.com/viewer/v1/token",
        headers={
            "User-Agent":         UA,
            "Accept":             "application/json, text/plain, */*",
            "Accept-Language":    "en-US,en;q=0.9",
            "sec-ch-ua":          '"Google Chrome";v="131", "Chromium";v="131", "Not_A Brand";v="24"',
            "sec-ch-ua-mobile":   "?0",
            "sec-ch-ua-platform": '"Windows"',
            "sec-fetch-dest":     "empty",
            "sec-fetch-mode":     "cors",
            "sec-fetch-site":     "same-site",
            "Origin":             "https://kick.com",
            "Referer":            f"https://kick.com/{CHANNEL_SLUG}",
            "X-CLIENT-TOKEN":     CLIENT_TOKEN,
            "X-Device-ID":        str(uuid.uuid4()),
            "X-Session-ID":       str(uuid.uuid4()),
        },
        timeout=15,
    )
    
    if r.status_code == 200:
        token = r.json().get("data", {}).get("token", "")
        return token, dict(session.cookies)
    
    print(f"  ❌ Token request failed: {r.status_code} — {r.text[:200]}")
    return None, None


async def connect_viewer(token, viewer_id=1):
    """Conectar al viewer WS y enviar handshake"""
    ws_url = f"{WS_BASE_URL}?token={token}"
    
    ssl_ctx = ssl.create_default_context()
    ssl_ctx.check_hostname = False
    ssl_ctx.verify_mode    = ssl.CERT_NONE
    
    headers = {
        "User-Agent": UA,
        "Origin":     "https://kick.com",
    }
    
    try:
        async with websockets.connect(
            ws_url,
            additional_headers=headers,
            ssl=ssl_ctx,
            open_timeout=10,
            ping_interval=None,
        ) as ws:
            print(f"  ✅ Viewer {viewer_id}: CONECTADO al viewer WS!")
            
            # Enviar channel_handshake
            handshake = json.dumps({
                "type": "channel_handshake",
                "data": {
                    "message": {
                        "channelId": CHANNEL_ID
                    }
                }
            })
            await ws.send(handshake)
            print(f"  → Viewer {viewer_id}: channel_handshake enviado (channel {CHANNEL_ID})")
            
            # Escuchar respuestas iniciales
            for _ in range(3):
                try:
                    msg = await asyncio.wait_for(ws.recv(), timeout=5)
                    print(f"  ← Viewer {viewer_id}: {str(msg)[:150]}")
                except asyncio.TimeoutError:
                    break
            
            # Mantener conexión con pings y re-handshakes
            iteration = 0
            while True:
                await asyncio.sleep(15)
                iteration += 1
                
                try:
                    # Re-handshake cada 15s (como hace el JS de Kick)
                    await ws.send(handshake)
                    
                    # Ping cada 30s
                    if iteration % 2 == 0:
                        await ws.send(json.dumps({"type": "ping"}))
                    
                    print(f"  ♻️  Viewer {viewer_id}: keepalive #{iteration} (uptime {iteration*15}s)")
                    
                    # Leer mensajes pendientes
                    try:
                        msg = await asyncio.wait_for(ws.recv(), timeout=1)
                        print(f"  ← Viewer {viewer_id}: {str(msg)[:100]}")
                    except asyncio.TimeoutError:
                        pass
                        
                except Exception as e:
                    print(f"  ⚠️  Viewer {viewer_id}: conexión perdida — {e}")
                    break
                    
    except Exception as e:
        print(f"  ❌ Viewer {viewer_id}: {type(e).__name__}: {e}")


async def main():
    print("╔══════════════════════════════════════════════════════════╗")
    print("║  KICK VIEWER WS — CONEXIÓN DIRECTA (SIN BROWSER)      ║")
    print("║  Método: curl_cffi + viewer/v1/token + WSS             ║")
    print("╚══════════════════════════════════════════════════════════╝\n")
    
    NUM_VIEWERS = 3  # Test con 3 viewers primero
    
    tasks = []
    
    for i in range(1, NUM_VIEWERS + 1):
        print(f"\n─── Viewer {i} ───")
        print(f"  Obteniendo token #{i}...")
        
        token, cookies = get_viewer_token()
        if not token:
            print(f"  ❌ No se pudo obtener token para viewer {i}")
            continue
        
        print(f"  🔑 Token: {token[:40]}...")
        
        tasks.append(connect_viewer(token, i))
        
        # Esperar entre tokens para no saturar
        if i < NUM_VIEWERS:
            await asyncio.sleep(2)
    
    if tasks:
        print(f"\n{'='*58}")
        print(f"  {len(tasks)} viewers conectándose al WS...")
        print(f"  Verifica en https://kick.com/{CHANNEL_SLUG} si se reflejan")
        print(f"  Ctrl+C para detener")
        print(f"{'='*58}\n")
        
        await asyncio.gather(*tasks)
    else:
        print("\n  ❌ No se pudieron obtener tokens")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n  Detenido.")
