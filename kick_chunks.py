"""kick_chunks.py — Descarga y analiza chunks con lógica viewer"""
import re
from curl_cffi import requests as cffi_requests

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"

urls = [
    "https://kick.com/_next/static/chunks/app/%5Blocale%5D/(base)/layout-7d57115784d4f674.js",
    "https://kick.com/_next/static/chunks/854-505c73ea839639ba.js",
    "https://kick.com/_next/static/chunks/7293-ecf4c756bc7f0aec.js",
    "https://kick.com/_next/static/chunks/9430-bc1282ce14d83635.js",
]

for url in urls:
    r = cffi_requests.get(
        url,
        headers={"User-Agent": UA, "Accept": "*/*", "Referer": "https://kick.com/jhonramirez22"},
        timeout=25, impersonate="chrome131"
    )
    fname = url.split("/")[-1].replace("%5B","[").replace("%5D","]")
    print(f"\n{'='*60}")
    print(f"  {fname}  [{r.status_code}] ({len(r.text)} chars)")
    print("="*60)
    if r.status_code != 200:
        continue
    c = r.text

    for label, patterns in [
        ("VIEWER TOKEN ENDPOINT", [
            r".{0,400}viewer.{0,5}v1.{0,5}token.{0,400}",
        ]),
        ("VIEWER WS CONNECT", [
            r".{0,300}viewer.{0,5}v1.{0,5}connect.{0,300}",
        ]),
        ("WEBSOCKETS URL", [
            r".{0,100}websockets\.kick\.com.{0,200}",
        ]),
        ("X-DEVICE/SESSION ID HEADERS", [
            r".{0,150}[Xx]-[Dd]evice.{0,200}",
            r".{0,150}[Xx]-[Ss]ession.{0,200}",
        ]),
        ("CLIENT_ID / OAUTH", [
            r"client.?[Ii][dD].{0,150}",
            r"oauth.{0,150}",
        ]),
        ("PUSHER CONFIG", [
            r"pusher.{0,200}",
            r"eb1d5f283081a78b932c",
        ]),
        ("CHANNEL HANDSHAKE", [
            r".{0,100}channel.handshake.{0,200}",
        ]),
    ]:
        matches = []
        for pat in patterns:
            for m in re.finditer(pat, c, re.IGNORECASE):
                text = m.group(0)[:350].replace("\n"," ")
                if text not in matches:
                    matches.append(text)
                if len(matches) >= 3:
                    break
            if len(matches) >= 3:
                break
        if matches:
            print(f"\n  >> {label}:")
            for mx in matches[:3]:
                print(f"     {mx[:350]}")
