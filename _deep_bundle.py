"""
Análisis profundo del bundle layout de Kick para entender el protocolo WS viewer.
Busca el formato EXACTO de los mensajes que envía el cliente.
"""
import re, json
from curl_cffi import requests as cffi_requests

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"

# Primero obtener la lista actual de chunks
print("=== Descargando página principal ===")
session = cffi_requests.Session(impersonate="chrome131")
html = session.get("https://kick.com/jhonramirez22",
    headers={"User-Agent": UA, "Accept": "text/html,*/*"},
    timeout=20).text
print(f"HTML: {len(html)} chars")

# Encontrar todos los JS chunks
chunks = re.findall(r'/_next/static/chunks/[^"\']+\.js', html)
print(f"Chunks encontrados: {len(chunks)}")

# Buscar el layout chunk actual
layout_chunks = [c for c in chunks if 'layout' in c]
print(f"Layout chunks: {layout_chunks}")

# Descargar el layout chunk
for chunk_path in layout_chunks:
    url = f"https://kick.com{chunk_path}"
    print(f"\n=== Descargando: {url} ===")
    r = session.get(url, headers={"User-Agent": UA, "Referer": "https://kick.com/"}, timeout=25)
    code = r.text
    print(f"Tamaño: {len(code)} chars")
    
    # Buscar TODO lo relacionado con WebSocket
    print("\n--- Búsqueda: WebSocket, viewer, handshake, connect ---\n")
    
    # 1. channel_handshake - formato exacto
    for m in re.finditer(r'.{200}channel_handshake.{500}', code):
        print("=== CHANNEL_HANDSHAKE CONTEXT ===")
        print(m.group(0))
        print()
    
    # 2. Cómo se construye el mensaje WS
    for m in re.finditer(r'.{100}\.send\(.{0,500}', code):
        text = m.group(0)
        if any(k in text.lower() for k in ['handshake', 'channel', 'ping', 'viewer']):
            print("=== WS SEND ===")
            print(text[:600])
            print()
    
    # 3. WebSocket connection y onopen
    for m in re.finditer(r'.{100}(onopen|addEventListener\("open"|\.on\("open).{0,500}', code):
        print("=== WS ONOPEN ===")
        print(m.group(0)[:600])
        print()
    
    # 4. Buscar la clase/función del WS provider
    for m in re.finditer(r'.{50}WebSocket(?:Provider|Connection|Manager|Client).{500}', code):
        print("=== WS PROVIDER ===")
        print(m.group(0)[:800])
        print()
    
    # 5. Buscar "type" patterns que se envían
    for m in re.finditer(r'type:\s*"[^"]+".{0,200}', code):
        text = m.group(0)[:300]
        if any(k in text for k in ['handshake', 'ping', 'channel', 'subscribe', 'connect']):
            print("=== TYPE PATTERN ===")
            print(text)
            print()
    
    # 6. Buscar JSON.stringify con tipos
    for m in re.finditer(r'JSON\.stringify\(\{.{0,400}\}\)', code):
        text = m.group(0)[:500]
        if any(k in text for k in ['type', 'channel', 'handshake']):
            print("=== JSON.stringify ===")
            print(text)
            print()

    # 7. Buscar el constructor del WS con la URL
    for m in re.finditer(r'new\s+WebSocket\([^)]{0,500}\)', code):
        print("=== new WebSocket() ===")
        print(m.group(0)[:500])
        print()

    # 8. Buscar "connect" como función
    for m in re.finditer(r'.{50}(function\s+connect|connect\s*[:=]\s*(async\s+)?function|\bconnect\b\s*\().{300}', code):
        text = m.group(0)
        if any(k in text.lower() for k in ['websocket', 'ws', 'socket', 'viewer', 'token']):
            print("=== CONNECT FUNCTION ===")
            print(text[:500])
            print()

# Ahora buscar en TODOS los chunks por el protocolo viewer WS
print("\n\n===== BUSCANDO EN TODOS LOS CHUNKS =====\n")
for chunk_path in chunks:
    url = f"https://kick.com{chunk_path}"
    try:
        r = session.get(url, headers={"User-Agent": UA}, timeout=15)
        code = r.text
        
        # Solo buscar en chunks que mencionan viewer WS
        if 'channel_handshake' in code or ('viewer' in code.lower() and 'websocket' in code.lower()):
            print(f"\n{'='*60}")
            print(f"CHUNK CON VIEWER WS: {chunk_path} ({len(code)} chars)")
            print(f"{'='*60}")
            
            # Extraer TODO lo relevante
            for m in re.finditer(r'.{100}channel_handshake.{500}', code):
                print("HANDSHAKE:")
                print(m.group(0))
                print()
            
            for m in re.finditer(r'\.send\(.{0,500}', code):
                text = m.group(0)[:400]
                if any(k in text.lower() for k in ['type', 'channel', 'handshake', 'ping']):
                    print("SEND:")
                    print(text)
                    print()

            for m in re.finditer(r'new\s+WebSocket\([^)]{0,500}\)', code):
                print("NEW WS:")
                print(m.group(0)[:500])
                print()

            # Buscar función que crea el WS viewer
            for m in re.finditer(r'.{0,200}viewer.{0,50}(connect|websocket|socket|ws).{0,300}', code, re.IGNORECASE):
                print("VIEWER CONNECT:")
                print(m.group(0)[:500])
                print()
                
    except:
        pass

print("\nDone!")
