"""Pull-only agent: a lost grant/response cannot authorize a successor."""
import threading
import time
from .node import Node
from .store import require

class Agent(Node):
    def __init__(self, root, name, controller, artifacts, tls):
        super().__init__(root,name,controller,artifacts,tls,secure=True)
        self.stopping=threading.Event(); self.sample=None; self.poll_sequence=0; self.last_error=None

    def tick(self):
        report=self.snapshot()
        try: probe=self.work(7,'heartbeat')
        except Exception: probe=None
        self.poll_sequence+=1
        reply=self.tls.request(self.controller,'/poll',dict(node=self.name,sequence=self.poll_sequence,status=report,probe=probe,sample=self.sample))
        command=reply['command']; self.sample=None
        if command=='idle': return
        require(command in ('accept','activate','sample','commit','cancel','refuse'),'Unknown command')
        args={k:v for k,v in reply.items() if k!='command'}
        if command=='accept':
            release=args['token']['release']
            try:
                try: self.artifacts.path(release)
                except FileNotFoundError:
                    raw=self.tls.request(self.controller,'/artifacts/'+self.artifacts.catalog[release],binary=True)
                    self.artifacts.install(raw,release)
            except Exception:
                # No candidate ran. Durable refusal fences this grant before it can
                # be settled as restored; the controller still needs that report.
                self.call('refuse',args); raise
        try: value=self.call(command,args)
        except Exception:
            if command=='activate':
                # Startup/application failures compensate through the same route
                # writer. Failure of compensation retains the grant as unknown.
                self.call('cancel',args)
            raise
        if command=='sample': self.sample=value

    def run(self):
        while not self.stopping.is_set():
            try: self.tick(); self.last_error=None
            except Exception as exc: self.last_error=type(exc).__name__
            self.stopping.wait(.05)

    def close(self):
        self.stopping.set()
        if getattr(self,'thread',None): self.thread.join(timeout=8)
        require(not getattr(self,'thread',None) or not self.thread.is_alive(),'Agent did not stop')
        super().close()
