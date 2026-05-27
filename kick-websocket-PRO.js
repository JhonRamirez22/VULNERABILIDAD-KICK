/**
 * KICK VIEWER BOT PRO v18.0 (IPC Daemon Architecture)
 * - M3U8 HLS simulado vía Persistent Python Daemon (0 Spawns = 0 CPU Lags)
 * - Node.js Event Loop Fully Async + ThreadPool en Python
 * - Anti-DDoS Sockets: Exponential Backoff Retry (Control de reconnects masivos)
 */

'use strict';

const WebSocket = require('ws');
const { spawn } = require('child_process');
const path = require('path');
const fs = require('fs');
const readline = require('readline');
const { SocksProxyAgent } = require('socks-proxy-agent');

const CLIENT_TOKEN = 'e1393935a959b4020a4491574f6490129f678acdaa92760471263db43487f823';
const WS_CONNECT = 'wss://websockets.kick.com/viewer/v1/connect';
const PUSHER_KEY = '32cbd69e4b950bf97679';
const PUSHER_WS  = `wss://ws-us2.pusher.com/app/${PUSHER_KEY}?protocol=7&client=js&version=8.4.0&flash=false`;

const PROXY_URL = 'socks5://127.0.0.1:1080';
const proxyAgent = new SocksProxyAgent(PROXY_URL);

const USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36'
];

function rand(min, max) { return Math.floor(Math.random() * (max - min + 1)) + min; }
function rndUA() { return USER_AGENTS[rand(0, USER_AGENTS.length - 1)]; }
function pad(s, n) { return String(s).padEnd(n); }
function isValidToken(t) { return typeof t === 'string' && t.trim().length > 20; }

// --- IPC DAEMON CONFIG ---
const DAEMON_PATH = path.join(require('os').tmpdir(), `_kv_daemon_${process.pid}.py`);
const PYTHON_DAEMON_CODE = `
import sys, json, uuid, time, random, os
from concurrent.futures import ThreadPoolExecutor
from curl_cffi import requests as cffi_requests
import threading

CLIENT_TOKEN = "${CLIENT_TOKEN}"
executor = ThreadPoolExecutor(max_workers=300)
out_lock = threading.Lock()

def handle_action(msg_id, action, payload):
    res = {}
    try:
        proxy = payload.get("proxy")
        proxies = {"http": proxy, "https": proxy} if proxy else None
        ua = payload.get("ua", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131.0.0.0")

        if action == "channel_info":
            stream = payload.get("streamName")
            r = cffi_requests.get(f"https://kick.com/api/v1/channels/{stream}",
                headers={"User-Agent": ua}, proxies=proxies, impersonate="chrome131", timeout=15)
            if r.status_code == 200:
                d = r.json()
                res = {
                    "id": d.get("id"),
                    "chatroom_id": (d.get("chatroom") or {}).get("id"),
                    "live": d.get("livestream") is not None,
                    "playback_url": d.get("playback_url", "")
                }
            else: res = {"error": f"HTTP {r.status_code}"}

        elif action == "tokens":
            count = payload.get("count", 20)
            stream = payload.get("streamName")
            s = cffi_requests.Session(impersonate="chrome131", proxies=proxies)
            s.get(f"https://kick.com/{stream}", headers={"User-Agent": ua}, timeout=15)
            
            tokens = []
            for _ in range(count):
                try:
                    tk_res = s.get("https://websockets.kick.com/viewer/v1/token",
                        headers={"User-Agent": ua, "Origin": "https://kick.com", "X-CLIENT-TOKEN": CLIENT_TOKEN, "X-Device-ID": str(uuid.uuid4()), "X-Session-ID": str(uuid.uuid4())}, timeout=10)
                    if tk_res.status_code == 200:
                        t = tk_res.json().get("data", {}).get("token", "")
                        if t: tokens.append(t)
                except: pass
                time.sleep(0.2)
            res = {"tokens": tokens}

        elif action == "hls":
            url = payload.get("url")
            cffi_requests.get(url, headers={"User-Agent": ua, "Referer": "https://kick.com/"}, proxies=proxies, impersonate="chrome131", timeout=15)
            res = {"status": "ok"}
            
        else: res = {"error": "Invalid action"}
    except Exception as e:
        res = {"error": str(e)}

    # Escribir respuesta atómicamente
    output = json.dumps({"id": msg_id, "result": res}) + "\\n"
    with out_lock:
        try:
            sys.stdout.write(output)
            sys.stdout.flush()
        except: pass

for line in sys.stdin:
    line = line.strip()
    if not line: continue
    try:
        data = json.loads(line)
        executor.submit(handle_action, data["id"], data["action"], data.get("payload", {}))
    except Exception as e:
        pass

os._exit(0) # Forzar matar hilos zombis al cerrarse Node.js
`;

class PythonDaemon {
    constructor() {
        fs.writeFileSync(DAEMON_PATH, PYTHON_DAEMON_CODE, 'utf8');
        this.proc = spawn('python3', [DAEMON_PATH]);
        this.callbacks = new Map();
        this.msgId = 0;

        const rl = readline.createInterface({ input: this.proc.stdout });
        rl.on('line', (line) => {
            try {
                const data = JSON.parse(line);
                if (this.callbacks.has(data.id)) {
                    this.callbacks.get(data.id)(data.result);
                    this.callbacks.delete(data.id);
                }
            } catch(e) {}
        });
        
        this.proc.stderr.on('data', d => console.error('[PYTHON_LOG]', d.toString()));
    }

    request(action, payload = {}) {
        return new Promise((resolve) => {
            const id = ++this.msgId;
            this.callbacks.set(id, resolve);
            this.proc.stdin.write(JSON.stringify({ id, action, payload }) + '\n');
        });
    }

    close() {
        this.proc.kill();
        try { fs.unlinkSync(DAEMON_PATH); } catch (_) {}
    }
}

class KickViewerBotPro {
    constructor(streamUrl, viewerCount) {
        this.streamUrl = streamUrl;
        this.viewerCount = viewerCount;
        this.streamName = streamUrl.replace(/\/$/, '').split('/').pop();
        this.channelId = null;
        this.chatroomId = null;
        this.playbackUrl = null;
        this.startTime = Date.now();
        this.tokenPool = [];
        this.daemon = new PythonDaemon();
        this.state = {
            connected: 0, pusher: 0, reconnects: 0, refreshes: 0, hlsDownloads: 0
        };
    }

    formatUptime() {
        const s = Math.floor((Date.now() - this.startTime) / 1000);
        return `${String(Math.floor(s/3600)).padStart(2,'0')}:${String(Math.floor((s%3600)/60)).padStart(2,'0')}:${String(s%60).padStart(2,'0')}`;
    }
    memUsage() { return `${(process.memoryUsage().rss/1024/1024).toFixed(1)} MB`; }

    async getChannelInfo() {
        const res = await this.daemon.request('channel_info', { streamName: this.streamName, proxy: PROXY_URL, ua: rndUA() });
        if (res.error) return false;
        this.channelId = String(res.id);
        this.chatroomId = String(res.chatroom_id || '');
        this.playbackUrl = res.playback_url || null;
        return true;
    }

    async getViewerTokens(totalCount) {
        let allTokens = [];
        const BATCH_SIZE = 25; 
        const threads = Math.ceil(totalCount / BATCH_SIZE);
        let promises = [];
        
        for (let i=0; i<threads; i++) {
            promises.push(this.daemon.request('tokens', { count: BATCH_SIZE, streamName: this.streamName, proxy: PROXY_URL, ua: rndUA() }));
            if (promises.length >= 20 || i === threads - 1) {
                const results = await Promise.all(promises);
                results.forEach(r => { if (r.tokens) allTokens.push(...r.tokens); });
                promises = [];
            }
        }
        return allTokens.filter(isValidToken);
    }

    async simulateHLSDownload(ua) {
        if (!this.playbackUrl) return;
        // IPC Async request, no congela Node.js ni spawnea procesos
        const res = await this.daemon.request('hls', { url: this.playbackUrl, ua, proxy: PROXY_URL });
        if (res.status === 'ok') this.state.hlsDownloads++;
    }

    connectViewer(token) {
        const ua = rndUA();

        let wsAttempts = 0;
        const connectWS = (tkn) => {
            if (!isValidToken(tkn)) return;
            wsAttempts++;

            const ws = new WebSocket(`${WS_CONNECT}?token=${tkn}`, {
                headers: { 'User-Agent': ua, 'Origin': 'https://kick.com' },
                agent: proxyAgent, rejectUnauthorized: false
            });

            ws.on('open', () => {
                wsAttempts = 0; // Reset backoff en connect exitoso
                this.state.connected++;
                ws.send(JSON.stringify({ type: 'channel_handshake', data: { message: { channelId: this.channelId } } }));
                
                ws.hlsInt = setInterval(() => { this.simulateHLSDownload(ua); }, 15000);
                ws.pingInt = setInterval(() => { if (ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify({ type: 'ping' })); }, 25000);
            });
            
            ws.on('message', (d) => {
                try {
                    const msg = JSON.parse(d.toString());
                    if (msg.event === 'ping' || msg.type === 'ping') {
                        if (ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify({ type: 'pong' }));
                    }
                } catch (_) {}
            });

            ws.on('close', () => {
                this.state.connected = Math.max(0, this.state.connected - 1);
                clearInterval(ws.pingInt); clearInterval(ws.hlsInt);
                this.state.reconnects++;
                
                // EXPONENTIAL BACKOFF RECONNECT (Evita bombardeo cuando proxy cae)
                const delay = Math.min(60000, (1000 * Math.pow(1.5, wsAttempts)) + rand(500, 2000));
                
                setTimeout(() => {
                    const poolToken = this.tokenPool.shift();
                    if (poolToken) connectWS(poolToken);
                }, delay);
            });

            ws.on('error', () => {});
        };

        const connectPusher = () => {
            const pws = new WebSocket(PUSHER_WS, {
                headers: { 'User-Agent': ua, 'Origin': 'https://kick.com' },
                agent: proxyAgent, rejectUnauthorized: false
            });

            pws.on('open', () => {
                pws.pingInt = setInterval(() => { if (pws.readyState === WebSocket.OPEN) pws.send(JSON.stringify({ event: 'pusher:ping', data: {} })); }, 30000);
            });

            pws.on('message', (d) => {
                try {
                    const msg = JSON.parse(d.toString());
                    if (msg.event === 'pusher:connection_established') {
                        ['channel_'+this.channelId, 'chatrooms.'+this.chatroomId+'.v2'].forEach(ch => {
                            pws.send(JSON.stringify({ event: 'pusher:subscribe', data: { auth: '', channel: ch } }));
                        });
                        this.state.pusher++;
                    }
                    if (msg.event === 'pusher:ping') pws.send(JSON.stringify({ event: 'pusher:pong', data: {} }));
                } catch (_) {}
            });

            pws.on('close', () => {
                this.state.pusher = Math.max(0, this.state.pusher - 1);
                clearInterval(pws.pingInt);
                setTimeout(() => connectPusher(), rand(5000, 15000));
            });

            pws.on('error', () => {});
        };

        connectWS(token);
        connectPusher();
    }

    async refreshTokenPool() {
        const needed = Math.max(Math.ceil(this.viewerCount * 0.25), this.viewerCount - this.state.connected);
        const capped = Math.max(25, Math.min(needed, 200)); // Límite de carga para refresh en background
        try {
            const tokens = await this.getViewerTokens(capped);
            if (tokens.length > 0) {
                this.tokenPool = this.tokenPool.concat(tokens);
                if (this.tokenPool.length > this.viewerCount * 2) this.tokenPool = this.tokenPool.slice(-this.viewerCount);
                this.state.refreshes++;
            }
        } catch (e) {}
    }

    updateDashboard() {
        console.clear();
        console.log([
            '╔══════════════════════════════════════════════════════════╗',
            '║   KICK VIEWER BOT PRO v18.0 — IPC Daemon Architecture ║',
            '╠══════════════════════════════════════════════════════════╣',
            `║  Stream      : ${pad(this.streamName, 42)}║`,
            `║  Token Pool  : ${pad(this.tokenPool.length + ' disponibles', 42)}║`,
            `║  HLS Video   : ${pad(this.playbackUrl ? 'Detectado y Descargando' : 'No Disponible', 42)}║`,
            `║  ViewerWS    : ${pad(this.state.connected + ' / ' + this.viewerCount, 42)}║`,
            `║  PusherWS    : ${pad(this.state.pusher + ' / ' + this.viewerCount, 42)}║`,
            `║  HLS Chunks  : ${pad(this.state.hlsDownloads + ' m3u8 peticiones TCP completadas', 42)}║`,
            `║  Reconex.    : ${pad(this.state.reconnects, 42)}║`,
            `║  RAM total   : ${pad(this.memUsage(), 42)}║`,
            `║  Uptime      : ${pad(this.formatUptime(), 42)}║`,
            '╚══════════════════════════════════════════════════════════╝'
        ].join('\n'));
    }

    async start() {
        console.log('Iniciando Daemon Python (Zero-Spawn IPC)...');
        await new Promise(r => setTimeout(r, 1000));

        console.log('Obteniendo canal y HLS Playlist...');
        await this.getChannelInfo();
        
        console.log('Obteniendo Tokens...');
        const tokens = await this.getViewerTokens(this.viewerCount);
        
        console.log('Pre-cargando token pool en background...');
        this.getViewerTokens(Math.min(Math.ceil(this.viewerCount * 0.25), 100)).then(res => { this.tokenPool = res; });

        console.log(`Lanzando ${tokens.length} viewers...`);
        for (let i=0; i<tokens.length; i++) {
            this.connectViewer(tokens[i]);
            
            // Stagger agresivo y pausado: No más de 20 unidas por tick para cuidar el proxy local
            const stagger = tokens.length > 5000 ? 50 : 150;
            if ((i + 1) % 100 === 0) {
                console.log(`Pausa de seguridad tras ${i+1} conexiones...`);
                await new Promise(r => setTimeout(r, 3000));
            }
            await new Promise(r => setTimeout(r, stagger));
        }

        setInterval(() => this.updateDashboard(), 3000);
        setInterval(() => this.refreshTokenPool(), 5 * 60 * 1000);
    }

    stop() {
        this.daemon.close();
        process.exit(0);
    }
}

const targetUrl = process.argv[2];
const targetCount = parseInt(process.argv[3]) || 50;

if (!targetUrl) { console.error('USO: node kick-websocket-PRO.js <URL> <CANTIDAD>'); process.exit(1); }

const bot = new KickViewerBotPro(targetUrl, targetCount);

process.on('SIGINT', () => { bot.stop(); });
process.on('uncaughtException', () => {}); // Catch-all de emergencia final
bot.start().catch(e => console.error(e));
