"""stdlib 만으로 Chrome DevTools Protocol — 캔버스 상호작용을 헤드리스 크롬에서 진짜 입력으로 시험한다 (websocket 라이브러리 없이).

PORT 는 다른 세션의 크롬(9333)과 겹치지 않게 9444. CHROME 은 이 맥의 크롬; 없으면 YONE_VIV_BROWSER.
"""
import base64, json, os, socket, struct, subprocess, sys, time, urllib.parse, urllib.request

CHROME = os.environ.get("YONE_VIV_BROWSER") or "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
PORT = 9444


def ws_connect(url):
    _, rest = url.split("://", 1); host, path = rest.split("/", 1); host, port = host.split(":")
    s = socket.create_connection((host, int(port))); key = base64.b64encode(os.urandom(16)).decode()
    s.send((f"GET /{path} HTTP/1.1\r\nHost: {host}:{port}\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n").encode())
    buf = b""
    while b"\r\n\r\n" not in buf:
        buf += s.recv(4096)
    return s


def ws_send(s, text):
    data = text.encode(); n = len(data); mask = os.urandom(4)
    hdr = bytes([0x81]) + (bytes([0x80 | n]) if n < 126 else (bytes([0x80 | 126]) + struct.pack(">H", n) if n < 65536 else bytes([0x80 | 127]) + struct.pack(">Q", n)))
    s.send(hdr + mask + bytes(b ^ mask[i % 4] for i, b in enumerate(data)))


def _recvn(s, n):
    b = b""
    while len(b) < n:
        c = s.recv(n - len(b))
        if not c:
            raise ConnectionError
        b += c
    return b


def ws_recv(s):
    h = _recvn(s, 2); n = h[1] & 0x7F
    if n == 126:
        n = struct.unpack(">H", _recvn(s, 2))[0]
    elif n == 127:
        n = struct.unpack(">Q", _recvn(s, 8))[0]
    return _recvn(s, n).decode("utf-8", "replace")


class CDP:
    def __init__(self, url):
        self.s = ws_connect(url); self.i = 0

    def call(self, method, **params):
        self.i += 1; ws_send(self.s, json.dumps({"id": self.i, "method": method, "params": params}))
        while True:
            m = json.loads(ws_recv(self.s))
            if m.get("id") == self.i:
                return m.get("result", m)

    def js(self, expr):
        r = self.call("Runtime.evaluate", expression=expr, awaitPromise=True, returnByValue=True)
        if "exceptionDetails" in r:
            raise RuntimeError(r["exceptionDetails"].get("exception", {}).get("description") or r["exceptionDetails"])
        return r.get("result", {}).get("value")


def main(url, script_path):
    proc = subprocess.Popen([CHROME, "--headless=new", "--disable-gpu", f"--remote-debugging-port={PORT}", "--window-size=1600,1000", "--user-data-dir=/tmp/cdp-prof", "about:blank"],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(50):
            try:
                urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json/version"); break
            except Exception:
                time.sleep(0.2)
        req = urllib.request.Request(f"http://127.0.0.1:{PORT}/json/new?{urllib.parse.quote(url, safe='')}", method="PUT")
        tab = json.load(urllib.request.urlopen(req))
        c = CDP(tab["webSocketDebuggerUrl"])
        time.sleep(2.5)
        for _ in range(40):
            if c.js("!!(document.querySelector('#svgwrap svg') && window.page)"):
                break
            time.sleep(0.25)
        steps = json.load(open(script_path, encoding="utf-8"))
        ok = True
        for name, expr in steps:
            try:
                v = c.js(expr)
                print(("PASS" if v is True or v is None or v else "FAIL"), name, "" if v in (True, None) else v)
                if v is False:
                    ok = False
            except Exception as e:
                ok = False; print("ERR ", name, str(e)[:300])
        return ok
    finally:
        proc.terminate()


if __name__ == "__main__":
    sys.exit(0 if main(sys.argv[1], sys.argv[2]) else 1)
