"""
Interceptar la conexión WS REAL del browser al viewer WS de Kick.
Usamos Playwright para abrir kick.com y capturar exactamente:
  - La URL del WS
  - Los headers del WS upgrade
  - Los frames WS enviados/recibidos
"""
import json, asyncio, time
from playwright.async_api import async_playwright

CHANNEL = "jhonramirez22"

async def main():
    print("="*60)
    print("INTERCEPTOR WS — Capturando protocolo REAL")
    print("="*60)
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=False,
            args=[
                '--disable-blink-features=AutomationControlled',
                '--no-sandbox',
            ]
        )
        context = await browser.new_context(
            viewport={'width': 1280, 'height': 720},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
        )
        page = await context.new_page()

        ws_connections = []
        ws_messages = []

        # Interceptar TODOS los WebSockets
        page.on('websocket', lambda ws: handle_ws(ws, ws_connections, ws_messages))
        
        # También interceptar las requests HTTP para ver el token fetch
        async def handle_request(request):
            url = request.url
            if 'viewer' in url or 'token' in url or 'websocket' in url.lower():
                print(f"\n[HTTP] {request.method} {url}")
                headers = request.headers
                for k, v in headers.items():
                    if k.lower() in ['x-client-token', 'x-request-id', 'x-device-id', 
                                      'x-session-id', 'cookie', 'origin', 'referer',
                                      'sec-websocket-protocol', 'sec-websocket-extensions',
                                      'sec-websocket-key', 'sec-websocket-version']:
                        print(f"  {k}: {v}")
        
        async def handle_response(response):
            url = response.url
            if 'viewer/v1/token' in url:
                print(f"\n[HTTP RESPONSE] {response.status} {url}")
                try:
                    body = await response.json()
                    print(f"  Body: {json.dumps(body, indent=2)}")
                except:
                    pass
        
        page.on('request', handle_request)
        page.on('response', handle_response)

        print(f"\nAbriendo https://kick.com/{CHANNEL}...")
        await page.goto(f'https://kick.com/{CHANNEL}', wait_until='domcontentloaded', timeout=30000)
        
        print("Esperando 20s para que se establezcan las conexiones WS...")
        await asyncio.sleep(20)

        print(f"\n\n{'='*60}")
        print(f"RESUMEN: {len(ws_connections)} conexiones WS capturadas")
        print(f"{'='*60}")
        
        for i, wc in enumerate(ws_connections):
            print(f"\nWS #{i+1}: {wc['url']}")
            print(f"  Estado: {wc.get('state', '?')}")
        
        print(f"\n{'='*60}")
        print(f"MENSAJES WS: {len(ws_messages)} capturados")
        print(f"{'='*60}")
        for msg in ws_messages:
            direction = "→ SEND" if msg['direction'] == 'send' else "← RECV"
            print(f"\n[{direction}] WS: {msg['ws_url'][:80]}")
            data = msg['data']
            if isinstance(data, str) and len(data) < 1000:
                print(f"  {data}")
            elif isinstance(data, bytes):
                print(f"  [BINARY] {len(data)} bytes: {data[:100]}")
            else:
                print(f"  [TEXT] {len(data)} chars: {data[:200]}...")

        # Guardar todo en JSON
        output = {
            'connections': ws_connections,
            'messages': [{
                'direction': m['direction'],
                'ws_url': m['ws_url'],
                'data': m['data'] if isinstance(m['data'], str) else f"[binary:{len(m['data'])}]",
                'timestamp': m['timestamp']
            } for m in ws_messages]
        }
        with open('_ws_capture.json', 'w') as f:
            json.dump(output, f, indent=2)
        print("\nGuardado en _ws_capture.json")

        await browser.close()


def handle_ws(ws, connections, messages):
    url = ws.url
    info = {'url': url, 'state': 'open'}
    connections.append(info)
    
    print(f"\n[WS OPEN] {url}")
    
    def on_frame_sent(payload):
        data = payload if isinstance(payload, str) else payload
        messages.append({
            'direction': 'send',
            'ws_url': url,
            'data': data,
            'timestamp': time.time()
        })
        if isinstance(data, str) and len(data) < 500:
            print(f"  [WS→] {url[:60]}... : {data[:200]}")
        elif isinstance(data, bytes):
            print(f"  [WS→] {url[:60]}... : [BINARY {len(data)}b] {data[:50]}")
    
    def on_frame_received(payload):
        data = payload if isinstance(payload, str) else payload
        messages.append({
            'direction': 'recv',
            'ws_url': url,
            'data': data,
            'timestamp': time.time()
        })
        if isinstance(data, str) and len(data) < 500:
            print(f"  [WS←] {url[:60]}... : {data[:200]}")
        elif isinstance(data, bytes):
            print(f"  [WS←] {url[:60]}... : [BINARY {len(data)}b] {data[:50]}")
    
    def on_close():
        info['state'] = 'closed'
        print(f"  [WS CLOSE] {url[:60]}")
    
    ws.on('framesent', on_frame_sent)
    ws.on('framereceived', on_frame_received)
    ws.on('close', on_close)


if __name__ == '__main__':
    asyncio.run(main())
