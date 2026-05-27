#!/usr/bin/env python3
"""
Token Server API v17.0 — FastAPI + asyncio (Fallback for Browserless Bot)
Compatible with kick-websocket.js v17.0 — chrome131 TLS Identity
Corre como demonio en http://127.0.0.1:8765
"""

import json
import uuid
import asyncio
import random
import logging
import re
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
import uvicorn
from curl_cffi import requests as cffi_requests
import time

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("TokenServer")

app = FastAPI(title="Kick Viewer Token Server v17.0", version="17.0")

CLIENT_TOKEN = "e1393935a959b4020a4491574f6490129f678acdaa92760471263db43487f823"
CHROME_131_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
TOKEN_CACHE = {}
PROXY_LIST = []
PROXY_INDEX = 0
DISCOVERY_COOKIES = ""

def load_proxies():
    global PROXY_LIST
    try:
        with open('upstreams.txt', 'r') as f:
            proxies = [line.strip() for line in f if line.strip()]
            PROXY_LIST = [f"socks5://{p}" if not p.startswith('socks') else p for p in proxies]
            logger.info(f"Cargados {len(PROXY_LIST)} proxies")
    except:
        logger.warning("No se pudo cargar proxies, usando directo")
        PROXY_LIST = []

def get_next_proxy():
    global PROXY_INDEX
    if not PROXY_LIST:
        return None
    prx = PROXY_LIST[PROXY_INDEX % len(PROXY_LIST)]
    PROXY_INDEX += 1
    return prx

async def fetch_token(channel_name: str, cookies: str = "", retries: int = 3) -> dict:
    """
    Obtener token con identidad chrome131 consistente.
    Soporta inyeccion de cookies del descubrimiento estatico.
    """
    cookie_dict = {}
    if cookies:
        for item in cookies.split('; '):
            if '=' in item:
                k, v = item.split('=', 1)
                cookie_dict[k.strip()] = v.strip()

    for attempt in range(retries):
        try:
            prx = get_next_proxy()
            proxy_dict = {"http": prx, "https": prx} if prx else None

            session = cffi_requests.Session(impersonate="chrome131", proxies=proxy_dict)

            if cookie_dict:
                for k, v in cookie_dict.items():
                    session.cookies.set(k, v)

            session.get(f"https://kick.com/{channel_name}", headers={
                "User-Agent": CHROME_131_UA,
                "Accept": "text/html,*/*",
            }, timeout=15)

            timeout = 15 + (attempt * 5)
            res = session.get(
                "https://websockets.kick.com/viewer/v1/token",
                headers={
                    "User-Agent": CHROME_131_UA,
                    "Accept": "application/json, text/plain, */*",
                    "Origin": "https://kick.com",
                    "Referer": f"https://kick.com/{channel_name}",
                    "X-CLIENT-TOKEN": CLIENT_TOKEN,
                    "X-Device-ID": str(uuid.uuid4()),
                    "X-Session-ID": str(uuid.uuid4()),
                },
                timeout=timeout
            )

            if res.status_code == 200:
                token = res.json().get("data", {}).get("token", "")
                if token and len(token) > 20:
                    cookie_str = "; ".join([f"{k}={v}" for k, v in session.cookies.get_dict().items()])
                    return {"token": token, "cookie": cookie_str, "ua": CHROME_131_UA}
        except Exception as e:
            logger.warning(f"Intento {attempt + 1}/{retries} fallo: {str(e)[:50]}")
            await asyncio.sleep(1 + (attempt * 0.5))

    return None


async def discover_channel_static(channel_name: str) -> dict:
    """Descubrimiento estatico via curl_cffi — extrae window.channel del HTML."""
    try:
        res = cffi_requests.get(f"https://kick.com/{channel_name}",
            impersonate="chrome131",
            headers={"User-Agent": CHROME_131_UA, "Accept": "text/html,*/*"},
            timeout=20
        )
        if res.status_code != 200:
            return {"error": f"HTTP {res.status_code}"}

        html = res.text
        channel_match = re.search(r'window\.channel\s*=\s*({.*?});', html, re.DOTALL)

        if not channel_match:
            next_data_match = re.search(r'<script[^>]*id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.DOTALL)
            if next_data_match:
                try:
                    next_data = json.loads(next_data_match.group(1))
                    props = next_data.get("props", {}).get("pageProps", {})
                    channel_data = props.get("channel", props.get("livestream", {}))
                    if channel_data:
                        ls = channel_data.get("livestream", channel_data)
                        return {
                            "id": channel_data.get("id"),
                            "chatroom_id": channel_data.get("chatroom", {}).get("id"),
                            "live": ls is not None,
                            "viewers": ls.get("viewers", 0) if ls else 0,
                            "title": ls.get("session_title", "Unknown") if ls else "Unknown",
                            "cookies": "; ".join([f"{k}={v}" for k, v in res.cookies.get_dict().items()]),
                            "ua": CHROME_131_UA,
                        }
                except:
                    pass
            return {"error": "window.channel not found"}

        channel = json.loads(channel_match.group(1))
        ls = channel.get("livestream") or {}
        chatroom = channel.get("chatroom") or {}
        return {
            "id": channel.get("id"),
            "chatroom_id": chatroom.get("id") or channel.get("chatroom_id"),
            "live": channel.get("livestream") is not None,
            "viewers": ls.get("viewers", 0) if ls else 0,
            "title": ls.get("session_title", "Unknown") if ls else "Unknown",
            "cookies": "; ".join([f"{k}={v}" for k, v in res.cookies.get_dict().items()]),
            "ua": CHROME_131_UA,
        }
    except Exception as e:
        return {"error": str(e)}


@app.get("/token")
async def get_token(channel: str, cookies: str = ""):
    """Endpoint para obtener un token de viewer."""
    token_data = await fetch_token(channel, cookies)
    if token_data:
        return {"token": token_data, "status": "ok"}
    return JSONResponse(status_code=503, content={"error": "No token obtained"})

@app.get("/batch-tokens")
async def batch_tokens(channel: str, count: int = 10, cookies: str = ""):
    """Obtener multiples tokens en paralelo usando asyncio."""
    if count > 100:
        count = 100

    tasks = [fetch_token(channel, cookies) for _ in range(count)]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    valid_tokens = [r for r in results if isinstance(r, dict) and r.get("token")]
    logger.info(f"Batch: {len(valid_tokens)}/{count} tokens exitosos")

    return {"tokens": valid_tokens, "count": len(valid_tokens)}

@app.get("/discover")
async def discover(channel: str):
    """Endpoint para descubrimiento estatico de canal."""
    result = await discover_channel_static(channel)
    if result.get("error"):
        return JSONResponse(status_code=404, content=result)
    return result

@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "alive", "proxies": len(PROXY_LIST), "version": "17.0"}

@app.on_event("startup")
async def startup():
    load_proxies()
    logger.info("Token Server v17.0 iniciado en http://127.0.0.1:8765")

if __name__ == "__main__":
    load_proxies()
    uvicorn.run(app, host="127.0.0.1", port=8765, log_level="warning", workers=1)
