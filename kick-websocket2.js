'use strict';

/**
 * ════════════════════════════════════════════════════════════════════════════
 *  KICK VIEWER BOT v18.0 — FULL VIEWER SIMULATION (REFLECTING)
 * ════════════════════════════════════════════════════════════════════════════
 *
 *  KEY DIFFERENCE vs v17.x:
 *  Kick counts viewers via HLS video stream access, not just WS connections.
 *  This tool implements the FULL viewing pipeline:
 *  [1] Page load + cookies (unique session per viewer)
 *  [2] Livestream API call → get playback_url (HLS manifest)
 *  [3] HLS playlist polling (simulates active video player)
 *  [4] Viewer WebSocket (authenticated, persistent)
 *  [5] Pusher WebSocket (channel presence)
 *  [6] Periodic HLS chunk requests (maintains "active viewer" status)
 *  [7] Token refresh cycle (prevents session expiry)
 *
 *  USAGE: node kick-websocket2.js <URL> [viewers]
 *  REQ  : pip install curl_cffi && npm install ws
 * ════════════════════════════════════════════════════════════════════════════
 */

const { spawn } = require('child_process');
const http = require('http');
const https = require('https');
const crypto = require('crypto');
const WebSocket = require('ws');

require('events').EventEmitter.defaultMaxListeners = 200000;

const CLIENT_TOKEN = 'e1393935a959b4020a4491574f6490129f678acdaa92760471263db43487f823';
const WS_CONNECT = 'wss://websockets.kick.com/viewer/v1/connect';
const PUSHER_KEY = '32cbd69e4b950bf97679';
const PUSHER_WS = `wss://ws-us2.pusher.com/app/${PUSHER_KEY}?protocol=7&client=js&version=8.4.0&flash=false`;

const USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:133.0) Gecko/20100101 Firefox/133.0',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.1 Safari/605.1.15',
];

const rand = (min, max) => Math.floor(Math.random() * (max - min + 1)) + min;
const pad = (s, n) => String(s).padEnd(n);
const rndUA = () => USER_AGENTS[Math.floor(Math.random() * USER_AGENTS.length)];

function isValidToken(t) {
    return t && typeof t === 'object' && typeof t.token === 'string' && t.token.trim().length > 20;
}

// ════════════════════════════════════════════════════════════════════════════
// [3] TOKEN POOL — Deduplicated, capped, with invalidation
// ════════════════════════════════════════════════════════════════════════════

class TokenPool {
    constructor(maxSize = 10000) {
        this._items = [];
        this._seen = new Set();
        this._invalidated = new Set();
        this._maxSize = maxSize;
        this._invalidatedCap = 50000;
    }

    add(tokenObj) {
        if (!isValidToken(tokenObj)) return false;
        const key = tokenObj.token;
        if (this._seen.has(key) || this._invalidated.has(key)) return false;
        this._items.push(tokenObj);
        this._seen.add(key);
        this._enforceCap();
        return true;
    }

    addMany(arr) {
        let added = 0;
        for (const t of arr) { if (this.add(t)) added++; }
        return added;
    }

    take() {
        while (this._items.length > 0) {
            const t = this._items.shift();
            if (!this._invalidated.has(t.token)) {
                this._seen.delete(t.token);
                return t;
            }
            this._seen.delete(t.token);
            this._invalidated.delete(t.token);
        }
        return null;
    }

    invalidateToken(token) {
        this._invalidated.add(token);
        if (this._invalidated.size > this._invalidatedCap) this._pruneInvalidated();
    }

    get size() { return this._items.length; }

    _enforceCap() {
        while (this._items.length > this._maxSize) {
            const removed = this._items.shift();
            this._seen.delete(removed.token);
        }
    }

    _pruneInvalidated() {
        const kept = new Set();
        for (const t of this._invalidated) { if (this._seen.has(t)) kept.add(t); }
        this._invalidated = kept;
    }

    clear() {
        this._items = []; this._seen.clear(); this._invalidated.clear();
    }
}

// ════════════════════════════════════════════════════════════════════════════
// HLS FETCHER — Periodic m3u8 playlist access (critical for viewer count)
// ════════════════════════════════════════════════════════════════════════════

class HLSFetcher {
    constructor(channelName) {
        this.channelName = channelName;
        this.playbackUrl = null;
        this.m3u8Interval = null;
        this._stopped = false;
    }

    async init() {
        return this._fetchPlaybackUrl();
    }

    _fetchPlaybackUrl() {
        return new Promise(resolve => {
            const req = https.request({
                hostname: 'kick.com',
                path: `/api/v2/channels/${this.channelName}/livestream`,
                method: 'GET',
                headers: { 'User-Agent': rndUA(), 'Accept': 'application/json' },
            }, res => {
                let data = '';
                res.on('data', c => data += c);
                res.on('end', () => {
                    try {
                        const json = JSON.parse(data);
                        const ls = json.livestream || json;
                        this.playbackUrl = ls.playback_url || null;
                        resolve(!!this.playbackUrl);
                    } catch { resolve(false); }
                });
            });
            req.on('error', () => resolve(false));
            req.setTimeout(15000);
            req.end();
        });
    }

    // Single HLS playlist request — simulates video player tick
    fetchPlaylistOnce(cookie, ua) {
        if (!this.playbackUrl) return Promise.resolve(false);
        return new Promise(resolve => {
            const url = new URL(this.playbackUrl);
            const req = https.request({
                hostname: url.hostname,
                path: url.pathname + url.search,
                method: 'GET',
                headers: {
                    'User-Agent': ua || rndUA(),
                    'Accept': '*/*',
                    'Referer': `https://kick.com/${this.channelName}`,
                    'Origin': 'https://kick.com',
                    cookie: cookie || '',
                },
            }, res => {
                // Consume response to complete the request
                res.resume();
                res.on('end', () => resolve(res.statusCode >= 200 && res.statusCode < 400));
            });
            req.on('error', () => resolve(false));
            req.setTimeout(15000);
            req.end();
        });
    }

    startPolling(cookie, ua, intervalMs = 10000) {
        if (this.m3u8Interval) return;
        // Initial fetch immediately
        this.fetchPlaylistOnce(cookie, ua);
        this.m3u8Interval = setInterval(() => {
            if (this._stopped) return;
            this.fetchPlaylistOnce(cookie, ua).then(ok => {
                if (!ok) {
                    // Playback URL may have expired — refresh it
                    this._fetchPlaybackUrl().then(() => {
                        if (this.playbackUrl) this.fetchPlaylistOnce(cookie, ua);
                    });
                }
            });
        }, intervalMs);
    }

    stop() {
        this._stopped = true;
        if (this.m3u8Interval) { clearInterval(this.m3u8Interval); this.m3u8Interval = null; }
    }
}

// ════════════════════════════════════════════════════════════════════════════
// [1] PERSISTENT PYTHON WORKER — Full session emulation per viewer
// ════════════════════════════════════════════════════════════════════════════

class PythonTokenWorker {
    constructor() {
        this.proc = null;
        this.ready = false;
        this.requestId = 0;
        this.pendingRequests = new Map();
        this.buffer = '';
        this._stopped = false;
        this._restartAttempts = 0;
        this._restartTimer = null;
        this._script = null;
    }

    async start() {
        this._stopped = false;
        this._restartAttempts = 0;
        return this._launch();
    }

    async _launch() {
        if (this._stopped) return;
        this._killProcess();
        console.log('  [WORKER] Starting persistent Python token worker...');

        this._script = `
import json, sys, uuid, time, threading, random, concurrent.futures
from concurrent.futures import ThreadPoolExecutor
from curl_cffi import requests as cffi_requests

CLIENT_TOKEN = "${CLIENT_TOKEN}"
POOL_SIZE = 50

UAS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:133.0) Gecko/20100101 Firefox/133.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.1 Safari/605.1.15",
]

executor = ThreadPoolExecutor(max_workers=POOL_SIZE)

def fetch_one_token(channel_name, cookie_dict):
    """
    Complete viewing session setup:
    1. Load page → get cookies
    2. Hit /api/v2/livestream → register IP as viewer
    3. Get viewer token → authenticated WS credential
    """
    ua = random.choice(UAS)
    session = None
    retries = 0
    max_retries = 3
    while retries < max_retries and session is None:
        try:
            session = cffi_requests.Session(impersonate="chrome131")
            # Step 1: Load the channel page (registers browser session)
            session.get(f"https://kick.com/{channel_name}",
                headers={"User-Agent": ua, "Accept": "text/html,*/*",
                    "sec-fetch-dest": "document", "sec-fetch-mode": "navigate"},
                timeout=20)
            # Step 2: Livestream API — THIS is what registers the viewer
            try:
                ls = session.get(f"https://kick.com/api/v2/channels/{channel_name}/livestream",
                    headers={"User-Agent": ua, "Accept": "application/json"}, timeout=15)
                if ls.status_code == 200:
                    ls_data = ls.json()
                    playback_url = (ls_data.get("livestream") or ls_data).get("playback_url")
                    if playback_url:
                        # Step 2b: Access HLS manifest — simulates video player loading
                        try:
                            session.get(playback_url,
                                headers={"User-Agent": ua, "Accept": "*/*",
                                    "Referer": f"https://kick.com/{channel_name}"},
                                timeout=10)
                        except: pass
            except: pass
            break
        except Exception as e:
            retries += 1
            if retries < max_retries:
                wait_time = min(5, (2 ** retries) + random.uniform(0, 1))
                time.sleep(wait_time)
                session = None
            else:
                return None
    if session is None:
        return None
    # Step 3: Get viewer token
    token_retry = 0
    while token_retry < 2:
        try:
            r = session.get("https://websockets.kick.com/viewer/v1/token",
                headers={
                    "User-Agent": ua,
                    "Accept": "application/json, text/plain, */*",
                    "sec-ch-ua": '"Google Chrome";v="131", "Chromium";v="131"',
                    "sec-ch-ua-mobile": "?0",
                    "sec-ch-ua-platform": '"Windows"',
                    "sec-fetch-dest": "empty",
                    "sec-fetch-mode": "cors",
                    "sec-fetch-site": "same-site",
                    "Origin": "https://kick.com",
                    "Referer": f"https://kick.com/{channel_name}",
                    "X-CLIENT-TOKEN": CLIENT_TOKEN,
                    "X-Device-ID": str(uuid.uuid4()),
                    "X-Session-ID": str(uuid.uuid4()),
                }, timeout=20)
            if r.status_code == 200:
                token = r.json().get("data", {}).get("token", "")
                if token:
                    cookie_str = "; ".join([f"{k}={v}" for k, v in session.cookies.get_dict().items()])
                    return {"token": token, "cookie": cookie_str, "ua": ua}
                return None
            elif r.status_code == 429:
                time.sleep(5)
                token_retry += 1
            else:
                token_retry += 1
                if token_retry < 2:
                    time.sleep(1)
        except Exception as e:
            token_retry += 1
            if token_retry < 2:
                time.sleep(1)
    return None

def discover_channel(channel_name):
    try:
        ua = random.choice(UAS)
        res = cffi_requests.get(f"https://kick.com/api/v1/channels/{channel_name}",
            headers={"User-Agent": ua, "Accept": "application/json"},
            impersonate="chrome131", timeout=15)
        if res.status_code == 200:
            d = res.json()
            ls = d.get("livestream") or {}
            return {"id": d.get("id"), "chatroom_id": (d.get("chatroom") or {}).get("id"),
                "live": d.get("livestream") is not None,
                "viewers": ls.get("viewers", 0),
                "title": ls.get("session_title", ""),
                "playback_url": ls.get("playback_url"),
                "cookies": "; ".join([f"{k}={v}" for k, v in res.cookies.get_dict().items()]),
                "ua": ua}
        return {"error": f"HTTP {res.status_code}"}
    except Exception as e:
        return {"error": str(e)}

def get_hls_url(channel_name):
    """Get HLS playback URL for periodic player simulation"""
    try:
        ua = random.choice(UAS)
        res = cffi_requests.get(f"https://kick.com/api/v2/channels/{channel_name}/livestream",
            headers={"User-Agent": ua, "Accept": "application/json"},
            impersonate="chrome131", timeout=15)
        if res.status_code == 200:
            d = res.json()
            ls = d.get("livestream") or d
            return {"playback_url": ls.get("playback_url")}
        return {"error": f"HTTP {res.status_code}"}
    except Exception as e:
        return {"error": str(e)}

def get_tokens_batch(channel_name, count, cookies):
    cookie_dict = {}
    if cookies:
        for item in cookies.split('; '):
            if '=' in item:
                k, v = item.split('=', 1)
                cookie_dict[k.strip()] = v.strip()
    tokens = []
    lock = threading.Lock()
    submitted = 0
    active_futures = {}
    def submit_next():
        nonlocal submitted
        if submitted < count:
            f = executor.submit(fetch_one_token, channel_name, cookie_dict)
            active_futures[f] = True
            submitted += 1
    for _ in range(min(POOL_SIZE, count)):
        submit_next()
    while active_futures:
        done_set, _ = concurrent.futures.wait(active_futures, return_when=concurrent.futures.FIRST_COMPLETED, timeout=90)
        for f in done_set:
            try:
                r = f.result()
                if r:
                    with lock:
                        tokens.append(r)
            except: pass
            del active_futures[f]
            submit_next()
    return {"tokens": tokens, "count": len(tokens)}

def get_single_token(channel_name, cookies):
    cookie_dict = {}
    if cookies:
        for item in cookies.split('; '):
            if '=' in item:
                k, v = item.split('=', 1)
                cookie_dict[k.strip()] = v.strip()
    return fetch_one_token(channel_name, cookie_dict) or {"error": "no_token"}

def write_response(request_id, data):
    sys.stdout.write(json.dumps({"id": request_id, "data": data}) + "\\n")
    sys.stdout.flush()

def process_command(line):
    try:
        cmd = json.loads(line.strip())
        action = cmd.get("action")
        rid = cmd.get("id", 0)
        if action == "discover":
            write_response(rid, discover_channel(cmd.get("channel", "")))
        elif action == "hls_url":
            write_response(rid, get_hls_url(cmd.get("channel", "")))
        elif action == "tokens":
            write_response(rid, get_tokens_batch(cmd.get("channel",""), cmd.get("count",1), cmd.get("cookies","")))
        elif action == "single_token":
            write_response(rid, get_single_token(cmd.get("channel",""), cmd.get("cookies","")))
        elif action == "health":
            write_response(rid, {"status": "alive"})
    except Exception as e:
        try: write_response(cmd.get("id", 0), {"error": str(e)})
        except: pass

for line in sys.stdin:
    line = line.strip()
    if line: process_command(line)
`.trim();

        return new Promise((resolve, reject) => {
            this.proc = spawn('python3', ['-c', this._script], {
                stdio: ['pipe', 'pipe', 'pipe'],
            });
            this.proc.stdout.on('data', data => {
                this.buffer += data.toString();
                this.processBuffer();
            });
            this.proc.stderr.on('data', data => {
                const msg = data.toString().trim();
                if (msg && msg.length < 200) process.stderr.write(`[WORKER] ${msg}\n`);
            });
            this.proc.on('error', err => {
                this.ready = false;
                this._failPending(err.message);
            });
            this.proc.on('close', code => {
                this.ready = false;
                this._failPending(`exit code ${code}`);
                if (!this._stopped) this._scheduleRestart(code);
            });
            const timeout = setTimeout(() => reject(new Error('Worker startup timeout')), 10000);
            this.sendCommand('health', {}, response => {
                clearTimeout(timeout);
                if (response && !response.error) {
                    this.ready = true;
                    this._restartAttempts = 0;
                    console.log('  [WORKER] Ready.');
                    resolve();
                } else {
                    reject(new Error('Worker health check failed'));
                }
            });
        });
    }

    _killProcess() {
        if (!this.proc) return;
        try {
            if (this.proc.stdin && !this.proc.stdin.destroyed) this.proc.stdin.end();
            this.proc.kill('SIGKILL');
        } catch {}
        this.proc = null;
        this.ready = false;
    }

    _scheduleRestart(exitCode) {
        if (this._restartTimer) return;
        const delay = Math.min(120000, 5000 * Math.pow(2, this._restartAttempts));
        this._restartAttempts++;
        console.log(`  [WORKER] Restarting in ${delay / 1000}s (attempt ${this._restartAttempts})...`);
        this._restartTimer = setTimeout(() => {
            this._restartTimer = null;
            this._launch().catch(() => {});
        }, delay);
    }

    _failPending(reason) {
        for (const [id, cb] of this.pendingRequests) {
            this.pendingRequests.delete(id);
            cb(null);
        }
    }

    sendCommand(action, params, callback) {
        const requestId = ++this.requestId;
        const timeout = setTimeout(() => {
            if (this.pendingRequests.has(requestId)) {
                this.pendingRequests.delete(requestId);
                callback(null);
            }
        }, 90000);
        this.pendingRequests.set(requestId, (...args) => {
            clearTimeout(timeout);
            callback(...args);
        });
        const cmd = JSON.stringify({ id: requestId, action, ...params });
        if (this.proc && this.proc.stdin.writable) {
            this.proc.stdin.write(cmd + '\n');
        } else {
            clearTimeout(timeout);
            this.pendingRequests.delete(requestId);
            callback(null);
        }
        return requestId;
    }

    processBuffer() {
        const lines = this.buffer.split('\n');
        this.buffer = lines.pop() || '';
        for (const line of lines) {
            if (!line.trim()) continue;
            try {
                const response = JSON.parse(line);
                const cb = this.pendingRequests.get(response.id);
                if (cb) { this.pendingRequests.delete(response.id); cb(response.data); }
            } catch {}
        }
    }

    async discover(channelName) {
        return new Promise(resolve => this.sendCommand('discover', { channel: channelName }, resolve));
    }

    async getHlsUrl(channelName) {
        return new Promise(resolve => this.sendCommand('hls_url', { channel: channelName }, resolve));
    }

    async getTokens(channelName, count, cookies) {
        return new Promise(resolve => this.sendCommand('tokens', { channel: channelName, count, cookies }, resolve));
    }

    async getSingleToken(channelName, cookies) {
        return new Promise(resolve => this.sendCommand('single_token', { channel: channelName, cookies }, resolve));
    }

    stop() {
        this._stopped = true;
        if (this._restartTimer) { clearTimeout(this._restartTimer); this._restartTimer = null; }
        this._killProcess();
        this._failPending('stopped');
        this.ready = false;
    }
}

// ════════════════════════════════════════════════════════════════════════════
// [8] CONNECTION CONCURRENCY LIMITER
// ════════════════════════════════════════════════════════════════════════════

class ConnectionLimiter {
    constructor(maxConcurrent, maxQueue = 5000) {
        this._active = 0;
        this._maxConcurrent = maxConcurrent;
        this._queue = [];
        this._maxQueue = maxQueue;
    }

    acquire(callback) {
        if (this._active < this._maxConcurrent) {
            this._active++;
            callback(this._release.bind(this));
            return;
        }
        if (this._queue.length < this._maxQueue) this._queue.push(callback);
    }

    _release() {
        this._active = Math.max(0, this._active - 1);
        const next = this._queue.shift();
        if (next) { this._active++; next(this._release.bind(this)); }
    }

    get active() { return this._active; }
    get queued() { return this._queue.length; }
}

// ════════════════════════════════════════════════════════════════════════════
// KICK VIEWER BOT v18.0 — FULL SIMULATION
// ════════════════════════════════════════════════════════════════════════════

class KickViewerBotV18 {
    constructor(streamUrl, viewerCount) {
        this.streamUrl = streamUrl;
        this.viewerCount = viewerCount;
        this.streamName = streamUrl.replace(/\/$/, '').split('/').pop();
        this.channelId = null;
        this.chatroomId = null;
        this.playbackUrl = null;
        this.startTime = Date.now();
        this.lastDiscovery = null;
        this.sockets = [];
        this.tokenPool = new TokenPool(Math.max(viewerCount * 2, 5000));
        this.isRefreshing = false;
        this.worker = new PythonTokenWorker();
        this.hlsFetcher = null;

        this.state = {
            tokens: 0,
            connected: 0,
            handshake: 0,
            pusher: 0,
            failed: 0,
            reconnects: 0,
            refreshes: 0,
            sessionRefreshes: 0,
            hlsRequests: 0,
        };

        this.latencies = [];
        this.maxLatencySamples = 100;
        this.backoffTracker = {};
        this.maxBackoffMs = 300000;
        this.stableThresholdMs = 30000;
        this._connLimiter = new ConnectionLimiter(500);
    }

    formatUptime() {
        const s = Math.floor((Date.now() - this.startTime) / 1000);
        return `${String(Math.floor(s / 3600)).padStart(2, '0')}:${String(Math.floor((s % 3600) / 60)).padStart(2, '0')}:${String(s % 60).padStart(2, '0')}`;
    }

    memUsage() { return `${(process.memoryUsage().rss / 1024 / 1024).toFixed(1)} MB`; }

    getAvgLatency() {
        if (this.latencies.length === 0) return 'N/A';
        return `${(this.latencies.reduce((a, b) => a + b, 0) / this.latencies.length).toFixed(0)}ms`;
    }

    registerSocket(ws) { this.sockets.push(ws); }

    removeSocket(ws) {
        const idx = this.sockets.indexOf(ws);
        if (idx !== -1) this.sockets.splice(idx, 1);
        if (ws._cleanup) { ws._cleanup(); ws._cleanup = null; }
    }

    // ──────────────────────────────────────────────────────────────────────
    // DISCOVERY
    // ──────────────────────────────────────────────────────────────────────
    async discoverViaWorker() {
        try {
            console.log('  [1/4] Discovering channel via persistent worker...');
            if (this.worker.ready) {
                const data = await this.worker.discover(this.streamName);
                if (data && data.id) {
                    this._applyDiscovery(data);
                    return true;
                }
            }
            return false;
        } catch (e) {
            console.log(`  [DISCOVERY] Exception: ${e.message}`);
            return false;
        }
    }

    async fetchHlsUrl() {
        if (this.worker.ready) {
            const data = await this.worker.getHlsUrl(this.streamName);
            if (data && data.playback_url) {
                this.playbackUrl = data.playback_url;
                console.log(`  [HLS] Playback URL obtained`);
                return true;
            }
        }
        return false;
    }

    _applyDiscovery(data) {
        this.channelId = String(data.id);
        this.chatroomId = data.chatroom_id ? String(data.chatroom_id) : null;
        this.playbackUrl = data.playback_url || null;
        this.lastDiscovery = Date.now();
        console.log(`  [DISCOVERY] Channel ID: ${this.channelId} | Chatroom: ${this.chatroomId || '???'}`);
        console.log(`  [DISCOVERY] En vivo: ${data.live ? 'SI (' + data.viewers + ') — ' + data.title : 'NO'}`);
        if (this.playbackUrl) console.log(`  [DISCOVERY] HLS URL: ${this.playbackUrl.substring(0, 60)}...`);
    }

    // ──────────────────────────────────────────────────────────────────────
    // TOKEN ACQUISITION
    // ──────────────────────────────────────────────────────────────────────
    async getViewerTokens(count) {
        console.log(`  [2/4] Getting ${count} tokens...`);
        let tokens = [];
        if (this.worker.ready) {
            const result = await this.worker.getTokens(this.streamName, count, '');
            if (result && result.tokens) {
                tokens = result.tokens.filter(isValidToken);
                console.log(`  [WORKER] ${tokens.length}/${count} obtained`);
            }
        }
        this.state.tokens += tokens.length;
        return tokens;
    }

    async getSingleToken() {
        if (this.worker.ready) {
            const result = await this.worker.getSingleToken(this.streamName, '');
            if (result && result.token && result.token.length > 20) return result;
        }
        return null;
    }

    // ──────────────────────────────────────────────────────────────────────
    // SESSION REFRESH
    // ──────────────────────────────────────────────────────────────────────
    triggerSessionRefresh() {
        if (this.isRefreshing) return;
        this.isRefreshing = true;
        (async () => {
            console.log('\n  [SESSION REFRESH] Re-running discovery...');
            const success = await this.discoverViaWorker();
            if (success) {
                const count = Math.max(50, Math.ceil(this.viewerCount * 0.1));
                const tokens = await this.getViewerTokens(count);
                const added = this.tokenPool.addMany(tokens);
                console.log(`  [SESSION REFRESH] ${added} new tokens added.\n`);
            } else {
                console.log('  [SESSION REFRESH] Failed, retrying in 60s...\n');
                setTimeout(() => { this.isRefreshing = false; this.triggerSessionRefresh(); }, 60000);
                return;
            }
            this.isRefreshing = false;
        })();
    }

    async refreshTokenPool() {
        if (this.isRefreshing) return;
        const needed = Math.max(Math.ceil(this.viewerCount * 0.15), this.viewerCount - this.state.connected);
        const capped = Math.max(20, Math.min(needed, this.viewerCount));
        console.log(`\n  [POOL REFRESH] Requesting ${capped} tokens...`);
        const tokens = await this.getViewerTokens(capped);
        const added = this.tokenPool.addMany(tokens);
        if (added > 0) {
            this.state.refreshes++;
            console.log(`  [POOL REFRESH] Pool: ${this.tokenPool.size} tokens`);
        } else {
            console.log('  [POOL REFRESH] Failed, retrying in 2 min...');
        }
    }

    startTokenRefreshLoop() {
        setTimeout(() => {
            this.refreshTokenPool();
            setInterval(() => this.refreshTokenPool(), 8 * 60 * 1000);
        }, 5 * 60 * 1000);
    }

    // ──────────────────────────────────────────────────────────────────────
    // BACKOFF
    // ──────────────────────────────────────────────────────────────────────
    getBackoffDelay(viewerIndex, closeCode) {
        if (!this.backoffTracker[viewerIndex]) {
            this.backoffTracker[viewerIndex] = { count: 0, code: closeCode };
        }
        const tracker = this.backoffTracker[viewerIndex];
        if (tracker.code !== closeCode) { tracker.count = 0; tracker.code = closeCode; }
        tracker.count++;
        if (closeCode === 4003) {
            const delay = Math.min(this.maxBackoffMs, 10000 * Math.pow(2, tracker.count - 1));
            const jitter = delay * 0.2 * Math.random();
            return delay + jitter;
        }
        return rand(5000, 15000);
    }

    resetBackoff(viewerIndex) {
        if (this.backoffTracker[viewerIndex]) this.backoffTracker[viewerIndex].count = 0;
    }

    // ──────────────────────────────────────────────────────────────────────
    // HLS PLAYER SIMULATION — Critical for viewer count
    // ──────────────────────────────────────────────────────────────────────
    startHlsPollingForViewer(tokenObj, viewerIndex) {
        if (!this.playbackUrl) return;
        const { cookie, ua } = tokenObj;

        const pollHls = async () => {
            try {
                const url = new URL(this.playbackUrl);
                const req = https.request({
                    hostname: url.hostname,
                    path: url.pathname + url.search,
                    method: 'GET',
                    headers: {
                        'User-Agent': ua || rndUA(),
                        'Accept': '*/*',
                        'Referer': `https://kick.com/${this.streamName}`,
                        'Origin': 'https://kick.com',
                        'Cookie': cookie || '',
                    },
                }, res => {
                    res.resume();
                    res.on('end', () => { this.state.hlsRequests++; });
                });
                req.on('error', () => {});
                req.setTimeout(10000);
                req.end();
            } catch {}
        };

        // Poll every 8-12 seconds — simulates video player refreshing the playlist
        const interval = setInterval(() => {
            pollHls();
        }, rand(8000, 12000));

        // Initial request
        pollHls();

        return interval;
    }

    // ──────────────────────────────────────────────────────────────────────
    // VIEWER WEBSOCKET + PUSHER + HLS = Full session
    // ──────────────────────────────────────────────────────────────────────
    connectViewer(index, tokenObj) {
        if (!isValidToken(tokenObj)) {
            const poolToken = this.tokenPool.take();
            if (poolToken && isValidToken(poolToken)) {
                return this.connectViewer(index, poolToken);
            }
            this.getSingleToken().then(fresh => {
                if (fresh) this.connectViewer(index, fresh);
                else setTimeout(() => this.getSingleToken().then(f2 => { if (f2) this.connectViewer(index, f2); }), rand(10000, 30000));
            });
            return;
        }

        const { token, cookie, ua } = tokenObj;

        // ── HLS Player polling (critical for viewer count) ──
        let hlsInterval = null;
        if (this.playbackUrl) {
            hlsInterval = this.startHlsPollingForViewer(tokenObj, index);
        }

        // ── Viewer WebSocket ──
        const ws = new WebSocket(`${WS_CONNECT}?token=${token}`, {
            headers: {
                'User-Agent': ua || rndUA(),
                'Origin': 'https://kick.com',
                'Cookie': cookie || '',
                'Cache-Control': 'no-cache',
                'Pragma': 'no-cache',
            },
            rejectUnauthorized: false,
        });

        let pingInterval = null;
        let pendingPing = null;
        let pendingPingTimeout = null;
        let handshakeSent = false;
        let handshakeValidated = false;
        let handshakeTimeout = null;
        let connectionAlive = false;

        const clearPendingPing = () => {
            if (pendingPingTimeout) { clearTimeout(pendingPingTimeout); pendingPingTimeout = null; }
            pendingPing = null;
        };

        const cleanup = () => {
            if (pingInterval) { clearInterval(pingInterval); pingInterval = null; }
            if (handshakeTimeout) { clearTimeout(handshakeTimeout); handshakeTimeout = null; }
            if (hlsInterval) { clearInterval(hlsInterval); hlsInterval = null; }
            clearPendingPing();
        };

        ws.on('open', () => {
            handshakeSent = true;
            ws.send(JSON.stringify({
                type: 'channel_handshake',
                data: { message: { channelId: this.channelId } },
            }));

            handshakeTimeout = setTimeout(() => {
                if (!handshakeValidated && ws.readyState === WebSocket.OPEN) {
                    this.state.failed++;
                    ws.close(1000, 'handshake timeout');
                }
            }, 10000);

            pingInterval = setInterval(() => {
                try {
                    if (ws.readyState === WebSocket.OPEN && !pendingPing) {
                        const pingId = `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
                        pendingPing = { id: pingId, ts: Date.now() };
                        ws.send(JSON.stringify({ type: 'ping', data: { id: pingId } }));
                        pendingPingTimeout = setTimeout(() => {
                            pendingPing = null;
                            pendingPingTimeout = null;
                        }, 30000);
                    }
                } catch {}
            }, 25000);
        });

        ws.on('message', data => {
            try {
                const msg = JSON.parse(data.toString());
                if (handshakeSent && !handshakeValidated) {
                    const isExplicitResponse = msg.type === 'channel_handshake_response' || msg.event === 'channel_handshake_response';
                    const isChannelEvent = msg.event && (
                        msg.event.startsWith('channel_') ||
                        msg.event.startsWith('chatroom_') ||
                        msg.event.startsWith('livestream_') ||
                        msg.event.startsWith('message:')
                    );
                    if (isExplicitResponse || isChannelEvent) {
                        clearTimeout(handshakeTimeout);
                        handshakeValidated = true;
                        connectionAlive = true;
                        this.state.connected++;
                        this.registerSocket(ws);
                        this.state.handshake++;
                        this.resetBackoff(index);
                        if (index <= 3) console.log(`  [Viewer ${index}] Connected ✓`);
                    }
                }
                if (pendingPing && msg.type === 'pong') {
                    if (msg.data && msg.data.id === pendingPing.id) {
                        const latency = Date.now() - pendingPing.ts;
                        this.latencies.push(latency);
                        if (this.latencies.length > this.maxLatencySamples) this.latencies.shift();
                    }
                    clearPendingPing();
                }
                if (msg.event === 'ping' || msg.type === 'ping') {
                    if (ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify({ type: 'pong' }));
                }
            } catch {}
        });

        ws.on('ping', () => { try { if (ws.readyState === WebSocket.OPEN) ws.pong(); } catch {} });
        ws.on('error', () => {});

        ws.on('close', (code) => {
            cleanup();
            ws._cleanup = null;
            if (connectionAlive) {
                this.state.connected = Math.max(0, this.state.connected - 1);
            }
            this.removeSocket(ws);
            if (code === 1000) return;
            this.state.reconnects++;
            if (code === 4003) {
                this.state.sessionRefreshes++;
                this.tokenPool.invalidateToken(token);
            }
            if (code === 1006 || code === 4003) this.triggerSessionRefresh();
            const delay = this.getBackoffDelay(index, code);
            setTimeout(() => {
                this._connLimiter.acquire((release) => {
                    const poolToken = this.tokenPool.take();
                    if (poolToken && isValidToken(poolToken)) {
                        this.connectViewer(index, poolToken);
                    } else {
                        this.getSingleToken().then(fresh => {
                            if (fresh) this.connectViewer(index, fresh);
                        });
                    }
                    release();
                });
            }, delay);
        });

        ws._cleanup = cleanup;

        // ── Pusher WebSocket ──
        this.connectPusher(tokenObj, index);
    }

    // ──────────────────────────────────────────────────────────────────────
    // PUSHER WEBSOCKET
    // ──────────────────────────────────────────────────────────────────────
    connectPusher(tokenObj, viewerIndex) {
        const ua = (tokenObj && tokenObj.ua) || rndUA();
        const cookie = (tokenObj && tokenObj.cookie) || '';

        const pws = new WebSocket(PUSHER_WS, {
            headers: {
                'User-Agent': ua,
                'Cookie': cookie,
                'Origin': 'https://kick.com',
            },
            rejectUnauthorized: false,
        });

        let pusherPingInterval = null;
        let pendingPusherPing = null;
        let pendingPusherPingTimeout = null;
        let pusherConnected = false;

        const clearPendingPusherPing = () => {
            if (pendingPusherPingTimeout) { clearTimeout(pendingPusherPingTimeout); pendingPusherPingTimeout = null; }
            pendingPusherPing = null;
        };

        const cleanup = () => {
            if (pusherPingInterval) { clearInterval(pusherPingInterval); pusherPingInterval = null; }
            clearPendingPusherPing();
        };

        pws.on('open', () => {
            pusherPingInterval = setInterval(() => {
                try {
                    if (pws.readyState === WebSocket.OPEN && !pendingPusherPing) {
                        pendingPusherPing = Date.now();
                        pws.send(JSON.stringify({ event: 'pusher:ping', data: {} }));
                        pendingPusherPingTimeout = setTimeout(() => {
                            pendingPusherPing = null;
                            pendingPusherPingTimeout = null;
                        }, 30000);
                    }
                } catch {}
            }, 30000);

            const channels = [
                `channel_${this.channelId}`,
                `channel.${this.channelId}`,
                `chatrooms.${this.chatroomId || this.channelId}.v2`,
                `chatroom_${this.chatroomId || this.channelId}`,
                `chatrooms.${this.chatroomId || this.channelId}`,
                'drops_category_8',
            ];
            channels.forEach(ch => {
                try { pws.send(JSON.stringify({ event: 'pusher:subscribe', data: { auth: '', channel: ch } })); } catch {}
            });
        });

        pws.on('message', data => {
            try {
                const msg = JSON.parse(data.toString());
                if (msg.event === 'pusher:connection_established' && !pusherConnected) {
                    pusherConnected = true;
                    this.state.pusher++;
                    this.registerSocket(pws);
                }
                if (msg.event === 'pusher:pong' && pendingPusherPing) {
                    this.latencies.push(Date.now() - pendingPusherPing);
                    if (this.latencies.length > this.maxLatencySamples) this.latencies.shift();
                    clearPendingPusherPing();
                }
                if (msg.event === 'pusher:ping') {
                    if (pws.readyState === WebSocket.OPEN) pws.send(JSON.stringify({ event: 'pusher:pong', data: {} }));
                }
            } catch {}
        });

        pws.on('ping', () => { try { if (pws.readyState === WebSocket.OPEN) pws.pong(); } catch {} });
        pws.on('error', () => {});

        pws.on('close', () => {
            cleanup();
            if (pusherConnected) this.state.pusher = Math.max(0, this.state.pusher - 1);
            this.removeSocket(pws);
            setTimeout(() => this.connectPusher(tokenObj, viewerIndex), rand(3000, 10000));
        });
    }

    // ──────────────────────────────────────────────────────────────────────
    // DASHBOARD
    // ──────────────────────────────────────────────────────────────────────
    updateDashboard() {
        console.clear();
        const uptime = this.formatUptime();
        const mem = this.memUsage();
        const avgLatency = this.getAvgLatency();
        const discoveryInfo = this.lastDiscovery ? `Last: ${new Date(this.lastDiscovery).toLocaleTimeString()}` : 'Pending...';
        const workerStatus = this.worker.ready ? 'Online' : 'Offline';
        const hlsStatus = this.playbackUrl ? 'Active' : 'Inactive';
        const statusLine = this.state.connected > 0
            ? `${this.state.connected} ViewerWS + ${this.state.pusher} PusherWS + HLS active`
            : this.state.tokens > 0 ? 'Connecting viewers...' : 'Getting tokens...';

        console.log([
            '',
            '╔══════════════════════════════════════════════════════════╗',
            '║ KICK VIEWER BOT v18.0 — FULL VIEWER SIMULATION           ║',
            '╠══════════════════════════════════════════════════════════╣',
            `║ Stream       : ${pad(this.streamName, 42)}║`,
            `║ Channel ID   : ${pad(this.channelId || '???', 42)}║`,
            `║ HLS Player   : ${pad(hlsStatus + ' | ' + discoveryInfo, 42)}║`,
            `║ Worker       : ${pad(workerStatus, 42)}║`,
            '╠══════════════════════════════════════════════════════════╣',
            `║ Tokens JWT   : ${pad(this.state.tokens, 42)}║`,
            `║ Token Pool   : ${pad(this.tokenPool.size + ' available', 42)}║`,
            `║ ViewerWS     : ${pad(this.state.connected + ' / ' + this.viewerCount, 42)}║`,
            `║ PusherWS     : ${pad(this.state.pusher + ' / ' + this.viewerCount, 42)}║`,
            `║ HLS Requests : ${pad(this.state.hlsRequests, 42)}║`,
            `║ Handshakes   : ${pad(this.state.handshake, 42)}║`,
            `║ Failed HS    : ${pad(this.state.failed, 42)}║`,
            `║ Reconnects   : ${pad(this.state.reconnects, 42)}║`,
            `║ Session Ref. : ${pad(this.state.sessionRefreshes + ' refreshes', 42)}║`,
            '╠══════════════════════════════════════════════════════════╣',
            `║ Net Health   : ${pad('Avg latency: ' + avgLatency + ' | Samples: ' + this.latencies.length, 42)}║`,
            `║ RAM Total    : ${pad(mem, 42)}║`,
            `║ Uptime       : ${pad(uptime, 42)}║`,
            '╠══════════════════════════════════════════════════════════╣',
            `║ ${pad(statusLine, 57)}║`,
            '╚══════════════════════════════════════════════════════════╝',
            '',
        ].join('\n'));
    }

    // ──────────────────────────────────────────────────────────────────────
    // MAIN BOOT SEQUENCE
    // ──────────────────────────────────────────────────────────────────────
    async start() {
        console.clear();
        console.log('\n╔══════════════════════════════════════════════════════════╗');
        console.log('║ KICK VIEWER BOT v18.0 — FULL VIEWER SIMULATION           ║');
        console.log('║ Page + Livestream API + HLS + ViewerWS + PusherWS        ║');
        console.log('╚══════════════════════════════════════════════════════════╝\n');
        console.log(` Stream  : ${this.streamName}`);
        console.log(` Viewers : ${this.viewerCount}`);

        // Start worker
        try { await this.worker.start(); }
        catch (e) { console.log(`  [WORKER] Failed: ${e.message}. Using one-shot.`); }

        // Discover channel
        const discovered = await this.discoverViaWorker();
        if (!discovered || !this.channelId) {
            console.log('  Cannot obtain channel ID. Exiting.');
            this.worker.stop();
            process.exit(1);
        }

        // Get HLS playback URL — critical for viewer simulation
        console.log('\n  [2.3/4] Fetching HLS playback URL...');
        await this.fetchHlsUrl();
        if (this.playbackUrl) {
            console.log(`  [HLS] URL: ${this.playbackUrl.substring(0, 80)}...`);
        } else {
            console.log('  [HLS] Could not obtain playback URL. Viewer count may be reduced.');
        }

        // Get viewer tokens (includes page load + livestream API + HLS access)
        console.log('\n  [2/4] Getting viewer tokens...');
        const tokens = await this.getViewerTokens(this.viewerCount);
        if (tokens.length === 0) {
            console.error('\n  No tokens obtained.');
            console.error('  Check: pip install curl_cffi');
            this.worker.stop();
            process.exit(1);
        }

        // Pre-load token pool
        console.log('\n  [2.5/4] Pre-loading token pool...');
        const extraCount = Math.min(Math.ceil(this.viewerCount * 0.15), 200);
        const extraTokens = await this.getViewerTokens(extraCount);
        const poolAdded = this.tokenPool.addMany(extraTokens);
        if (poolAdded > 0) console.log(`  Token pool: ${this.tokenPool.size} reserve tokens`);

        // Connect viewers
        console.log(`\n  [3/4] Connecting ${tokens.length} viewers (HLS + ViewerWS + PusherWS)...\n`);
        for (let i = 0; i < tokens.length; i++) {
            this.connectViewer(i + 1, tokens[i]);
            const stagger = tokens.length > 5000
                ? 20 + Math.random() * 50
                : (tokens.length > 1000 ? 50 + Math.random() * 100 : 250 + Math.random() * 350);
            if ((i + 1) % 500 === 0 && i + 1 < tokens.length) {
                console.log(`  Security pause (${i + 1}/${tokens.length} barrier)...`);
                await new Promise(r => setTimeout(r, 3000));
            }
            await new Promise(r => setTimeout(r, stagger));
        }

        console.log(`\n  ${tokens.length} viewers launched. Dashboard in 10s...`);
        this.startTokenRefreshLoop();
        setInterval(() => this.updateDashboard(), 10000);
    }
}

// ════════════════════════════════════════════════════════════════════════════
// MAIN ENTRY POINT
// ════════════════════════════════════════════════════════════════════════════

const targetUrl = process.argv[2];
const targetCount = parseInt(process.argv[3]) || 50;

if (!targetUrl) {
    console.error('\nUSAGE: node kick-websocket2.js <URL> [viewers]');
    console.error('EJ   : node kick-websocket2.js "https://kick.com/canal" 100\n');
    console.error('REQ  : pip install curl_cffi && npm install ws');
    process.exit(1);
}

const bot = new KickViewerBotV18(targetUrl, targetCount);

process.on('SIGINT', () => {
    console.log(`\nClosing ${bot.sockets.length} WebSockets...`);
    bot.worker.stop();
    bot.sockets.forEach(ws => { try { ws.close(1000); } catch {} });
    setTimeout(() => process.exit(0), 2000);
});

process.on('uncaughtException', e => {
    console.error('[UNCAUGHT]', e.message);
});

bot.start().catch(e => console.error('Error fatal:', e));
setInterval(() => {}, 1000);
