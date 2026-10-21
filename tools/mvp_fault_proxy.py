"""Test-only mTLS forwarder: durably authorize, lose one reply, then gate retries."""
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import json
from pathlib import Path
import time
from fleetweft.tls import TLS

STATE=Path('/var/lib/fleetweft/proxy'); STATE.mkdir(exist_ok=True)
tls=TLS('/etc/fleetweft/ca.crt','/etc/fleetweft/a.crt','/etc/fleetweft/a.key')
# The fixture proxy is the configured controller endpoint for A. Its TLS server
# uses controller identity; its upstream client preserves A's node role.
server_tls=TLS('/etc/fleetweft/ca.crt','/etc/fleetweft/controller.crt','/etc/fleetweft/controller.key')
class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        length=int(self.headers['Content-Length']); assert 0<length<=32768
        body=json.loads(self.rfile.read(length))
        if (STATE/'lost.json').exists() and self.path=='/poll':
            end=time.monotonic()+20
            while not (STATE/'release').exists():
                if time.monotonic()>end: self.send_error(503); return
                time.sleep(.01)
        value=tls.request('https://192.0.2.1:19443',self.path,body)
        if self.path=='/authorize_commit':
            with (STATE/'approvals.jsonl').open('a') as f: f.write(json.dumps(value)+'\n')
            if not (STATE/'lost.json').exists():
                (STATE/'lost.json').write_text(json.dumps(value))
                self.connection.shutdown(2); self.connection.close(); return
        raw=json.dumps(value).encode(); self.send_response(200)
        self.send_header('Content-Length',str(len(raw))); self.end_headers(); self.wfile.write(raw)
    def do_GET(self):
        raw=tls.request('https://192.0.2.1:19443',self.path,binary=True)
        self.send_response(200); self.send_header('Content-Length',str(len(raw))); self.end_headers(); self.wfile.write(raw)
    def log_message(self,*_):pass
class Server(ThreadingHTTPServer):
    daemon_threads=True
    def get_request(self):
        sock,addr=super().get_request();sock.settimeout(2)
        try:return server_tls.server.wrap_socket(sock,server_side=True),addr
        except BaseException:sock.close();raise
Server(('192.0.2.1',19444),Handler).serve_forever()
