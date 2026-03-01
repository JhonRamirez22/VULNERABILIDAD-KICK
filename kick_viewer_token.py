"""
kick_viewer_token.py — Obtener el viewer JWT token de Kick
usando la lógica exacta extraída del bundle de Next.js

Flujo descubierto:
  GET https://websockets.kick.com/viewer/v1/token
  Headers:
    X-CLIENT-TOKEN: e1393935a959b4020a4491574f6490129f678acdaa92760471263db43487f823
    X-REQUEST-ID: {fingerprint_data} (FingerprintJS)

El endpoint está detrás de Cloudflare.
curl_cffi imita el TLS fingerprint de Chrome → puede pasar CF.
"""
import json
import uuid
import time
import sys
from curl_cffi import requests as cffi_requests

CLIENT_TOKEN = "e1393935a959b4020a4491574f6490129f678acdaa92760471263db43487f823"
CHANNEL      = "jhonramirez22"
UA           = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"


def try_token(session, label, extra_headers=None, cookies=None):
    """Intentar obtener el viewer token con diferentes combinaciones"""
    headers = {
        "User-Agent":         UA,
        "Accept":             "application/json, text/plain, */*",
        "Accept-Language":    "en-US,en;q=0.9",
        "Accept-Encoding":    "gzip, deflate, br",
        "sec-ch-ua":          '"Google Chrome";v="131", "Chromium";v="131", "Not_A Brand";v="24"',
        "sec-ch-ua-mobile":   "?0",
        "sec-ch-ua-platform": '"Windows"',
        "sec-fetch-dest":     "empty",
        "sec-fetch-mode":     "cors",
        "sec-fetch-site":     "same-site",
        "Origin":             "https://kick.com",
        "Referer":            f"https://kick.com/{CHANNEL}",
        "X-CLIENT-TOKEN":     CLIENT_TOKEN,
        "X-Device-ID":        str(uuid.uuid4()),
        "X-Session-ID":       str(uuid.uuid4()),
    }
    if extra_headers:
        headers.update(extra_headers)
    
    try:
        r = session.get(
            "https://websockets.kick.com/viewer/v1/token",
            headers=headers,
            cookies=cookies,
            timeout=15,
        )
        icon = "✅" if r.status_code == 200 else "⚠️" if r.status_code in (401, 400) else "🔒"
        print(f"\n{icon} [{r.status_code}] {label}")
        if r.status_code == 200:
            try:
                data = r.json()
                token = data.get("data", {}).get("token", "")
                print(f"  🎯 TOKEN: {token[:60]}...")
                return token
            except Exception:
                print(f"  Body: {r.text[:300]}")
        else:
            print(f"  Body: {r.text[:200]}")
        return None
    except Exception as e:
        print(f"  💥 [{label}] {e}")
        return None


def main():
    print("╔══════════════════════════════════════════════════════════╗")
    print("║  KICK VIEWER TOKEN EXTRACTION (RE)                     ║")
    print("║  X-CLIENT-TOKEN: e1393935a959b4...                     ║")
    print("╚══════════════════════════════════════════════════════════╝")

    # ── Método A: curl_cffi con sesión persistente (Chrome TLS) ──────
    print("\n=== Método A: curl_cffi sesión persistente ===")
    
    session = cffi_requests.Session(impersonate="chrome131")
    
    # Paso 1: Visitar kick.com para obtener cookies CF
    print("  [1] Obteniendo sesión CF en kick.com...")
    r1 = session.get(
        f"https://kick.com/{CHANNEL}",
        headers={
            "User-Agent": UA,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "sec-fetch-dest": "document",
            "sec-fetch-mode": "navigate",
            "sec-fetch-site": "none",
            "Upgrade-Insecure-Requests": "1",
        },
        timeout=20,
    )
    cf_cookies = dict(session.cookies)
    print(f"  CF cookies: {list(cf_cookies.keys())}")
    print(f"  Status: {r1.status_code}")

    # Paso 2: Intentar token con cookies de la sesión
    print("\n  [2] Intentando /viewer/v1/token con sesión CF...")
    token = try_token(session, "Sesión CF + X-CLIENT-TOKEN")

    if not token:
        # Paso 3: Intentar con diferentes variaciones de impersonación
        for browser in ["chrome131", "chrome124", "chrome120", "chrome116", "chrome110", "edge101", "safari17_2_ios", "safari18_0"]:
            print(f"\n  [3] Probando impersonate={browser}...")
            try:
                s2 = cffi_requests.Session(impersonate=browser)
                # Primero visitar kick.com
                s2.get(f"https://kick.com/{CHANNEL}", headers={
                    "User-Agent": UA, "Accept": "text/html,*/*",
                    "sec-fetch-dest": "document", "sec-fetch-mode": "navigate"
                }, timeout=15)
                time.sleep(0.5)
                token = try_token(s2, f"impersonate={browser}")
                if token:
                    break
            except Exception as e:
                print(f"  ERR: {e}")

    if not token:
        # Paso 4: Intentar con X-REQUEST-ID (fingerprint)
        # FingerprintJS genera un visitorId que se usa como X-REQUEST-ID
        print("\n  [4] Intentando con X-REQUEST-ID (fingerprint falso)...")
        fake_fp = uuid.uuid4().hex[:20]
        token = try_token(session, "Con X-REQUEST-ID", {"X-REQUEST-ID": fake_fp})

    if not token:
        # Paso 5: Intentar sin X-CLIENT-TOKEN (por si CF lo rechaza por header raro)
        print("\n  [5] Sin X-CLIENT-TOKEN (por si CF lo rechaza)...")
        s3 = cffi_requests.Session(impersonate="chrome131")
        s3.get(f"https://kick.com/{CHANNEL}", headers={"User-Agent": UA, "Accept": "text/html,*/*"}, timeout=15)
        time.sleep(1)
        headers_minimal = {
            "User-Agent":         UA,
            "Accept":             "application/json",
            "Origin":             "https://kick.com",
            "Referer":            f"https://kick.com/{CHANNEL}",
            "sec-fetch-site":     "same-site",
            "sec-fetch-mode":     "cors",
            "X-CLIENT-TOKEN":     CLIENT_TOKEN,
        }
        r = s3.get("https://websockets.kick.com/viewer/v1/token", headers=headers_minimal, timeout=15)
        print(f"  [{r.status_code}] Minimal headers")
        if r.status_code == 200:
            token = r.json().get("data", {}).get("token")
            print(f"  🎯 TOKEN: {token[:60]}...")
        else:
            print(f"  Body: {r.text[:200]}")

    if not token:
        # Paso 6: Intentar desde kick.com (same-origin) en vez de websockets.kick.com
        print("\n  [6] Probando desde kick.com (proxy reverso?)...")
        for path in ["/api/viewer/v1/token", "/viewer/v1/token", "/api/v1/viewer/token"]:
            try:
                r = session.get(
                    f"https://kick.com{path}",
                    headers={
                        "User-Agent": UA, "Accept": "application/json",
                        "X-CLIENT-TOKEN": CLIENT_TOKEN,
                        "sec-fetch-site": "same-origin",
                        "sec-fetch-mode": "cors",
                    },
                    timeout=10,
                )
                print(f"  [{r.status_code}] kick.com{path}")
                if r.status_code == 200:
                    print(f"  Body: {r.text[:300]}")
                    break
            except Exception as e:
                print(f"  ERR: {e}")

    # ── Resultado ────────────────────────────────────────────────────
    print("\n" + "="*58)
    if token:
        print(f"  ✅ VIEWER TOKEN OBTENIDO: {token[:80]}...")
        print(f"  WSS URL: wss://websockets.kick.com/viewer/v1/connect?token={token[:40]}...")
        
        # Guardar para uso del bot
        with open("viewer_token.json", "w") as f:
            json.dump({"token": token, "wss_url": f"wss://websockets.kick.com/viewer/v1/connect?token={token}"}, f, indent=2)
        print("  💾 Guardado en viewer_token.json")
    else:
        print("  ❌ No se pudo obtener el token directamente")
        print("  → El endpoint está protegido por CF Bot Management (no solo TLS)")
        print("  → Se necesita resolver el JS challenge de CF Turnstile")
        print("  → O usar el browser (Playwright) para interceptar el token")
    print("="*58)


if __name__ == "__main__":
    main()
