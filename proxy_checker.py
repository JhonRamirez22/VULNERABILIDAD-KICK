#!/usr/bin/env python3
"""
Proxy Checker — valida y cachea proxies vivos en Redis
Corre constantemente en background verificando salud de proxies
"""

import requests
import time
import random
import logging
from datetime import datetime
import json

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger("ProxyChecker")

PROXY_FILE = "upstreams.txt"
TEST_URL = "https://httpbin.org/ip"  # URL ligera para test
CHECK_INTERVAL = 300  # Validar proxies cada 5 minutos
TIMEOUT = 10

def load_proxies():
    """Cargar proxies del archivo"""
    try:
        with open(PROXY_FILE, 'r') as f:
            proxies = [line.strip() for line in f if line.strip()]
            return [f"socks5://{p}" if not p.startswith('socks') else p for p in proxies]
    except:
        return []

def check_proxy(proxy):
    """Verificar si un proxy está vivo"""
    try:
        resp = requests.get(TEST_URL, proxies={"http": proxy, "https": proxy}, timeout=TIMEOUT)
        return resp.status_code == 200
    except:
        return False

def validate_proxies_batch():
    """Validar todos los proxies y eliminar los muertos"""
    proxies = load_proxies()
    logger.info(f"🔍 Validando {len(proxies)} proxies...")
    
    alive = []
    for i, proxy in enumerate(proxies):
        if check_proxy(proxy):
            alive.append(proxy)
            logger.info(f"✅ [{i+1}/{len(proxies)}] {proxy[:30]}... OK")
        else:
            logger.warning(f"❌ [{i+1}/{len(proxies)}] {proxy[:30]}... DEAD")
        
        # Pequeño delay para no saturar
        time.sleep(0.1)
    
    # Guardar solo los vivos
    with open(PROXY_FILE + ".alive", 'w') as f:
        for proxy in alive:
            f.write(proxy + "\n")
    
    logger.info(f"💾 Guardados {len(alive)}/{len(proxies)} proxies vivos en {PROXY_FILE}.alive")
    return alive

def main():
    logger.info("🚀 Proxy Checker iniciado")
    
    while True:
        try:
            validate_proxies_batch()
            logger.info(f"⏳ Próxima validación en {CHECK_INTERVAL} segundos...")
            time.sleep(CHECK_INTERVAL)
        except Exception as e:
            logger.error(f"❌ Error: {str(e)}")
            time.sleep(60)

if __name__ == "__main__":
    main()
