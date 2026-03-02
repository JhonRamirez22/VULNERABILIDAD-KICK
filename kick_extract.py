"""
kick_extract.py — Extrae client_id, viewer token logic y configuración
desde los JS bundles de Next.js de kick.com

Resultados del probe anterior:
  ✅ /api/v1/channels/{slug}         → 200 (channel ID, playback_url)
  ✅ /api/v2/channels/{slug}         → 200 (channel ID, livestream info)
  ✅ HTML 543KB con JS bundles       → contiene config embebida
  ⚠️ api.kick.com /public/v1/*       → 401 (necesita Bearer)
  🔒 websockets.kick.com /viewer/v1/token → 403 (necesita cookie CF)

Objetivo: encontrar client_id de OAuth + lógica exacta del viewer token
"""
import re
import json
import sys
import uuid
from curl_cffi import requests as cffi_requests

CHANNEL = "jhonramirez22"
UA      = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"

HEADERS_NAV = {
    "User-Agent":              UA,
    "Accept":                  "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
    "Accept-Language":         "en-US,en;q=0.9",
    "Accept-Encoding":         "gzip, deflate, br",
    "sec-ch-ua":               '"Google Chrome";v="131", "Chromium";v="131", "Not_A Brand";v="24"',
    "sec-ch-ua-mobile":        "?0",
    "sec-ch-ua-platform":      '"Windows"',
    "sec-fetch-dest":          "document",
    "sec-fetch-mode":          "navigate",
    "sec-fetch-site":          "none",
    "Upgrade-Insecure-Requests": "1",
}

HEADERS_JS = {
    "User-Agent":         UA,
    "Accept":             "*/*",
    "Accept-Language":    "en-US,en;q=0.9",
    "Accept-Encoding":    "gzip, deflate, br",
    "sec-ch-ua":          '"Google Chrome";v="131", "Chromium";v="131", "Not_A Brand";v="24"',
    "sec-ch-ua-mobile":   "?0",
    "sec-ch-ua-platform": '"Windows"',
    "sec-fetch-dest":     "script",
    "sec-fetch-mode":     "no-cors",
    "sec-fetch-site":     "same-origin",
    "Referer":            f"https://kick.com/{CHANNEL}",
}

def get(url, headers):
    try:
        r = cffi_requests.get(url, headers=headers, timeout=20, impersonate="chrome131", allow_redirects=True)
        return r
    except Exception as e:
        print(f"  ERR {url[:60]}: {e}")
        return None

def search_in_js(content, label):
    """Buscar patrones relevantes en un JS bundle"""
    findings = {}
    
    patterns = {
        "viewer_token_url":  r'(viewer/v1/token[^"\']{0,50})',
        "viewer_ws_url":     r'(viewer/v1/connect[^"\']{0,50})',
        "client_id":         r'client[_-]?id["\s:=,\(]+["\']?([a-zA-Z0-9\-_]{8,60})["\']?',
        "client_secret":     r'client[_-]?secret["\s:=,\(]+["\']?([a-zA-Z0-9\-_]{8,80})["\']?',
        "oauth_token_url":   r'(oauth[^"\'<>]{0,60}token[^"\'<>]{0,30})',
        "pusher_key":        r'pusher[_A-Z]*key["\s:=,\(]+["\']?([a-zA-Z0-9]{10,40})["\']?',
        "pusher_cluster":    r'pusher[_A-Z]*cluster["\s:=,\(]+["\']?([a-zA-Z0-9\-]{2,10})["\']?',
        "x_device_id":       r'[xX]-?[dD]evice-?[iI][dD][^a-zA-Z]',
        "x_session_id":      r'[xX]-?[sS]ession-?[iI][dD][^a-zA-Z]',
        "api_base":          r'(https?://(?:api|ws|websocket)[a-zA-Z0-9.\-]*kick\.com[^"\']{0,60})',
        "bearer_header":     r'[Bb]earer[^a-zA-Z0-9][^"\']{0,100}',
        "channel_handshake": r'(channel.handshake[^"\']{0,80})',
        "viewer_count":      r'(viewer[_A-Z]*count[^"\']{0,50})',
    }
    
    for key, pat in patterns.items():
        matches = re.findall(pat, content, re.IGNORECASE)
        if matches:
            unique = list(dict.fromkeys(
                (m if isinstance(m, str) else m[-1])[:120] for m in matches[:5]
            ))
            findings[key] = unique
            
    return findings

def main():
    print("\n" + "═"*60)
    print("   KICK JS BUNDLE EXTRACTOR")
    print("═"*60)

    # ── 1. Obtener HTML completo con cookies CF ──────────────────
    print("\n[1] Cargando página principal...")
    r_html = get(f"https://kick.com/{CHANNEL}", HEADERS_NAV)
    
    if not r_html or r_html.status_code != 200:
        print(f"  ERROR: status {r_html.status_code if r_html else 'N/A'}")
        sys.exit(1)
    
    html = r_html.text
    cookies = dict(r_html.cookies)
    print(f"  ✅ HTML: {len(html)} bytes | Cookies: {list(cookies.keys())}")

    # ── 2. Extraer __NEXT_DATA__ (datos SSR de Next.js) ──────────
    print("\n[2] Extrayendo __NEXT_DATA__...")
    next_match = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.+?)</script>', html, re.DOTALL)
    
    if next_match:
        try:
            next_data = json.loads(next_match.group(1))
            print(f"  ✅ __NEXT_DATA__: {len(next_match.group(1))} bytes")
            
            # Buscar datos del canal en Next.js SSR
            text_nd = json.dumps(next_data)
            
            for field in ["id", "slug", "viewers", "channel_id", "is_live", "livestream",
                          "client_id", "pusher", "token", "playback", "access"]:
                idxs = [m.start() for m in re.finditer(f'"{field}"', text_nd, re.IGNORECASE)]
                for idx in idxs[:2]:
                    snippet = text_nd[idx:idx+150]
                    if any(v in snippet.lower() for v in ["jhon", "54451", "55578", "token", "key", "secret"]):
                        print(f"  → {field}: {snippet[:120]}")
                        break
        except Exception as e:
            print(f"  Parse error: {e}")
    else:
        print("  No encontrado — Next.js app router (sin SSR data)")

    # ── 3. Extraer URLs de JS bundles ────────────────────────────
    print("\n[3] Extrayendo JS bundles críticos...")
    
    js_urls = re.findall(r'"(/_next/static/chunks/[^"]+\.js)"', html)
    # También buscar en script tags
    script_srcs = re.findall(r'<script[^>]+src="(/_next/[^"]+\.js)"', html)
    all_js = list(dict.fromkeys(js_urls + script_srcs))
    
    print(f"  Bundles encontrados: {len(all_js)}")
    
    # Priorizar bundles que probablemente tienen la lógica de viewer
    priority_keywords = ["websocket", "viewer", "kick", "player", "stream", "auth", "ws", "pusher", "channel"]
    priority = [u for u in all_js if any(k in u.lower() for k in priority_keywords)]
    other    = [u for u in all_js if u not in priority]
    
    ordered = priority + other[:10]  # máximo 10 bundles no-prioritarios
    print(f"  Bundles prioritarios: {len(priority)} | Total a analizar: {len(ordered)}")

    # ── 4. Descargar y analizar cada bundle ──────────────────────
    print("\n[4] Analizando bundles...")
    
    all_findings = {}
    headers_js_with_cookies = {**HEADERS_JS}
    if cookies:
        headers_js_with_cookies["Cookie"] = "; ".join(f"{k}={v}" for k, v in cookies.items())
    
    for js_path in ordered:
        js_url = "https://kick.com" + js_path
        r_js = get(js_url, headers_js_with_cookies)
        if not r_js or r_js.status_code != 200:
            continue
        
        content = r_js.text
        findings = search_in_js(content, js_path)
        
        if findings:
            print(f"\n  📦 {js_path[-60:]}")
            for key, vals in findings.items():
                for v in vals:
                    print(f"     {key}: {v[:100]}")
            all_findings.update(findings)

    # ── 5. API v1 completa del canal ─────────────────────────────
    print("\n[5] Obteniendo datos completos del canal via API v1...")
    
    api_headers = {
        "User-Agent":         UA,
        "Accept":             "application/json",
        "Accept-Language":    "en-US,en;q=0.9",
        "sec-ch-ua":          '"Google Chrome";v="131", "Chromium";v="131", "Not_A Brand";v="24"',
        "sec-ch-ua-mobile":   "?0",
        "sec-ch-ua-platform": '"Windows"',
        "sec-fetch-dest":     "empty",
        "sec-fetch-mode":     "cors",
        "sec-fetch-site":     "same-origin",
        "Referer":            f"https://kick.com/{CHANNEL}",
    }
    if cookies:
        api_headers["Cookie"] = "; ".join(f"{k}={v}" for k, v in cookies.items())
    
    r_api = get(f"https://kick.com/api/v1/channels/{CHANNEL}", api_headers)
    if r_api and r_api.status_code == 200:
        try:
            data = r_api.json()
            print(f"\n  ✅ Channel data:")
            important = {
                "id":            data.get("id"),
                "user_id":       data.get("user_id"),
                "slug":          data.get("slug"),
                "chatroom_id":   data.get("chatroom", {}).get("id"),
                "is_live":       data.get("livestream") is not None,
                "viewers":       data.get("livestream", {}).get("viewers") if data.get("livestream") else 0,
                "channel_title": data.get("livestream", {}).get("session_title") if data.get("livestream") else None,
                "playback_url":  data.get("playback_url", "")[:80] + "...",
            }
            for k, v in important.items():
                print(f"    {k}: {v}")
            
            # Guardar para uso en el bot principal
            with open("kick_channel_data.json", "w") as f:
                json.dump(data, f, indent=2, default=str)
            print("\n  💾 Datos guardados en kick_channel_data.json")
        except Exception as e:
            print(f"  Parse error: {e}")

    # ── 6. Intentar /viewer/v1/token con cookies de CF ───────────
    print("\n[6] Intentando /viewer/v1/token con cookies CF reales...")
    
    token_headers = {
        "User-Agent":         UA,
        "Accept":             "application/json, text/plain, */*",
        "Accept-Language":    "en-US,en;q=0.9",
        "sec-ch-ua":          '"Google Chrome";v="131", "Chromium";v="131", "Not_A Brand";v="24"',
        "sec-ch-ua-mobile":   "?0",
        "sec-ch-ua-platform": '"Windows"',
        "sec-fetch-dest":     "empty",
        "sec-fetch-mode":     "cors",
        "sec-fetch-site":     "same-site",
        "Referer":            f"https://kick.com/{CHANNEL}",
        "Origin":             "https://kick.com",
        "X-Device-ID":        str(uuid.uuid4()),
        "X-Session-ID":       str(uuid.uuid4()),
    }
    if cookies:
        token_headers["Cookie"] = "; ".join(f"{k}={v}" for k, v in cookies.items())
    
    r_token = get("https://websockets.kick.com/viewer/v1/token", token_headers)
    if r_token:
        print(f"  Status: {r_token.status_code}")
        print(f"  Body: {r_token.text[:500]}")
        if r_token.status_code == 200:
            print("\n  🎯 VIEWER TOKEN OBTENIDO!")
            try:
                td = r_token.json()
                print(json.dumps(td, indent=2))
                with open("kick_viewer_token.json", "w") as f:
                    json.dump(td, f, indent=2)
            except Exception:
                pass

    # ── 7. Resumen ───────────────────────────────────────────────
    print("\n" + "═"*60)
    print("   RESUMEN")
    print("═"*60)
    print(f"  Cookies CF obtenidas: {list(cookies.keys()) if cookies else 'ninguna'}")
    if all_findings:
        for k, v in all_findings.items():
            print(f"  {k}: {v[0][:100] if v else 'N/A'}")

if __name__ == "__main__":
    main()
