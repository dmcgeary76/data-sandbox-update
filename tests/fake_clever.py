"""A small stand-in for Clever's login flow, portal and an app, for browser tests.

Mirrors the real flow: a login-method chooser (Badge / Password), a username step
with a Next button that stays disabled until the field registers input, then a
password step, then the portal. The tiles open new tabs: one to a working app, one
to an OAuth callback on a port where nothing listens (like a localhost dev app).
"""
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

CHOOSER = """<html><body><h1>Log in with Clever</h1>
<div id=choose><div onclick="go()" style="cursor:pointer">Badge</div>
<div onclick="go()" style="cursor:pointer">Password</div></div>
<form id=f method=post action=/login-username style="display:none">
<input id=username name=username type=text autocomplete=username>
<button type=submit id=next disabled>Next</button></form>
<script>
function go(){document.getElementById('choose').style.display='none';
  // the field only starts listening a moment later, like a hydrating React app
  setTimeout(()=>{document.getElementById('f').style.display='block';
    setTimeout(()=>{document.getElementById('username').addEventListener('input',
      e=>{document.getElementById('next').disabled=!e.target.value;});},300);},200);}
</script></body></html>"""
PASSWORD = """<html><body><form method=post action=/login>
<input type=hidden name=username value="{u}"><input name=password type=password>
<button type=submit>Log in</button></form></body></html>"""
PORTAL = """<html><body><h1>Portal</h1>
<a href="/lantern-app" target="_blank" aria-label="Lantern">Lantern</a>
<a href="http://127.0.0.1:9/api/auth/callback?code=abc123" target="_blank">Lantern Learn - DEMO App</a>
<a href="/api/auth/callback?code=xyz" target="_blank">Strict App</a>
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
            return self._send(CHOOSER)
        if path in ("/in/demo/student/portal", "/in/demo/teacher"):
            if "sess=" not in (self.headers.get("Cookie") or ""):
                return self._send("", 302, {"Location": "/in/demo"})
            return self._send(PORTAL)
        if path == "/lantern-app":
            return self._send(APP)
        if path == "/api/auth/callback":  # accepts the code, then has no matching account
            return self._send("", 302, {"Location": "/login/error?reason=no_match"})
        if path == "/login/error":
            return self._send("<h1>We couldn't sign you in</h1>")
        self._send("not found", 404)

    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0))
        f = parse_qs(self.rfile.read(n).decode())
        u, p = f.get("username", [""])[0], f.get("password", [""])[0]
        if self.path == "/login-username":
            return self._send(PASSWORD.format(u=u))
        if u and u == p:
            dest = "/in/demo/teacher" if u.startswith("7") else "/in/demo/student/portal"
            return self._send("", 302, {"Location": dest, "Set-Cookie": f"sess={u}; Path=/"})
        self._send("<p>Bad credentials</p>", 401)


def serve():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv
