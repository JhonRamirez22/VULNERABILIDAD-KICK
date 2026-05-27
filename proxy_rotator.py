#!/usr/bin/env python3
"""
Proxy Residencial Escalable — SOCKS5 + HTTP
════════════════════════════════════════════════════════════════
Modos de salida (se pueden combinar):
  1. Upstream pool   — encadena a través de proxies externos reales
                       cargados desde --upstream-file o --upstream
  2. Multi-NIC       — enlaza cada conexión saliente a una IP local
                       distinta (--local-ips 1.2.3.4,5.6.7.8)
  3. Directo         — sin upstream ni NIC extra (comportamiento original)

Estrategias de rotación: round-robin (default), random, sticky
Health-checker automático cada N segundos.
Estadísticas en vivo con --stats-port.
════════════════════════════════════════════════════════════════
Uso rápido:
  python proxy_server.py --no-auth
  python proxy_server.py --upstream-file upstreams.txt --rotation random
  python proxy_server.py --local-ips 203.0.113.1,203.0.113.2 --user a --password b
"""

import asyncio
import argparse
import base64
import hashlib
import itertools
import json
import logging
import random
import socket
import struct
import sys
import time
from asyncio import StreamReader, StreamWriter
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

# ─────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("proxy")

# ─────────────────────────────────────────────
#  Constantes SOCKS5
# ─────────────────────────────────────────────
SOCKS5_VERSION = 0x05
NO_AUTH        = 0x00
USER_PASS_AUTH = 0x02
AUTH_NONE      = 0xFF
CMD_CONNECT    = 0x01
ATYP_IPV4      = 0x01
ATYP_DOMAIN    = 0x03
ATYP_IPV6      = 0x04

# ─────────────────────────────────────────────
#  Pool de upstreams
# ─────────────────────────────────────────────

@dataclass
class UpstreamProxy:
    scheme: str            # socks5 | http
    host: str
    port: int
    user: Optional[str]   = None
    password: Optional[str] = None
    alive: bool            = True
    failures: int          = 0
    requests: int          = 0
    latency_ms: float      = 0.0

    def __str__(self):
        auth = f"{self.user}:***@" if self.user else ""
        return f"{self.scheme}://{auth}{self.host}:{self.port}"


def parse_upstream(raw: str) -> UpstreamProxy:
    raw = raw.strip()
    if not raw or raw.startswith("#"):
        raise ValueError("Vacío o comentario")
    if "://" not in raw:
        raw = "socks5://" + raw
    p = urlparse(raw)
    scheme = p.scheme.lower()
    if scheme not in ("socks5", "http", "https"):
        raise ValueError(f"Esquema no soportado: {scheme}")
    return UpstreamProxy(
        scheme=scheme,
        host=p.hostname,
        port=p.port or (1080 if scheme == "socks5" else 8080),
        user=p.username or None,
        password=p.password or None,
    )


class ProxyPool:
    """Pool rotativo de upstreams con health-check y estadísticas."""

    def __init__(self, proxies: list, rotation: str = "round-robin"):
        self._all      = proxies
        self._rotation = rotation
        self._cycle    = itertools.cycle(range(len(proxies))) if proxies else iter([])
        self._sticky: dict = {}
        self.stats: dict   = defaultdict(lambda: {"ok": 0, "fail": 0, "ms": 0.0})

    def alive(self):
        return [p for p in self._all if p.alive]

    def pick(self, sticky_key=None):
        pool = self.alive()
        if not pool:
            return None
        if self._rotation == "sticky" and sticky_key:
            if sticky_key not in self._sticky or not self._sticky[sticky_key].alive:
                self._sticky[sticky_key] = random.choice(pool)
            return self._sticky[sticky_key]
        if self._rotation == "random":
            return random.choice(pool)
        # round-robin
        for _ in range(len(self._all)):
            idx = next(self._cycle)
            if self._all[idx].alive:
                return self._all[idx]
        return None

    def record_ok(self, proxy, ms: float):
        proxy.requests += 1
        proxy.latency_ms = ms
        k = str(proxy)
        self.stats[k]["ok"] += 1
        self.stats[k]["ms"] = round(ms, 1)

    def record_fail(self, proxy):
        proxy.failures += 1
        proxy.requests += 1
        self.stats[str(proxy)]["fail"] += 1
        if proxy.failures >= 3:
            proxy.alive = False
            log.warning("⛔  Upstream muerto: %s", proxy)

    async def health_check_loop(self, interval: int = 60):
        while True:
            await asyncio.sleep(interval)
            for proxy in self._all:
                ok = await self._ping(proxy)
                if ok and not proxy.alive:
                    proxy.alive   = True
                    proxy.failures = 0
                    log.info("✅  Upstream recuperado: %s", proxy)
                elif not ok and proxy.alive:
                    proxy.failures += 1
                    if proxy.failures >= 3:
                        proxy.alive = False
                        log.warning("⛔  Upstream caído: %s", proxy)

    async def _ping(self, proxy, timeout: float = 5.0) -> bool:
        try:
            t0 = time.perf_counter()
            r, w = await asyncio.wait_for(
                asyncio.open_connection(proxy.host, proxy.port), timeout=timeout
            )
            w.close()
            proxy.latency_ms = round((time.perf_counter() - t0) * 1000, 1)
            return True
        except Exception:
            return False

    def summary(self):
        return [
            {
                "upstream":   str(p),
                "alive":      p.alive,
                "requests":   p.requests,
                "failures":   p.failures,
                "latency_ms": p.latency_ms,
            }
            for p in self._all
        ]


# ─────────────────────────────────────────────
#  Pool de IPs locales (Multi-NIC)
# ─────────────────────────────────────────────

class LocalIPPool:
    def __init__(self, ips: list, rotation: str = "round-robin"):
        self._ips      = ips
        self._rotation = rotation
        self._cycle    = itertools.cycle(ips) if ips else iter([])

    def pick(self, sticky_key=None):
        if not self._ips:
            return None
        if self._rotation == "random":
            return random.choice(self._ips)
        if self._rotation == "sticky" and sticky_key:
            idx = int(hashlib.md5(sticky_key.encode()).hexdigest(), 16) % len(self._ips)
            return self._ips[idx]
        return next(self._cycle)

    def __bool__(self):
        return bool(self._ips)


# ─────────────────────────────────────────────
#  Apertura de conexiones salientes
# ─────────────────────────────────────────────

async def _via_socks5(proxy: UpstreamProxy, host: str, port: int, timeout: float):
    r, w = await asyncio.wait_for(
        asyncio.open_connection(proxy.host, proxy.port), timeout=timeout
    )
    if proxy.user:
        w.write(bytes([SOCKS5_VERSION, 2, NO_AUTH, USER_PASS_AUTH]))
    else:
        w.write(bytes([SOCKS5_VERSION, 1, NO_AUTH]))
    await w.drain()
    resp = await asyncio.wait_for(r.read(2), timeout=timeout)
    if resp[1] == USER_PASS_AUTH:
        ub = proxy.user.encode()
        pb = proxy.password.encode()
        w.write(bytes([1, len(ub)]) + ub + bytes([len(pb)]) + pb)
        await w.drain()
        ar = await asyncio.wait_for(r.read(2), timeout=timeout)
        if ar[1] != 0:
            raise ConnectionError("Auth SOCKS5 rechazada por upstream")
    dst = host.encode()
    w.write(bytes([SOCKS5_VERSION, CMD_CONNECT, 0, ATYP_DOMAIN, len(dst)])
            + dst + struct.pack("!H", port))
    await w.drain()
    cr = await asyncio.wait_for(r.read(10), timeout=timeout)
    if cr[1] != 0:
        raise ConnectionError(f"SOCKS5 upstream rechazó CONNECT: código {cr[1]}")
    return r, w


async def _via_http_connect(proxy: UpstreamProxy, host: str, port: int, timeout: float):
    r, w = await asyncio.wait_for(
        asyncio.open_connection(proxy.host, proxy.port), timeout=timeout
    )
    req = f"CONNECT {host}:{port} HTTP/1.1\r\nHost: {host}:{port}\r\n"
    if proxy.user:
        cred = base64.b64encode(f"{proxy.user}:{proxy.password}".encode()).decode()
        req += f"Proxy-Authorization: Basic {cred}\r\n"
    req += "\r\n"
    w.write(req.encode())
    await w.drain()
    resp = b""
    while b"\r\n\r\n" not in resp:
        chunk = await asyncio.wait_for(r.read(4096), timeout=timeout)
        if not chunk:
            break
        resp += chunk
    if b"200" not in resp.split(b"\r\n")[0]:
        raise ConnectionError(f"HTTP CONNECT rechazado: {resp[:80]}")
    return r, w


async def open_connection_via(host, port, pool, nic_pool, sticky_key=None, timeout=15.0):
    """
    Devuelve (reader, writer, upstream|None).
    Orden: upstream pool → NIC local → directo.
    """
    if pool:
        proxy = pool.pick(sticky_key)
        if proxy:
            t0 = time.perf_counter()
            try:
                if proxy.scheme == "socks5":
                    r, w = await _via_socks5(proxy, host, port, timeout)
                else:
                    r, w = await _via_http_connect(proxy, host, port, timeout)
                pool.record_ok(proxy, (time.perf_counter() - t0) * 1000)
                return r, w, proxy
            except Exception as e:
                pool.record_fail(proxy)
                log.warning("Upstream %s falló (%s), reintentando…", proxy, e)

    if nic_pool:
        local_ip = nic_pool.pick(sticky_key)
        if local_ip:
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.bind((local_ip, 0))
                sock.setblocking(False)
                await asyncio.wait_for(
                    asyncio.get_event_loop().sock_connect(sock, (host, port)),
                    timeout=timeout,
                )
                r, w = await asyncio.open_connection(sock=sock)
                log.debug("Salida via NIC %s → %s:%d", local_ip, host, port)
                return r, w, None
            except Exception as e:
                sock.close()
                log.warning("NIC %s falló (%s), usando directo…", local_ip, e)

    r, w = await asyncio.wait_for(asyncio.open_connection(host, port), timeout=timeout)
    return r, w, None


# ─────────────────────────────────────────────
#  SOCKS5 handler entrante
# ─────────────────────────────────────────────

async def socks5_handshake(reader, writer, username, password) -> bool:
    data = await reader.read(257)
    if not data or data[0] != SOCKS5_VERSION:
        return False
    methods = data[2: 2 + data[1]]
    use_auth = username is not None
    if use_auth and USER_PASS_AUTH in methods:
        writer.write(bytes([SOCKS5_VERSION, USER_PASS_AUTH]))
        await writer.drain()
        auth = await reader.read(513)
        ulen = auth[1]
        uname = auth[2: 2 + ulen].decode()
        plen = auth[2 + ulen]
        passwd = auth[3 + ulen: 3 + ulen + plen].decode()
        if uname == username and passwd == password:
            writer.write(b"\x01\x00")
        else:
            writer.write(b"\x01\x01")
            await writer.drain()
            log.warning("SOCKS5 auth fallida: '%s'", uname)
            return False
        await writer.drain()
    elif NO_AUTH in methods and not use_auth:
        writer.write(bytes([SOCKS5_VERSION, NO_AUTH]))
        await writer.drain()
    else:
        writer.write(bytes([SOCKS5_VERSION, AUTH_NONE]))
        await writer.drain()
        return False
    return True


async def socks5_parse_request(reader):
    header = await reader.read(4)
    if len(header) < 4 or header[0] != SOCKS5_VERSION or header[1] != CMD_CONNECT:
        return None
    atyp = header[3]
    if atyp == ATYP_IPV4:
        raw = await reader.read(6)
        host = socket.inet_ntoa(raw[:4])
        port = struct.unpack("!H", raw[4:])[0]
    elif atyp == ATYP_DOMAIN:
        length = (await reader.read(1))[0]
        raw = await reader.read(length + 2)
        host = raw[:length].decode()
        port = struct.unpack("!H", raw[length:])[0]
    elif atyp == ATYP_IPV6:
        raw = await reader.read(18)
        host = socket.inet_ntop(socket.AF_INET6, raw[:16])
        port = struct.unpack("!H", raw[16:])[0]
    else:
        return None
    return host, port


async def handle_socks5(reader, writer, username, password, pool, nic_pool, rotation):
    peer = writer.get_extra_info("peername")
    sk = hashlib.md5(str(peer[0]).encode()).hexdigest() if rotation == "sticky" else None
    try:
        if not await socks5_handshake(reader, writer, username, password):
            return
        result = await socks5_parse_request(reader)
        if result is None:
            writer.write(b"\x05\x07\x00\x01" + b"\x00" * 6)
            await writer.drain()
            return
        host, port = result
        try:
            rr, rw, up = await open_connection_via(host, port, pool, nic_pool, sk)
        except Exception as e:
            log.warning("No se pudo conectar %s:%d — %s", host, port, e)
            writer.write(b"\x05\x05\x00\x01" + b"\x00" * 6)
            await writer.drain()
            return
        log.info("SOCKS5 %s → %s:%d%s", peer, host, port, f" via {up}" if up else "")
        writer.write(b"\x05\x00\x00\x01" + b"\x00" * 6)
        await writer.drain()
        await asyncio.gather(pipe(reader, rw), pipe(rr, writer), return_exceptions=True)
    except Exception as e:
        log.debug("SOCKS5 error: %s", e)
    finally:
        writer.close()


# ─────────────────────────────────────────────
#  HTTP handler entrante
# ─────────────────────────────────────────────

async def handle_http(reader, writer, username, password, pool, nic_pool, rotation):
    peer = writer.get_extra_info("peername")
    sk = hashlib.md5(str(peer[0]).encode()).hexdigest() if rotation == "sticky" else None
    try:
        raw = await reader.read(8192)
        if not raw:
            return
        first_line = raw.split(b"\r\n")[0].decode(errors="replace")

        if username is not None:
            creds = None
            for line in raw.split(b"\r\n")[1:]:
                if line.lower().startswith(b"proxy-authorization:"):
                    creds = line.split(b":", 1)[1].strip()
                    break
            if creds is None:
                writer.write(
                    b"HTTP/1.1 407 Proxy Authentication Required\r\n"
                    b"Proxy-Authenticate: Basic realm=\"proxy\"\r\n"
                    b"Content-Length: 0\r\n\r\n"
                )
                await writer.drain()
                return
            try:
                _, encoded = creds.split(b" ", 1)
                user, pwd = base64.b64decode(encoded).decode().split(":", 1)
            except Exception:
                user, pwd = "", ""
            if user != username or pwd != password:
                writer.write(b"HTTP/1.1 407 Proxy Authentication Required\r\n\r\n")
                await writer.drain()
                log.warning("HTTP auth fallida: '%s'", user)
                return

        method, target, *_ = first_line.split()
        if method == "CONNECT":
            host, port_str = target.rsplit(":", 1)
            port = int(port_str)
            try:
                rr, rw, up = await open_connection_via(host, port, pool, nic_pool, sk)
            except Exception as e:
                log.warning("No se pudo conectar %s:%d — %s", host, port, e)
                writer.write(b"HTTP/1.1 502 Bad Gateway\r\n\r\n")
                await writer.drain()
                return
            log.info("HTTP CONNECT %s → %s:%d%s", peer, host, port, f" via {up}" if up else "")
            writer.write(b"HTTP/1.1 200 Connection Established\r\n\r\n")
            await writer.drain()
            await asyncio.gather(pipe(reader, rw), pipe(rr, writer), return_exceptions=True)
        else:
            parsed = urlparse(target)
            host = parsed.hostname
            port = parsed.port or 80
            try:
                rr, rw, up = await open_connection_via(host, port, pool, nic_pool, sk)
            except Exception as e:
                log.warning("No se pudo conectar %s:%d — %s", host, port, e)
                writer.write(b"HTTP/1.1 502 Bad Gateway\r\n\r\n")
                await writer.drain()
                return
            log.info("HTTP %s %s%s", method, target, f" via {up}" if up else "")
            rw.write(raw)
            await rw.drain()
            await asyncio.gather(pipe(reader, rw), pipe(rr, writer), return_exceptions=True)
    except Exception as e:
        log.debug("HTTP error: %s", e)
    finally:
        writer.close()


# ─────────────────────────────────────────────
#  Pipe bidireccional
# ─────────────────────────────────────────────

async def pipe(src, dst, chunk: int = 65536):
    try:
        while True:
            data = await src.read(chunk)
            if not data:
                break
            dst.write(data)
            await dst.drain()
    except Exception:
        pass
    finally:
        try:
            dst.close()
        except Exception:
            pass


# ─────────────────────────────────────────────
#  Servidor de estadísticas
# ─────────────────────────────────────────────

async def stats_server(pool, nic_pool, port: int):
    async def handle(reader, writer):
        await reader.read(4096)
        data = {
            "upstreams": pool.summary() if pool else [],
            "local_ips": nic_pool._ips if nic_pool else [],
        }
        body = json.dumps(data, indent=2).encode()
        writer.write(
            b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n"
            + b"Content-Length: " + str(len(body)).encode() + b"\r\n\r\n"
            + body
        )
        await writer.drain()
        writer.close()

    srv = await asyncio.start_server(handle, "127.0.0.1", port)
    log.info("📊  Stats → http://127.0.0.1:%d/", port)
    async with srv:
        await srv.serve_forever()


# ─────────────────────────────────────────────
#  Main
# ─────────────────────────────────────────────

async def main():
    parser = argparse.ArgumentParser(
        description="Proxy Residencial Escalable — SOCKS5 + HTTP con pool externo",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    # Servidor local
    parser.add_argument("--host",         default="0.0.0.0")
    parser.add_argument("--socks5-port",  type=int, default=1080)
    parser.add_argument("--http-port",    type=int, default=8080)
    parser.add_argument("--user",         default=None)
    parser.add_argument("--password",     default=None)
    parser.add_argument("--no-auth",      action="store_true")

    # Upstreams
    parser.add_argument(
        "--upstream", action="append", metavar="PROXY", dest="upstreams",
        help="ej: socks5://user:pass@1.2.3.4:1080  (repetible)",
    )
    parser.add_argument(
        "--upstream-file", metavar="FILE",
        help="Archivo con un upstream por línea (# = comentario)",
    )

    # Multi-NIC
    parser.add_argument(
        "--local-ips", metavar="IPS",
        help="IPs locales separadas por coma para rotar NICs",
    )

    # Rotación / health
    parser.add_argument(
        "--rotation", choices=["round-robin", "random", "sticky"],
        default="round-robin",
    )
    parser.add_argument("--health-interval", type=int, default=60)

    # Stats
    parser.add_argument("--stats-port", type=int, default=None,
                        help="Puerto para endpoint JSON de estadísticas")

    args = parser.parse_args()

    username = None if args.no_auth else args.user
    password = None if args.no_auth else args.password
    if username and not password:
        parser.error("--user requiere --password")

    # Cargar upstreams
    raw_list = list(args.upstreams or [])
    if args.upstream_file:
        fp = Path(args.upstream_file)
        if not fp.exists():
            parser.error(f"Archivo no encontrado: {fp}")
        for line in fp.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                raw_list.append(line)

    proxies = []
    for raw in raw_list:
        try:
            proxies.append(parse_upstream(raw))
        except Exception as e:
            log.warning("Upstream inválido '%s': %s", raw, e)

    pool     = ProxyPool(proxies, rotation=args.rotation) if proxies else None
    local_ips = [ip.strip() for ip in args.local_ips.split(",")] if args.local_ips else []
    nic_pool  = LocalIPPool(local_ips, rotation=args.rotation) if local_ips else None

    socks5_srv = await asyncio.start_server(
        lambda r, w: handle_socks5(r, w, username, password, pool, nic_pool, args.rotation),
        args.host, args.socks5_port,
    )
    http_srv = await asyncio.start_server(
        lambda r, w: handle_http(r, w, username, password, pool, nic_pool, args.rotation),
        args.host, args.http_port,
    )

    auth_info = f"{username}:****" if username else "sin autenticación"
    log.info("╔══════════════════════════════════════════════╗")
    log.info("║      Proxy Residencial Escalable             ║")
    log.info("╠══════════════════════════════════════════════╣")
    log.info("║  SOCKS5  → %s:%-5d                      ║", args.host, args.socks5_port)
    log.info("║  HTTP    → %s:%-5d                      ║", args.host, args.http_port)
    log.info("║  Auth    → %-32s ║", auth_info)
    log.info("║  Rot.    → %-32s ║", args.rotation)
    if pool:
        log.info("║  Upstreams → %-30d ║", len(pool._all))
    if nic_pool:
        log.info("║  NICs    → %-32s ║", ", ".join(local_ips))
    if not pool and not nic_pool:
        log.info("║  Modo    → directo (sin upstream/NIC)        ║")
    log.info("╚══════════════════════════════════════════════╝")

    tasks = [socks5_srv.serve_forever(), http_srv.serve_forever()]
    if pool:
        tasks.append(pool.health_check_loop(args.health_interval))
    if args.stats_port:
        tasks.append(stats_server(pool, nic_pool, args.stats_port))

    async with socks5_srv, http_srv:
        await asyncio.gather(*tasks)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log.info("Servidor detenido.")
        sys.exit(0)
