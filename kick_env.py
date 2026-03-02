"""kick_env.py — Extrae todas las variables NEXT_PUBLIC del bundle de configuración"""
import re
from curl_cffi import requests as cffi_requests

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"

r = cffi_requests.get(
    "https://kick.com/_next/static/chunks/854-505c73ea839639ba.js",
    headers={"User-Agent": UA, "Accept": "*/*", "Referer": "https://kick.com/jhonramirez22"},
    timeout=20, impersonate="chrome131"
)
c = r.text
print(f"Bundle size: {len(c)} chars\n")

# Extraer TODOS los env vars NEXT_PUBLIC con sus valores
all_envs = re.findall(r'NEXT_PUBLIC_(\w+)[:\s\"=,]+\"([^\"]{1,150})\"', c)
seen = {}
for k, v in all_envs:
    if k not in seen:
        seen[k] = v

print("=== NEXT_PUBLIC env vars ===")
for k, v in seen.items():
    print(f"  NEXT_PUBLIC_{k}: {v}")

print("\n=== CLIENT TOKEN ===")
for m in re.finditer(r"CLIENT_TOKEN[^;,\n]{0,300}", c, re.IGNORECASE):
    print(m.group(0)[:300])

print("\n=== WEBSOCKET CONFIG COMPLETA ===")
# Buscar el objeto de config completo
for m in re.finditer(r"WEBSOCKET[^;,\n]{0,300}", c, re.IGNORECASE):
    print(m.group(0)[:300])

print("\n=== PUSHER COMPLETO ===")
for m in re.finditer(r"PUSHER[^;,\n]{0,200}", c, re.IGNORECASE):
    print(m.group(0)[:200])

# Buscar el objeto de config completo con todos los valores hardcodeados
print("\n=== OBJETO CONFIG HARDCODEADO ===")
idx = c.find("NEXT_PUBLIC_BASE_API_URL")
if idx >= 0:
    print(c[max(0, idx-100):idx+1500])
