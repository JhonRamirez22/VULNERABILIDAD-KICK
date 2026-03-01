"""
Obtener la URL HLS del stream y probar si consumir segmentos cuenta como viewer.
"""
import json, time
from curl_cffi import requests as cffi_requests

CHANNEL_SLUG = "jhonramirez22"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"

session = cffi_requests.Session(impersonate="chrome131")

# 1. Obtener playback URL de la API
print("=== Obteniendo playback URL ===")

# API v1
r = session.get(f"https://kick.com/api/v1/channels/{CHANNEL_SLUG}",
    headers={"User-Agent": UA, "Accept": "application/json"},
    timeout=15)
data = r.json()

ls = data.get("livestream", {}) or {}
playback_url = ls.get("playback_url", "")
print(f"playback_url (v1): {playback_url}")

# API v2
r2 = session.get(f"https://kick.com/api/v2/channels/{CHANNEL_SLUG}",
    headers={"User-Agent": UA, "Accept": "application/json"},
    timeout=15)
data2 = r2.json()
ls2 = data2.get("livestream", {}) or {}
playback_url2 = ls2.get("playback_url", "")
print(f"playback_url (v2): {playback_url2}")

# Playback URL endpoint
r3 = session.get(f"https://kick.com/api/v2/channels/{CHANNEL_SLUG}/playback-url",
    headers={"User-Agent": UA, "Accept": "application/json",
             "Referer": f"https://kick.com/{CHANNEL_SLUG}"},
    timeout=15)
print(f"playback-url endpoint status: {r3.status_code}")
if r3.status_code == 200:
    print(f"playback-url data: {r3.text[:500]}")

# 2. Si tenemos playback_url, intentar obtener el manifiesto HLS
url = playback_url or playback_url2
if url:
    print(f"\n=== Descargando manifiesto HLS ===")
    print(f"URL: {url}")
    
    r4 = session.get(url,
        headers={"User-Agent": UA, "Accept": "*/*",
                 "Origin": "https://player.kick.com",
                 "Referer": "https://player.kick.com/"},
        timeout=15)
    print(f"Status: {r4.status_code}")
    print(f"Content-Type: {r4.headers.get('content-type', '?')}")
    print(f"Manifest:\n{r4.text[:2000]}")
    
    # Buscar los variant streams
    import re
    variants = re.findall(r'#EXT-X-STREAM-INF.*\n(.+)', r4.text)
    print(f"\nVariant streams: {variants}")
    
    # Intentar descargar un variant (el de menor calidad)
    if variants:
        # Resolver URL relativa
        base = url.rsplit('/', 1)[0]
        variant_url = variants[-1] if not variants[-1].startswith('http') else variants[-1]
        if not variant_url.startswith('http'):
            variant_url = base + '/' + variant_url
        
        print(f"\n=== Descargando variant stream ===")
        print(f"URL: {variant_url}")
        
        r5 = session.get(variant_url,
            headers={"User-Agent": UA, "Accept": "*/*",
                     "Origin": "https://player.kick.com",
                     "Referer": "https://player.kick.com/"},
            timeout=15)
        print(f"Status: {r5.status_code}")
        print(f"Content:\n{r5.text[:2000]}")
        
        # Obtener segmentos
        segments = re.findall(r'(https?://[^\s]+\.ts[^\s]*|[^\s]+\.ts[^\s]*)', r5.text)
        print(f"\nSegmentos encontrados: {len(segments)}")
        if segments:
            for seg in segments[:3]:
                print(f"  {seg[:150]}")
            
            # Descargar un segmento
            seg_url = segments[0]
            if not seg_url.startswith('http'):
                seg_base = variant_url.rsplit('/', 1)[0]
                seg_url = seg_base + '/' + seg_url
            
            print(f"\n=== Descargando primer segmento ===")
            print(f"URL: {seg_url[:150]}")
            r6 = session.get(seg_url,
                headers={"User-Agent": UA, "Accept": "*/*",
                         "Origin": "https://player.kick.com",
                         "Referer": "https://player.kick.com/"},
                timeout=15)
            print(f"Status: {r6.status_code}")
            print(f"Content-Type: {r6.headers.get('content-type', '?')}")
            print(f"Size: {len(r6.content)} bytes")
            
            # Verificar conteo después de consumir segmentos
            print("\n=== Consumiendo segmentos por 30s ===")
            viewers_before = 0
            rv = session.get(f"https://kick.com/api/v2/channels/{CHANNEL_SLUG}",
                headers={"User-Agent": UA, "Accept": "application/json"},
                timeout=15)
            if rv.status_code == 200:
                viewers_before = (rv.json().get("livestream") or {}).get("viewers", 0)
            print(f"Viewers antes: {viewers_before}")
            
            for i in range(6):
                # Re-descargar playlist para obtener nuevos segmentos
                r_pl = session.get(variant_url,
                    headers={"User-Agent": UA, "Accept": "*/*",
                             "Origin": "https://player.kick.com"},
                    timeout=10)
                new_segs = re.findall(r'(https?://[^\s]+\.ts[^\s]*|[^\s]+\.ts[^\s]*)', r_pl.text)
                if new_segs:
                    seg = new_segs[-1]
                    if not seg.startswith('http'):
                        seg = variant_url.rsplit('/', 1)[0] + '/' + seg
                    r_s = session.get(seg,
                        headers={"User-Agent": UA, "Accept": "*/*",
                                 "Origin": "https://player.kick.com"},
                        timeout=10)
                    print(f"  [{(i+1)*5}s] Segmento descargado: {r_s.status_code} ({len(r_s.content)} bytes)")
                
                time.sleep(5)
                rv = session.get(f"https://kick.com/api/v2/channels/{CHANNEL_SLUG}",
                    headers={"User-Agent": UA, "Accept": "application/json"},
                    timeout=15)
                viewers_now = (rv.json().get("livestream") or {}).get("viewers", 0) if rv.status_code == 200 else -1
                diff = viewers_now - viewers_before
                print(f"  [{(i+1)*5}s] Viewers: {viewers_now} ({'+' if diff > 0 else ''}{diff})")
else:
    print("\n❌ No playback URL found!")
    
    # Buscar en los datos del canal
    print("\nBuscando en datos del canal...")
    for key in ['playback_url', 'stream_url', 'hls_url', 'video_url', 'source']:
        for d in [data, ls, data2, ls2]:
            if key in d:
                print(f"  {key}: {d[key]}")
