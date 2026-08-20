import http.server, socketserver, json, urllib.request, ssl, threading, time, sys
UPSTREAM = sys.argv[1] if len(sys.argv) > 1 else "https://mainnet.gateway.tenderly.co"
PORT = 9999
ctx = ssl.create_default_context(cafile="/root/.ccr/ca-bundle.crt")
cache = {}
lock = threading.Lock()
last = [0.0]
MINGAP = 0.30  # ~3.3 req/s to stay under rate limits

def upstream_call(body_bytes, key=None):
    if key is not None:
        with lock:
            if key in cache:
                return cache[key]
    for attempt in range(8):
        with lock:
            dt = time.time() - last[0]
            if dt < MINGAP:
                time.sleep(MINGAP - dt)
            last[0] = time.time()
        try:
            req = urllib.request.Request(UPSTREAM, data=body_bytes,
                                         headers={"Content-Type": "application/json", "User-Agent": "curl/8"})
            raw = urllib.request.urlopen(req, timeout=40, context=ctx).read()
            j = json.loads(raw)  # raises on 1015 html
            if isinstance(j, dict) and isinstance(j.get('error'), dict) and j['error'].get('code') in (-32005, 429, 1015, -32097):
                time.sleep(0.8 * (attempt + 1)); continue
            if key is not None and isinstance(j, dict) and 'result' in j:
                with lock:
                    cache[key] = raw
            return raw
        except Exception:
            time.sleep(0.7 * (attempt + 1))
    return json.dumps({"jsonrpc": "2.0", "id": 1, "error": {"code": -32000, "message": "forwarder upstream fail"}}).encode()

def cache_key(m):
    try:
        method = m.get('method'); p = m.get('params', [])
        # cache immutable pinned reads (skip 'latest' so ganache can pin a fixed fork block)
        if method in ("eth_chainId", "net_version", "eth_getCode", "eth_getBlockByNumber",
                      "eth_getBlockByHash", "eth_getStorageAt", "eth_getBalance",
                      "eth_getTransactionCount", "eth_call", "eth_getProof"):
            s = json.dumps(p, sort_keys=True)
            if "latest" in s:
                return None
            return method + "|" + s
    except Exception:
        pass
    return None

class H(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass
    def do_POST(self):
        n = int(self.headers.get('Content-Length', 0)); data = self.rfile.read(n)
        try:
            m = json.loads(data)
        except Exception:
            m = None
        key = cache_key(m) if isinstance(m, dict) else None
        resp = upstream_call(data, key)
        self.send_response(200); self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(resp))); self.end_headers()
        try:
            self.wfile.write(resp)
        except Exception:
            pass

class TS(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True

if __name__ == "__main__":
    print(f"forwarder(single) -> {UPSTREAM} on :{PORT}", flush=True)
    TS(("127.0.0.1", PORT), H).serve_forever()
