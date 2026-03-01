"""
Extraer el WebSocketProvider COMPLETO del layout bundle de Kick.
Necesitamos entender CÓMO se crea el WebSocket y cómo se conecta.
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
print(f"Layout bundle: {len(code)} chars\n")

# Encontrar el módulo 5677 que contiene WebSocketProvider
idx = code.find('5677:(e,t,l)=>')
if idx < 0:
    idx = code.find('WebSocketProvider')
    
print(f"WebSocketProvider encontrado en offset: {idx}")

# Extraer un bloque GRANDE del módulo 5677
block = code[idx:idx+8000]
print("\n===== MODULO WebSocketProvider (5677) =====\n")
print(block)

# También extraer el módulo de la función que hace el token fetch (d.token)
print("\n\n===== BUSCANDO fetch/token/viewer helpers =====\n")

# Buscar la función que obtiene el token viewer (es parte del módulo 5677)
# d.token usa (0,o.A6) que es un fetch helper
for m in re.finditer(r'(A6|fetch|viewerToken|getToken).{0,800}', code):
    text = m.group(0)[:400]
    if 'viewer' in text.lower() or '/v1/token' in text:
        print("=== TOKEN HELPER ===")
        print(text)
        print()

# Buscar cómo se crea el ReconnectingWebSocket o WebSocket nativo
print("\n===== BUSCANDO WebSocket constructor =====\n")
for m in re.finditer(r'(ReconnectingWebSocket|createWebSocket|new WebSocket).{0,1000}', code):
    print("=== WS CONSTRUCTOR ===")
    print(m.group(0)[:800])
    print()

# Buscar el módulo que define A6 (la función de fetch)
print("\n===== BUSCANDO módulo A6 (fetch helper) =====\n")
for m in re.finditer(r'A6.{0,50}(function|=>).{0,600}', code):
    text = m.group(0)[:500]
    if 'fetch' in text.lower() or 'url' in text.lower() or 'http' in text.lower():
        print("=== A6 ===")
        print(text)
        print()

# Buscar el ReconnectingWebSocket o ws library que usa
print("\n===== BUSCANDO ReconnectingWebSocket library =====\n")
for m in re.finditer(r'.{0,100}reconnect.{0,400}', code, re.IGNORECASE):
    text = m.group(0)
    if 'websocket' in text.lower() or 'ws' in text.lower():
        print(text[:500])
        print("---")

# Buscar qué pasa después de que se abre el WS
print("\n===== ONOPEN handler completo =====\n")
for m in re.finditer(r'onOpen.{0,2000}', code):
    text = m.group(0)[:1500]
    if 'connection' in text.lower() or 'state' in text.lower() or 'send' in text.lower():
        print(text)
        print("---")

# Buscar la URL de conexión del WS
print("\n===== WS URL construction =====\n")
for m in re.finditer(r'(WEBSOCKET_CONNECTION_URL|viewer/v1/connect).{0,500}', code):
    print(m.group(0)[:400])
    print("---")
