// kick-evidence-collector-final.js
// Evidencia de viewers reales y fake usando el bot real (kick-websocket.js)

const fs = require('fs');
const path = require('path');
const { spawn, spawnSync } = require('child_process');

const STREAM_URL = 'https://kick.com/djmariio';
const DURATION = 6 * 60; // 6 minutos
const INJECT_COUNT = 500;
const LOG_FILE = path.join(__dirname, 'evidence_log.csv');
const INTERVAL = 30; // segundos

const INFO_DETAIL = `\nFuente de datos:\n- Real Viewers (API): https://kick.com/api/v1/channels/<canal> (livestream.viewers)\n- Inyección viewers: node kick-websocket.js <url> <viewers>\n- WebSocket: wss://websockets.kick.com/viewer/v1/connect?token=<token>\n- Herramienta: kick-websocket.js (Node.js)\n`;

function getTimestamp() {
    const d = new Date();
    return d.toISOString().replace('T', ' ').replace(/\..+/, '');
}

function fetchRealViewers(streamName) {
    const apiUrl = `https://kick.com/api/v1/channels/${streamName}`;
    const pyScript = `import json\nfrom curl_cffi import requests as r\nres = r.get(\"${apiUrl}\", headers={\"User-Agent\":\"Mozilla/5.0\",\"Accept\":\"application/json\"}, timeout=15, impersonate=\"chrome131\")\nprint(res.json().get(\"livestream\",{}).get(\"viewers\",0) if res.status_code==200 else -1)`;
    const tmpPath = path.join(require('os').tmpdir(), '_evidence_viewers.py');
    fs.writeFileSync(tmpPath, pyScript);
    const result = spawnSync('python3', [tmpPath], { encoding: 'utf8', timeout: 15000 });
    try { fs.unlinkSync(tmpPath); } catch (_) {}
    return parseInt(result.stdout.trim()) || 0;
}

if (!fs.existsSync(LOG_FILE)) {
    fs.writeFileSync(LOG_FILE, 'Timestamp,Hour,Real Viewers (API),Fake Viewers Injected,Comparativo (Reflejado),Observaciones\n');
}

const streamName = STREAM_URL.replace(/\/$/, '').split('/').pop();

console.log(INFO_DETAIL);
console.log('Iniciando inyección de viewers reales y fake...');
console.log('Canal:', STREAM_URL);
console.log('Duración:', DURATION, 'segundos');
console.log('Inyectando:', INJECT_COUNT, 'viewers');
console.log('Log:', LOG_FILE);

// Lanzar el bot real como proceso hijo
const botProcess = spawn('node', ['kick-websocket.js', STREAM_URL, INJECT_COUNT], {
    cwd: __dirname,
    stdio: ['ignore', 'ignore', 'ignore'] // Silenciar salida para no saturar
});

let rows = [];
let minViewers = Infinity, maxViewers = 0, sumViewers = 0, samples = 0;
let comparativos = [];
let startTime = Date.now();

const interval = setInterval(() => {
    const timestamp = getTimestamp();
    const hour = timestamp.split(' ')[1].slice(0,5);
    const realViewers = fetchRealViewers(streamName);
    minViewers = Math.min(minViewers, realViewers);
    maxViewers = Math.max(maxViewers, realViewers);
    sumViewers += realViewers;
    samples++;

    let comparativo = '';
    let observaciones = '';
    // Cada minuto después de 2 minutos, comparar viewers reflejados
    const elapsed = Math.floor((Date.now() - startTime) / 1000);
    if (elapsed >= 120 && elapsed % 60 === 0) {
        comparativo = realViewers;
        comparativos.push({min: elapsed/60, viewers: realViewers});
        observaciones = `Comparativo minuto ${elapsed/60}`;
    }

    const row = [timestamp, hour, realViewers, INJECT_COUNT, comparativo, observaciones].join(',');
    rows.push(row);
    fs.appendFileSync(LOG_FILE, row + '\n');

    // Mostrar tabla en consola
    console.clear();
    console.log(INFO_DETAIL);
    console.log('| Timestamp           | Hour  | Real Viewers (API) | Fake Viewers Injected | Comparativo (Reflejado) | Observaciones         |');
    console.log('|---------------------|-------|--------------------|----------------------|------------------------|-----------------------|');
    rows.slice(-10).forEach(r => {
        const cols = r.split(',');
        console.log(`| ${cols[0]} | ${cols[1].padStart(5)} | ${cols[2].padStart(18)} | ${cols[3].padStart(20)} | ${cols[4].padStart(22)} | ${cols[5].padStart(21)} |`);
    });
}, INTERVAL * 1000);

setTimeout(() => {
    clearInterval(interval);
    botProcess.kill('SIGINT');
    const avgViewers = samples > 0 ? Math.round(sumViewers / samples) : 0;
    console.log('\nResumen:');
    console.log('Min real viewers:', minViewers);
    console.log('Max real viewers:', maxViewers);
    console.log('Avg real viewers:', avgViewers);
    console.log('Comparativos por minuto después de 2 min:');
    comparativos.forEach(c => console.log(`Minuto ${c.min}: ${c.viewers} viewers reflejados`));
    console.log('Evidence log saved to', LOG_FILE);
    // Tabla final
    console.log('\nTabla final:');
    console.log('| Timestamp           | Hour  | Real Viewers (API) | Fake Viewers Injected | Comparativo (Reflejado) | Observaciones         |');
    console.log('|---------------------|-------|--------------------|----------------------|------------------------|-----------------------|');
    rows.forEach(r => {
        const cols = r.split(',');
        console.log(`| ${cols[0]} | ${cols[1].padStart(5)} | ${cols[2].padStart(18)} | ${cols[3].padStart(20)} | ${cols[4].padStart(22)} | ${cols[5].padStart(21)} |`);
    });
    process.exit(0);
}, DURATION * 1000);
