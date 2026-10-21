"""Production-path MVP entry point; legacy HTTP exploration is separate."""
import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import secrets
import signal
import threading
from urllib.parse import parse_qs,urlparse
from .agent import Agent
from .artifacts import Artifacts,build,read_bounded
from .coordinator import Coordinator
from .store import Store,require
from .tls import TLS,peer_name

def provision(config):
    root=Path(config['state']); require(not (root/'state.sqlite').exists(),'State already provisioned')
    s=Store(root,dict(committed='v1',generation=0,accepted=None,phase='IDLE',children=[],revision=0,
                      node_uuid=secrets.token_hex(16),boot_sequence=0))
    identity=s.read()['node_uuid']; s.close(); return identity

def artifacts(config):
    return Artifacts(config['cache'],config['signing_public_key'],config['catalog'],
                     config.get('platform','linux-aarch64'),config.get('cache_quota',1048576))

def run(config):
    tls=TLS(config['ca'],config['cert'],config['key']); role=config['role']
    if role=='controller':
        require((Path(config['state'])/'state.sqlite').is_file(),'Explicit controller provisioning required')
        core=Coordinator(config['state'],config['catalog'],config.get('samples',3),config.get('window',.1))
    else: core=Agent(config['state'],config['node'],config['controller'],artifacts(config),tls)
    class Handler(BaseHTTPRequestHandler):
        def dispatch(self,body):
            try:
                peer=peer_name(self.connection.getpeercert()); path=urlparse(self.path).path
                if role=='controller':
                    if path.startswith('/artifacts/'):
                        require(peer in core.store.read()['registry'],'Enrolled node required')
                        sha=path.split('/')[-1]; require(sha in config['catalog'].values(),'Unknown artifact')
                        raw=read_bounded(Path(config['bundles'])/(sha+'.zip'),131072)
                        require(len(raw)<=131072,'Oversized artifact'); return self.reply(200,raw,'application/zip')
                    result=core.call(path.lstrip('/'),body,peer)
                else:
                    require(peer in ('operator','controller'),'Operator identity required')
                    require(path in ('/status','/work'),'Read-only node API')
                    if path=='/status': result={**core.snapshot(),'last_error':core.last_error}
                    else:
                        q=parse_qs(urlparse(self.path).query)
                        result=core.work(int(q.get('x',['7'])[0]),q.get('challenge',[''])[0],int(q.get('delay_ms',['0'])[0]))
                self.reply(200,json.dumps(result,allow_nan=False).encode())
            except (ValueError,KeyError,TypeError): self.reply(409,b'{"error":"protocol rejection"}')
            except Exception: self.reply(503,b'{"error":"execution failure"}')
        def reply(self,code,raw,kind='application/json'):
            self.send_response(code); self.send_header('Content-Type',kind)
            self.send_header('Content-Length',str(len(raw))); self.end_headers(); self.wfile.write(raw)
        def do_GET(self): self.dispatch({})
        def do_POST(self):
            try:
                n=int(self.headers.get('Content-Length','0')); require(0<n<=32768,'Invalid body size')
                self.connection.settimeout(2); raw=self.rfile.read(n); require(len(raw)==n,'Incomplete body')
                body=json.loads(raw); require(type(body) is dict,'Object required')
            except Exception: self.reply(400,b'{}'); return
            self.dispatch(body)
        def log_message(self,*args): pass
    class Server(ThreadingHTTPServer):
        daemon_threads=True
        def get_request(self):
            sock,addr=super().get_request(); sock.settimeout(2)
            try: return tls.server.wrap_socket(sock,server_side=True),addr
            except BaseException: sock.close(); raise
    server=Server((config.get('listen','127.0.0.1'),config['port']),Handler)
    if role=='node':
        core.thread=threading.Thread(target=core.run,daemon=True); core.thread.start()
    def stop(*_): threading.Thread(target=server.shutdown,daemon=True).start()
    signal.signal(signal.SIGTERM,stop); signal.signal(signal.SIGINT,stop)
    try: server.serve_forever(poll_interval=.1)
    finally:
        server.server_close()
        if role=='node': core.close()
        else: core.store.close()

def main():
    parser=argparse.ArgumentParser(description='Fleetweft single-platform stateless application rollout')
    sub=parser.add_subparsers(dest='command',required=True)
    for name in ('serve','provision-node','provision-controller'):
        sub.add_parser(name).add_argument('--config',required=True)
    p=sub.add_parser('bundle'); p.add_argument('--app',required=True); p.add_argument('--release',required=True)
    p.add_argument('--key',required=True); p.add_argument('--output',required=True)
    p=sub.add_parser('cache'); p.add_argument('--config',required=True); p.add_argument('--bundle',required=True); p.add_argument('--release',required=True)
    p=sub.add_parser('ctl'); p.add_argument('--config',required=True)
    p.add_argument('action',choices=('status','enroll','deploy','pause','resume','rollback'))
    p.add_argument('--body',default='{}')
    a=parser.parse_args()
    if a.command=='bundle':
        raw=build(Path(a.app).read_bytes(),a.release,a.key); Path(a.output).write_bytes(raw); return
    config=json.loads(Path(a.config).read_text())
    if a.command=='serve': run(config)
    elif a.command=='cache': artifacts(config).install(Path(a.bundle).read_bytes(),a.release)
    elif a.command=='provision-node': print(json.dumps({'node_uuid':provision(config)}))
    elif a.command=='provision-controller':
        require(not (Path(config['state'])/'state.sqlite').exists(),'State already provisioned')
        c=Coordinator(config['state'],config['catalog']); c.store.close()
    else:
        tls=TLS(config['ca'],config['cert'],config['key'])
        print(json.dumps(tls.request(config['controller'],'/'+a.action,json.loads(a.body)),indent=2))

if __name__=='__main__': main()
