"""
Depuración profunda del viewer WS de Kick.
Captura TODOS los mensajes del servidor para entender el protocolo.
"""
import json, uuid, time, asyncio, ssl, sys
from curl_cffi import requests as cffi_requests
import websockets

CHANNEL_ID   = "54451863"
CHANNEL_SLUG = "jhonramirez22"
CLIENT_TOKEN = "e1393935a959b4020a4491574f6490129f678acdaa92760471263db43487f823"
WS_BASE_URL  = "wss://websockets.kick.com/viewer/v1/connect"
UA           = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"


def get_token():
    session = cffi_requests.Session(impersonate="chrome131")
    session.get(f"https://kick.com/{CHANNEL_SLUG}",
        headers={"User-Agent": UA, "Accept": "text/html,*/*",
                 "sec-fetch-dest": "document", "sec-fetch-mode": "navigate"},
        timeout=20)
    r = session.get("https://websockets.kick.com/viewer/v1/token",
        headers={
            "User-Agent": UA,
            "Accept": "application/json, text/plain, */*",
            "sec-ch-ua": '"Google Chrome";v="131", "Chromium";v="131"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"',
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-site",
            "Origin": "https://kick.com",
            "Referer": f"https://kick.com/{CHANNEL_SLUG}",
            "X-CLIENT-TOKEN": CLIENT_TOKEN,
            "X-Device-ID": str(uuid.uuid4()),
            "X-Session-ID": str(uuid.uuid4()),
        }, timeout=15)
    print(f"Token status: {r.status_code}")
    if r.status_code == 200:
        data = r.json()
        print(f"Token response: {json.dumps(data, indent=2)}")
        return data.get("data", {}).get("token", "")
    else:
        print(f"Token error: {r.text[:500]}")
        return None


async def debug_viewer_ws():
    token = get_token()
    if not token:
        print("No token!")
        return

    print(f"\nToken: {token}")
    ws_url = f"{WS_BASE_URL}?token={token}"
    print(f"Connecting to: {ws_url}\n")

    ssl_ctx = ssl.create_default_context()
    ssl_ctx.check_hostname = False
    ssl_ctx.verify_mode = ssl.CERT_NONE

    async with websockets.connect(
        ws_url,
        additional_headers={"User-Agent": UA, "Origin": "https://kick.com"},
        ssl=ssl_ctx,
        open_timeout=10,
        ping_interval=None,
    ) as ws:
        print("=== CONNECTED ===\n")

        # Escuchar mensajes iniciales del servidor (antes de enviar nada)
        print("--- Esperando mensajes iniciales del servidor (5s) ---")
        for _ in range(5):
            try:
                msg = await asyncio.wait_for(ws.recv(), timeout=1)
                if isinstance(msg, bytes):
                    print(f"[BINARY] {len(msg)} bytes: {msg[:200]}")
                else:
                    print(f"[TEXT]   {msg}")
            except asyncio.TimeoutError:
                print("  (sin mensaje)")

        # Enviar handshake versión 1: como lo tenemos ahora
        print("\n--- Enviando handshake v1 (actual) ---")
        hs1 = json.dumps({
            "type": "channel_handshake",
            "data": {"message": {"channelId": CHANNEL_ID}}
        })
        print(f"SEND: {hs1}")
        await ws.send(hs1)

        print("--- Respuestas post-handshake (10s) ---")
        for _ in range(10):
            try:
                msg = await asyncio.wait_for(ws.recv(), timeout=1)
                if isinstance(msg, bytes):
                    print(f"[BINARY] {len(msg)} bytes: {msg[:200]}")
                else:
                    print(f"[TEXT]   {msg}")
            except asyncio.TimeoutError:
                print("  (sin mensaje)")

        # Variante 2: channelId como INT
        print("\n--- Enviando handshake v2 (channelId como int) ---")
        hs2 = json.dumps({
            "type": "channel_handshake",
            "data": {"message": {"channelId": 54451863}}
        })
        print(f"SEND: {hs2}")
        await ws.send(hs2)

        for _ in range(5):
            try:
                msg = await asyncio.wait_for(ws.recv(), timeout=1)
                print(f"[TEXT]   {msg}")
            except asyncio.TimeoutError:
                print("  (sin mensaje)")

        # Variante 3: channelId directo (sin wrapping en message)
        print("\n--- Enviando handshake v3 (sin wrapper message) ---")
        hs3 = json.dumps({
            "type": "channel_handshake",
            "data": {"channelId": CHANNEL_ID}
        })
        print(f"SEND: {hs3}")
        await ws.send(hs3)

        for _ in range(5):
            try:
                msg = await asyncio.wait_for(ws.recv(), timeout=1)
                print(f"[TEXT]   {msg}")
            except asyncio.TimeoutError:
                print("  (sin mensaje)")

        # Variante 4: channelId como int directo
        print("\n--- Enviando handshake v4 (int, sin wrapper) ---")
        hs4 = json.dumps({
            "type": "channel_handshake",
            "data": {"channelId": 54451863}
        })
        print(f"SEND: {hs4}")
        await ws.send(hs4)

        for _ in range(5):
            try:
                msg = await asyncio.wait_for(ws.recv(), timeout=1)
                print(f"[TEXT]   {msg}")
            except asyncio.TimeoutError:
                print("  (sin mensaje)")

        # Variante 5: data como string (como Pusher hace)
        print("\n--- Enviando handshake v5 (data como string JSON) ---")
        hs5 = json.dumps({
            "type": "channel_handshake",
            "data": json.dumps({"message": {"channelId": CHANNEL_ID}})
        })
        print(f"SEND: {hs5}")
        await ws.send(hs5)

        for _ in range(5):
            try:
                msg = await asyncio.wait_for(ws.recv(), timeout=1)
                print(f"[TEXT]   {msg}")
            except asyncio.TimeoutError:
                print("  (sin mensaje)")

        # Mantener vivo y monitorear por 60s más
        print("\n--- Manteniendo conexión (60s, ping cada 15s) ---")
        for i in range(4):
            await asyncio.sleep(15)
            # Re-handshake
            await ws.send(hs1)
            # Ping
            await ws.send(json.dumps({"type": "ping"}))
            print(f"  keepalive #{i+1} (uptime {(i+1)*15}s)")
            # Leer respuestas
            for _ in range(3):
                try:
                    msg = await asyncio.wait_for(ws.recv(), timeout=1)
                    print(f"  [TEXT]   {msg}")
                except asyncio.TimeoutError:
                    pass


async def debug_pusher_ws():
    """También analizar qué datos pasan por Pusher"""
    print("\n\n=== PUSHER WS DEBUG ===")
    PUSHER_KEY = "32cbd69e4b950bf97679"
    ws_url = f"wss://ws-us2.pusher.com/app/{PUSHER_KEY}?protocol=7&client=js&version=8.4.0-rc2&flash=false"

    ssl_ctx = ssl.create_default_context()
    ssl_ctx.check_hostname = False
    ssl_ctx.verify_mode = ssl.CERT_NONE

    async with websockets.connect(
        ws_url,
        additional_headers={"User-Agent": UA, "Origin": "https://kick.com"},
        ssl=ssl_ctx,
        ping_interval=None,
    ) as ws:
        print("Pusher connected!")

        # Esperar connection_established
        msg = await asyncio.wait_for(ws.recv(), timeout=5)
        data = json.loads(msg)
        print(f"Pusher: {json.dumps(data, indent=2)}")

        # Suscribirse al canal del livestream
        for ch in [
            f"channel.{CHANNEL_ID}",
            f"chatrooms.54163483.v2",
            f"private-channel.{CHANNEL_ID}",
            f"presence-channel.{CHANNEL_ID}",
            f"viewer.{CHANNEL_ID}",
            f"livestream.{CHANNEL_ID}",
        ]:
            await ws.send(json.dumps({
                "event": "pusher:subscribe",
                "data": {"channel": ch}
            }))
            print(f"Subscribed to: {ch}")

        # Monitorear mensajes Pusher por 30s
        print("\n--- Mensajes Pusher (30s) ---")
        start = time.time()
        while time.time() - start < 30:
            try:
                msg = await asyncio.wait_for(ws.recv(), timeout=2)
                data = json.loads(msg)
                print(f"  Pusher event: {data.get('event','?')} channel={data.get('channel','?')} data={str(data.get('data',''))[:200]}")
            except asyncio.TimeoutError:
                pass


async def main():
    print("╔══════════════════════════════════════════╗")
    print("║  DEBUG PROFUNDO — Kick Viewer Protocol  ║")
    print("╚══════════════════════════════════════════╝\n")
    await debug_viewer_ws()
    await debug_pusher_ws()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nDetenido.")
