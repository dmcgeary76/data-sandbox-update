"""A tiny stand-in for the Clever login page, portal and an app, for browser tests."""
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

LOGIN = """<html><body><h1>Log in</h1><form method=post action=/login>
<input name=username placeholder=Username><input name=password type=password>
<button type=submit>Log in</button></form></body></html>"""
PORTAL = """<html><body><h1>Portal</h1>
<a href="/lantern-app" target="_blank" aria-label="Lantern">Lantern</a>
<a href="/other-app">Other App</a></body></html>"""
APP = "<html><body><h1>Welcome to Lantern</h1><button>Start</button></body></html>"


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, body, code=200, headers=None):
        self.send_response(code)
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write(body.encode())

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/in/demo":
            return self._send(LOGIN)
        if path == "/portal":
            if "sess=" not in (self.headers.get("Cookie") or ""):
                return self._send("", 302, {"Location": "/in/demo"})
            return self._send(PORTAL)
        if path == "/lantern-app":
            return self._send(APP)
        self._send("not found", 404)

    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0))
        f = parse_qs(self.rfile.read(n).decode())
        u, p = f.get("username", [""])[0], f.get("password", [""])[0]
        if u and u == p:
            return self._send("", 302, {"Location": "/portal", "Set-Cookie": f"sess={u}; Path=/"})
        self._send(LOGIN.replace("<h1>Log in</h1>", "<h1>Log in</h1><p>Bad credentials</p>"), 401)


def serve():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv
