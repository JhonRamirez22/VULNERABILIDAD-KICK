import json
from curl_cffi import requests as r
try:
    res = r.get("https://kick.com/api/v1/channels/tucanal", headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36", "Accept": "application/json"}, timeout=15, impersonate="chrome131")
    print(res.status_code)
    print(res.text[:100])
except Exception as e:
    print("ERR", str(e))
