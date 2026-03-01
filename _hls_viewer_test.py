"""
TEST DEFINITIVO v2: Consumir stream HLS (Amazon IVS) + WS handshake
para verificar si ambos combinados cuentan como viewer.

Hipótesis: Kick cuenta viewers por consumo del stream HLS vía IVS,
no solo por el WebSocket.
"""
import json, uuid, time, re, asyncio, ssl
from curl_cffi import requests as cffi_requests

CHANNEL_SLUG = "jhonramirez22"
CLIENT_TOKEN = "e1393935a959b4020a4491574f6490129f678acdaa92760471263db43487f823"
WS_URL = "wss://websockets.kick.com/viewer/v1/connect"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"

session = cffi_requests.Session(impersonate="chrome131")

def get_viewers():
    r = session.get(f"https://kick.com/api/v2/channels/{CHANNEL_SLUG}",
        headers={"User-Agent": UA, "Accept": "application/json"}, timeout=15)
    return (r.json().get("livestream") or {}).get("viewers", 0) if r.status_code == 200 else -1

def get_playback_url():
    r = session.get(f"https://kick.com/api/v2/channels/{CHANNEL_SLUG}/playback-url",
        headers={"User-Agent": UA, "Accept": "application/json",
                 "Referer": f"https://kick.com/{CHANNEL_SLUG}"}, timeout=15)
    if r.status_code == 200:
        data = r.json()
        return data.get("data", "")
    return ""

def get_channel_id():
    r = session.get(f"https://kick.com/api/v1/channels/{CHANNEL_SLUG}",
        headers={"User-Agent": UA, "Accept": "application/json"}, timeout=15)
    return str(r.json().get("id", "54451863")) if r.status_code == 200 else "54451863"

def consume_hls_segment(hls_url):
    """Descargar el manifest HLS y consumir un segmento"""
    try:
        # Descargar master playlist
        r = session.get(hls_url,
            headers={"User-Agent": UA, "Accept": "*/*",
                     "Origin": "https://player.kick.com",
                     "Referer": "https://player.kick.com/"},
            timeout=10)
        
        if r.status_code != 200:
            return f"master: {r.status_code}"
        
        # Parsear variant streams
        variants = re.findall(r'#EXT-X-STREAM-INF.*\n(.+)', r.text)
        if not variants:
            return "no variants"
        
        # Tomar la variante de menor calidad (última)
        base = hls_url.rsplit('/', 1)[0]
        variant = variants[-1].strip()
        if not variant.startswith('http'):
            variant = base + '/' + variant
        
        # Descargar variant playlist (media playlist)
        r2 = session.get(variant,
            headers={"User-Agent": UA, "Accept": "*/*",
                     "Origin": "https://player.kick.com",
                     "Referer": "https://player.kick.com/"},
            timeout=10)
        
        if r2.status_code != 200:
            return f"variant: {r2.status_code}"
        
        # Obtener último segmento .ts
        segments = re.findall(r'([^\s]+\.ts[^\s]*)', r2.text)
        if not segments:
            return "no segments"
        
        seg = segments[-1].strip()
        seg_base = variant.rsplit('/', 1)[0]
        if not seg.startswith('http'):
            seg = seg_base + '/' + seg
        
        # Descargar el segmento (esto es lo que realmente "consume" el stream)
        r3 = session.get(seg,
            headers={"User-Agent": UA, "Accept": "*/*",
                     "Origin": "https://player.kick.com",
                     "Referer": "https://player.kick.com/"},
            timeout=10)
        
        return f"OK ({len(r3.content)} bytes)" if r3.status_code == 200 else f"seg: {r3.status_code}"
    
    except Exception as e:
        return f"error: {e}"


print("╔══════════════════════════════════════════════════╗")
print("║  TEST: HLS Consumption + WS → ¿Viewers suben?  ║")
print("╚══════════════════════════════════════════════════╝\n")

# Obtener datos
print("[0] Preparando...")
viewers_before = get_viewers()
channel_id = get_channel_id()
hls_url = get_playback_url()

print(f"  Viewers antes: {viewers_before}")
print(f"  Channel ID: {channel_id}")
print(f"  HLS URL: {hls_url[:80]}...")

if not hls_url:
    print("❌ No HLS URL!")
    exit(1)

# Test 1: Solo HLS (sin WS)
print(f"\n{'='*50}")
print("[TEST 1] Solo consumir HLS (sin WebSocket)")
print(f"{'='*50}")

for i in range(12):
    result = consume_hls_segment(hls_url)
    viewers = get_viewers()
    diff = viewers - viewers_before
    print(f"  [{(i+1)*5}s] HLS: {result} | Viewers: {viewers} ({'+' if diff > 0 else ''}{diff})")
    time.sleep(5)

viewers_after_hls = get_viewers()
print(f"\n  Resultado TEST 1: {viewers_before} → {viewers_after_hls} "
      f"({'FUNCIONA!' if viewers_after_hls > viewers_before else 'No funciona'})")

# Test 2: HLS + WS (como lo haría un browser real)
print(f"\n{'='*50}")
print("[TEST 2] HLS + WebSocket + Handshake (combinado)")
print(f"{'='*50}")

import websockets

async def test_combined():
    viewers_base = get_viewers()
    print(f"  Viewers base: {viewers_base}")
    
    # Obtener token WS
    token_session = cffi_requests.Session(impersonate="chrome131")
    token_session.get(f"https://kick.com/{CHANNEL_SLUG}",
        headers={"User-Agent": UA, "Accept": "text/html,*/*"}, timeout=20)
    
    r = token_session.get("https://websockets.kick.com/viewer/v1/token",
        headers={
            "User-Agent": UA, "Accept": "application/json",
            "Origin": "https://kick.com", "Referer": f"https://kick.com/{CHANNEL_SLUG}",
            "X-CLIENT-TOKEN": CLIENT_TOKEN,
            "X-REQUEST-ID": str(uuid.uuid4()),
        }, timeout=15)
    token = r.json().get("data", {}).get("token", "")
    print(f"  Token: {token}")
    
    # Conectar WS
    ssl_ctx = ssl.create_default_context()
    ssl_ctx.check_hostname = False
    ssl_ctx.verify_mode = ssl.CERT_NONE
    
    async with websockets.connect(
        f"{WS_URL}?token={token}",
        additional_headers={"User-Agent": UA, "Origin": "https://kick.com"},
        ssl=ssl_ctx, open_timeout=10, ping_interval=None,
    ) as ws:
        print("  ✅ WS conectado")
        
        handshake = json.dumps({
            "type": "channel_handshake",
            "data": {"message": {"channelId": channel_id}}
        })
        await ws.send(handshake)
        print("  ✅ Handshake enviado")
        
        # Combinado: consumir HLS cada 5s + keepalive WS
        for i in range(12):
            # HLS
            result = consume_hls_segment(hls_url)
            
            # WS keepalive
            await ws.send(handshake)
            if i % 2 == 0:
                await ws.send(json.dumps({"type": "ping"}))
            
            viewers = get_viewers()
            diff = viewers - viewers_base
            print(f"  [{(i+1)*5}s] HLS: {result} | WS: OPEN | "
                  f"Viewers: {viewers} ({'+' if diff > 0 else ''}{diff})")
            
            await asyncio.sleep(5)
    
    viewers_final = get_viewers()
    print(f"\n  Resultado TEST 2: {viewers_base} → {viewers_final} "
          f"({'FUNCIONA!' if viewers_final > viewers_base else 'No funciona'})")

asyncio.run(test_combined())

print("\n✅ Tests completados!")
