"""
kick_ws_test.py — Conectar al viewer WS de Kick sin browser
usando el CLIENT_TOKEN extraído de los bundles de Next.js

Descubierto:
  WSS: wss://websockets.kick.com/viewer/v1/connect
  CLIENT_TOKEN: e1393935a959b4020a4491574f6490129f678acdaa92760471263db43487f823
  PUSHER_KEY: 32cbd69e4b950bf97679
  Channel ID: 54451863
"""
import json
import uuid
import time
import asyncio
import websockets
import ssl
import sys

CHANNEL_ID   = "54451863"
CLIENT_TOKEN = "e1393935a959b4020a4491574f6490129f678acdaa92760471263db43487f823"
WS_URL       = "wss://websockets.kick.com/viewer/v1/connect"
PUSHER_KEY   = "32cbd69e4b950bf97679"
PUSHER_WS    = f"wss://ws-us2.pusher.com/app/{PUSHER_KEY}?protocol=7&client=js&version=8.4.0-rc2&flash=false"

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"


async def test_viewer_ws_direct():
    """Conectar al viewer WS directamente con CLIENT_TOKEN"""
    print("\n=== MÉTODO 1: Viewer WS directo con CLIENT_TOKEN ===")

    device_id  = str(uuid.uuid4())
    session_id = str(uuid.uuid4())

    # Probar con el token como parámetro de query
    urls = [
        f"{WS_URL}?token={CLIENT_TOKEN}",
        f"{WS_URL}?client_token={CLIENT_TOKEN}",
        f"{WS_URL}",
    ]

    headers = {
        "User-Agent":      UA,
        "Origin":          "https://kick.com",
        "Sec-WebSocket-Protocol": "protoo",
        "Accept-Language":  "en-US,en;q=0.9",
        "X-Device-ID":     device_id,
        "X-Session-ID":    session_id,
    }

    ssl_ctx = ssl.create_default_context()
    ssl_ctx.check_hostname = False
    ssl_ctx.verify_mode    = ssl.CERT_NONE

    for url in urls:
        try:
            print(f"\n  Intentando: {url[:80]}...")
            async with websockets.connect(
                url,
                additional_headers=headers,
                ssl=ssl_ctx,
                open_timeout=10,
                ping_interval=None,
            ) as ws:
                print(f"  ✅ CONECTADO!")

                # Enviar channel_handshake (como hace el JS de Kick)
                handshake = json.dumps({
                    "type": "channel_handshake",
                    "data": {
                        "message": {
                            "channelId": CHANNEL_ID
                        }
                    }
                })
                await ws.send(handshake)
                print(f"  → SENT: {handshake}")

                # Escuchar respuestas
                for _ in range(5):
                    try:
                        msg = await asyncio.wait_for(ws.recv(), timeout=5)
                        print(f"  ← RECV: {str(msg)[:200]}")
                    except asyncio.TimeoutError:
                        print("  (timeout esperando respuesta)")
                        break

                print("  Manteniendo conexión 15s...")
                await asyncio.sleep(15)

                # Re-enviar handshake (como hace Kick cada 15s)
                await ws.send(handshake)
                print(f"  → RE-SENT handshake")

                await asyncio.sleep(5)
                print("  ✅ Conexión mantenida exitosamente")
                return True

        except Exception as e:
            print(f"  ❌ Error: {type(e).__name__}: {e}")

    return False


async def test_pusher_ws():
    """Conectar al Pusher WS (chat) — este no cuenta viewers pero ayuda"""
    print("\n=== MÉTODO 2: Pusher WS (canal de chat) ===")

    ssl_ctx = ssl.create_default_context()
    ssl_ctx.check_hostname = False
    ssl_ctx.verify_mode    = ssl.CERT_NONE

    try:
        print(f"  Conectando a Pusher WS...")
        async with websockets.connect(
            PUSHER_WS,
            additional_headers={"Origin": "https://kick.com", "User-Agent": UA},
            ssl=ssl_ctx,
            open_timeout=10,
        ) as ws:
            # Esperar mensaje de bienvenida
            msg = await asyncio.wait_for(ws.recv(), timeout=5)
            parsed = json.loads(msg)
            print(f"  ← RECV: {msg[:200]}")

            if parsed.get("event") == "pusher:connection_established":
                data = json.loads(parsed["data"])
                socket_id = data.get("socket_id")
                print(f"  ✅ Socket ID: {socket_id}")

                # Suscribirse al canal de chat
                sub = json.dumps({
                    "event": "pusher:subscribe",
                    "data": {
                        "channel": f"channel.{CHANNEL_ID}"
                    }
                })
                await ws.send(sub)
                print(f"  → SUBSCRIBE: channel.{CHANNEL_ID}")

                # También al chatroom
                sub2 = json.dumps({
                    "event": "pusher:subscribe",
                    "data": {
                        "channel": f"chatrooms.54163483.v2"
                    }
                })
                await ws.send(sub2)
                print(f"  → SUBSCRIBE: chatrooms.54163483.v2")

                # Escuchar
                for _ in range(5):
                    try:
                        msg = await asyncio.wait_for(ws.recv(), timeout=5)
                        print(f"  ← RECV: {str(msg)[:200]}")
                    except asyncio.TimeoutError:
                        break

                return True
    except Exception as e:
        print(f"  ❌ Error: {type(e).__name__}: {e}")

    return False


async def test_viewer_ws_with_token_header():
    """Intentar pasar el CLIENT_TOKEN como header de autorización"""
    print("\n=== MÉTODO 3: Viewer WS con CLIENT_TOKEN en header ===")

    ssl_ctx = ssl.create_default_context()
    ssl_ctx.check_hostname = False
    ssl_ctx.verify_mode = ssl.CERT_NONE

    attempts = [
        {"Authorization": f"Bearer {CLIENT_TOKEN}"},
        {"Authorization": CLIENT_TOKEN},
        {"X-Client-Token": CLIENT_TOKEN},
        {"X-Websocket-Client-Token": CLIENT_TOKEN},
    ]

    for hdrs in attempts:
        try:
            headers = {
                "User-Agent": UA,
                "Origin":     "https://kick.com",
                "X-Device-ID":  str(uuid.uuid4()),
                "X-Session-ID": str(uuid.uuid4()),
                **hdrs,
            }
            label = list(hdrs.keys())[0]
            print(f"\n  [{label}: {list(hdrs.values())[0][:40]}...]")
            async with websockets.connect(
                WS_URL,
                additional_headers=headers,
                ssl=ssl_ctx,
                open_timeout=8,
                ping_interval=None,
            ) as ws:
                print(f"  ✅ CONECTADO con {label}!")

                handshake = json.dumps({
                    "type": "channel_handshake",
                    "data": {"message": {"channelId": CHANNEL_ID}}
                })
                await ws.send(handshake)
                print(f"  → SENT handshake")

                for _ in range(3):
                    try:
                        msg = await asyncio.wait_for(ws.recv(), timeout=5)
                        print(f"  ← RECV: {str(msg)[:200]}")
                    except asyncio.TimeoutError:
                        break
                return True
        except Exception as e:
            print(f"  ❌ {type(e).__name__}: {str(e)[:100]}")

    return False


async def main():
    print("╔══════════════════════════════════════════════════════╗")
    print("║   KICK WS DIRECT CONNECT TEST                      ║")
    print("║   CLIENT_TOKEN: e1393935a959b40...                  ║")
    print("║   Channel ID:   54451863                            ║")
    print("╚══════════════════════════════════════════════════════╝")

    r1 = await test_viewer_ws_direct()
    r2 = await test_pusher_ws()
    r3 = await test_viewer_ws_with_token_header()

    print("\n" + "="*56)
    print("  RESULTADOS:")
    print(f"    Viewer WS directo:        {'✅' if r1 else '❌'}")
    print(f"    Pusher WS:                {'✅' if r2 else '❌'}")
    print(f"    Viewer WS con auth:       {'✅' if r3 else '❌'}")
    print("="*56)


if __name__ == "__main__":
    asyncio.run(main())
