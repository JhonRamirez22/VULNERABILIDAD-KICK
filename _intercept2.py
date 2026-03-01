"""
Interceptor v2: Usar Chrome real con CDP para capturar WS frames.
Abre Chrome SIN headless y espera más tiempo.
"""
import json, asyncio, time, sys
from playwright.async_api import async_playwright

CHANNEL = "jhonramirez22"

async def main():
    print("="*60)
    print("INTERCEPTOR WS v2 — Chrome real + más tiempo")  
    print("="*60)
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=False,
            args=[
                '--disable-blink-features=AutomationControlled',
                '--no-sandbox',
                '--disable-web-security',
                '--disable-features=IsolateOrigins,site-per-process',
            ]
        )
        context = await browser.new_context(
            viewport={'width': 1280, 'height': 720},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
            bypass_csp=True,
        )
        
        # Anti-detection
        await context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            window.chrome = { runtime: {} };
        """)
        
        page = await context.new_page()

        ws_data = {'connections': [], 'messages': []}

        def handle_ws(ws):
            url = ws.url
            ws_data['connections'].append({'url': url, 'time': time.time()})
            print(f"\n[WS ABIERTO] {url[:100]}")
            
            def on_sent(payload):
                ws_data['messages'].append({
                    'd': 'send', 'url': url[:100],
                    'data': payload if isinstance(payload, str) else f'[bin:{len(payload)}]',
                    't': time.time()
                })
                if isinstance(payload, str):
                    print(f"  →SEND: {payload[:300]}")
                else:
                    print(f"  →SEND: [BINARY {len(payload)} bytes] {payload[:80]}")
            
            def on_recv(payload):
                ws_data['messages'].append({
                    'd': 'recv', 'url': url[:100],
                    'data': payload if isinstance(payload, str) else f'[bin:{len(payload)}]',
                    't': time.time()
                })
                if isinstance(payload, str):
                    print(f"  ←RECV: {payload[:300]}")
                else:
                    print(f"  ←RECV: [BINARY {len(payload)} bytes] {payload[:80]}")
            
            def on_close():
                print(f"  [WS CERRADO] {url[:80]}")
            
            ws.on('framesent', on_sent)
            ws.on('framereceived', on_recv)
            ws.on('close', on_close)

        page.on('websocket', handle_ws)
        
        # También capturar token request
        async def on_response(response):
            if 'viewer/v1/token' in response.url:
                print(f"\n[TOKEN] {response.status} {response.url}")
                try:
                    body = await response.text()
                    print(f"  Response: {body[:500]}")
                except:
                    pass
            if 'viewer/v1/connect' in response.url:
                print(f"\n[WS UPGRADE] {response.status} {response.url}")
                
        page.on('response', on_response)
        
        print(f"\nNavegando a https://kick.com/{CHANNEL}...")
        try:
            await page.goto(f'https://kick.com/{CHANNEL}', timeout=60000, wait_until='domcontentloaded')
        except Exception as e:
            print(f"Navigation: {e}")
        
        print("\nPágina cargada. Esperando 45s para WS connections...")
        print("(Si aparece CF challenge, resuélvelo manualmente en el browser)\n")
        
        for i in range(45):
            await asyncio.sleep(1)
            if i % 10 == 0:
                print(f"  ... {i}s ({len(ws_data['connections'])} WS, {len(ws_data['messages'])} msgs)")
        
        # Resumen
        print(f"\n{'='*60}")
        print(f"CAPTURA COMPLETADA")
        print(f"{'='*60}")
        print(f"Conexiones WS: {len(ws_data['connections'])}")
        print(f"Mensajes WS  : {len(ws_data['messages'])}")
        
        for c in ws_data['connections']:
            print(f"\n  WS: {c['url']}")
        
        print(f"\nMensajes:")
        for m in ws_data['messages'][:50]:
            arrow = "→" if m['d'] == 'send' else "←"
            print(f"  {arrow} [{m['url'][:50]}] {str(m['data'])[:200]}")
        
        with open('_ws_capture2.json', 'w') as f:
            json.dump(ws_data, f, indent=2, default=str)
        print("\nGuardado en _ws_capture2.json")
        
        input("\nPresiona Enter para cerrar...")
        await browser.close()


if __name__ == '__main__':
    asyncio.run(main())
