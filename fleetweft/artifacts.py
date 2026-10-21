"""Bounded, signed single-file application bundles. This is not a TUF client."""
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import zipfile
from .store import require

LIMIT = 131072

def read_bounded(path, limit):
    with Path(path).open('rb') as stream:
        require(os.fstat(stream.fileno()).st_size<=limit, 'Oversized artifact file')
        raw=stream.read(limit+1)
    require(len(raw)<=limit, 'Oversized artifact file')
    return raw

def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()

def digest(raw):
    return hashlib.sha256(raw).hexdigest()

def build(app, release, key, platform='linux-aarch64'):
    require(release.isalnum() and len(release) <= 32, 'Invalid release')
    manifest = canonical(dict(schema=1, release=release, platform=platform,
                              payload_sha256=digest(app), payload_bytes=len(app)))
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp); (p/'manifest').write_bytes(manifest)
        signature = subprocess.run(['openssl','dgst','-sha256','-sign',str(key),str(p/'manifest')],
                                   check=True, capture_output=True, timeout=5).stdout
    out = io.BytesIO()
    with zipfile.ZipFile(out, 'w', compression=zipfile.ZIP_STORED) as z:
        for name, data in [('manifest.json',manifest),('manifest.sig',signature),('app.py',app)]:
            z.writestr(name, data)
    require(len(out.getvalue()) <= LIMIT, 'Bundle too large')
    return out.getvalue()

class Artifacts:
    def __init__(self, root, public_key, catalog, platform='linux-aarch64', quota=1048576):
        self.root = Path(root); self.root.mkdir(parents=True, exist_ok=True)
        self.key, self.catalog, self.platform, self.quota = str(public_key), dict(catalog), platform, quota
        require(all(isinstance(v,str) and len(v)==64 and set(v)<=set('0123456789abcdef')
                    for v in self.catalog.values()), 'Invalid catalog digest')

    def verify(self, raw, release):
        require(release in self.catalog and len(raw) <= LIMIT and digest(raw)==self.catalog[release], 'Bundle digest mismatch')
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            infos = z.infolist()
            require(len(infos)==3 and {i.filename for i in infos}=={'manifest.json','manifest.sig','app.py'}, 'Unsafe bundle entries')
            require(all(i.compress_type==zipfile.ZIP_STORED and not i.is_dir() and i.file_size<=65536
                        and (i.external_attr>>16)&0o170000 not in (0o120000,) for i in infos), 'Unsafe bundle size/type')
            manifest = z.read('manifest.json'); signature = z.read('manifest.sig'); app=z.read('app.py')
        require(len(manifest)<=4096 and len(signature)<=1024, 'Oversized metadata')
        m=json.loads(manifest)
        require(set(m)=={'schema','release','platform','payload_sha256','payload_bytes'} and
                type(m['schema']) is int and m['schema']==1 and m['release']==release and
                m['platform']==self.platform and type(m['payload_bytes']) is int and
                m['payload_bytes']==len(app) and m['payload_sha256']==digest(app) and canonical(m)==manifest,
                'Invalid manifest')
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp); (p/'manifest').write_bytes(manifest); (p/'sig').write_bytes(signature)
            r=subprocess.run(['openssl','dgst','-sha256','-verify',self.key,'-signature',str(p/'sig'),str(p/'manifest')],
                             capture_output=True, timeout=5)
            require(r.returncode==0, 'Invalid artifact signature')
        compile(app, '<signed app>', 'exec')
        return app

    def install(self, raw, release):
        app=self.verify(raw, release); target=self.root/self.catalog[release]
        if target.exists():
            self.path(release); return
        used=sum(p.stat().st_size for p in self.root.rglob('*') if p.is_file())
        require(used+len(raw)+len(app)<=self.quota, 'Artifact quota exceeded')
        tmp=Path(tempfile.mkdtemp(prefix='.stage-', dir=self.root))
        try:
            for name, value in [('bundle.zip',raw),('app.py',app)]:
                with (tmp/name).open('wb') as f: f.write(value); f.flush(); os.fsync(f.fileno())
                (tmp/name).chmod(0o400)
            self._sync(tmp); os.rename(tmp,target); self._sync(self.root)
        finally:
            if tmp.exists(): shutil.rmtree(tmp)

    @staticmethod
    def _sync(path):
        fd=os.open(path,os.O_RDONLY)
        try: os.fsync(fd)
        finally: os.close(fd)

    def path(self, release):
        target=self.root/self.catalog[release]
        app=self.verify(read_bounded(target/'bundle.zip',LIMIT),release)
        require(read_bounded(target/'app.py',65536)==app,'Cached payload changed')
        return target/'app.py'
