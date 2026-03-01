"""
Extraer el módulo ReconnectingWebSocket (2729) y el módulo fetch (66065/A6)
del layout bundle para ver si hay algo especial en la conexión WS.
"""
import re
from curl_cffi import requests as cffi_requests

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"

session = cffi_requests.Session(impersonate="chrome131")
r = session.get(
    "https://kick.com/_next/static/chunks/app/%5Blocale%5D/(base)/layout-7d57115784d4f674.js",
    headers={"User-Agent": UA, "Referer": "https://kick.com/"},
    timeout=25)
code = r.text

# Encontrar módulo 2729 (ReconnectingWebSocket)
idx = code.find('2729:')
if idx >= 0:
    block = code[idx:idx+10000]
    print("===== MÓDULO 2729 (ReconnectingWebSocket) =====\n")
    print(block[:8000])
else:
    print("Módulo 2729 no encontrado en layout bundle")
    # Buscar en otros chunks
    print("Buscando 'h3' y 'ReconnectingWebSocket' en otros chunks...")
    
    html = session.get("https://kick.com/jhonramirez22",
        headers={"User-Agent": UA, "Accept": "text/html,*/*"}, timeout=20).text
    chunks = re.findall(r'/_next/static/chunks/(\d+)-[a-f0-9]+\.js', html)
    
    for chunk_id in chunks:
        chunk_url_pattern = f'/_next/static/chunks/{chunk_id}-'
        matches = re.findall(f'/_next/static/chunks/{chunk_id}-[a-f0-9]+\\.js', html)
        if matches:
            url = f"https://kick.com{matches[0]}"
            try:
                r2 = session.get(url, headers={"User-Agent": UA}, timeout=15)
                if '2729:' in r2.text or 'ReconnectingWebSocket' in r2.text or 'reconnect' in r2.text.lower():
                    idx2 = r2.text.find('2729:')
                    if idx2 < 0:
                        idx2 = r2.text.lower().find('reconnectingwebsocket')
                    if idx2 >= 0:
                        print(f"\n=== Found in {url} at offset {idx2} ===")
                        print(r2.text[max(0,idx2-100):idx2+5000])
                        break
            except:
                pass

print("\n\n===== MÓDULO 66065 (fetch A6) =====\n")
idx = code.find('66065:')
if idx >= 0:
    block = code[idx:idx+5000]
    print(block[:4000])
else:
    # Try to find A6 definition
    for m in re.finditer(r'd\(t,\{A6.{0,3000}', code):
        print("A6 export:")
        print(m.group(0)[:2000])
        break

print("\n\n===== MÓDULO 83437 (c.on) — Websocket base URLs =====\n")
idx = code.find('83437:')
if idx >= 0:
    block = code[idx:idx+3000]
    print(block[:2000])

# Buscar todas las URLs de websockets.kick.com
print("\n\n===== TODAS las URLs websockets.kick.com =====\n")
for m in re.finditer(r'websockets\.kick\.com[^"\'`\s]{0,200}', code):
    print(m.group(0))
