import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import signal
import threading
from urllib.parse import urlparse, parse_qs
from .core import Controller
from .node import Node


def main():
    p = argparse.ArgumentParser(); p.add_argument('role', choices=('controller', 'node'))
    p.add_argument('--state', required=True); p.add_argument('--port', type=int, required=True)
    p.add_argument('--listen', default='127.0.0.1'); p.add_argument('--node', default='a')
    p.add_argument('--samples', type=int, default=3); p.add_argument('--window', type=float, default=.05)
    p.add_argument('--controller', default='http://127.0.0.1:19081')
    a = p.parse_args()
    core = Controller(a.state, a.samples, a.window) if a.role == 'controller' else Node(a.state, a.node, a.controller)
    class Handler(BaseHTTPRequestHandler):
        def handle_request(self, body):
            parsed = urlparse(self.path)
            try:
                if parsed.path == '/work' and a.role == 'node':
                    q = parse_qs(parsed.query)
                    value = core.work(int(q.get('x', ['7'])[0]), q.get('challenge', [''])[0])
                else:
                    value = core.call(parsed.path.lstrip('/'), body)
                code = 200
            except (ValueError, KeyError, TypeError) as exc:
                value = {'error': str(exc)}; code = 409
            except Exception as exc:
                value = {'error': type(exc).__name__}; code = 503
            raw = json.dumps(value).encode(); self.send_response(code)
            self.send_header('Content-Type', 'application/json'); self.send_header('Content-Length', str(len(raw)))
            self.end_headers(); self.wfile.write(raw)
        def do_GET(self): self.handle_request({})
        def do_POST(self):
            try:
                length = int(self.headers.get('Content-Length', '0'))
                if not 0 < length <= 16384: raise ValueError('Invalid body size')
                self.connection.settimeout(2)
                body = json.loads(self.rfile.read(length))
            except Exception:
                self.send_error(400); return
            self.handle_request(body)
        def log_message(self, *args): pass
    server = ThreadingHTTPServer((a.listen, a.port), Handler); server.daemon_threads = True
    def stop(*_): threading.Thread(target=server.shutdown, daemon=True).start()
    signal.signal(signal.SIGTERM, stop)
    print(json.dumps({'ready': a.role, 'port': server.server_port}), flush=True)
    try: server.serve_forever()
    finally:
        server.server_close()
        if a.role == 'node': core.close()
        else: core.store.close()


if __name__ == '__main__': main()
