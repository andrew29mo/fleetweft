"""Fixed stateless HTTP application for coordination experiments, not arbitrary payloads."""
import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from urllib.parse import urlparse, parse_qs


def main():
    p = argparse.ArgumentParser(); p.add_argument('release'); p.add_argument('instance'); a = p.parse_args()
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            q = parse_qs(urlparse(self.path).query)
            x = int(q.get('x', ['7'])[0]); challenge = q.get('challenge', [''])[0]
            value = {'release': a.release, 'worker': a.instance, 'challenge': challenge,
                     'result': x * (3 if a.release == 'bad' else 2), 'healthy': True}
            raw = json.dumps(value).encode(); self.send_response(200)
            self.send_header('Content-Length', str(len(raw))); self.end_headers(); self.wfile.write(raw)
        def log_message(self, *args): pass
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    print(json.dumps({'port': server.server_port}), flush=True)
    server.serve_forever()


if __name__ == '__main__': main()
