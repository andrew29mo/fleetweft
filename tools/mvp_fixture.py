"""Ephemeral test credentials and real signed sample apps; never commit keys."""
import json
from pathlib import Path
import subprocess
from fleetweft.artifacts import build,digest

def cmd(*args): return subprocess.run(args,check=True,capture_output=True,text=True,timeout=15).stdout

def credentials(root, addresses):
    root=Path(root); root.mkdir(parents=True,exist_ok=True)
    cmd('openssl','req','-x509','-newkey','rsa:2048','-nodes','-days','2','-keyout',str(root/'ca.key'),
        '-out',str(root/'ca.crt'),'-subj','/CN=ephemeral-fleetweft-test-ca')
    for name,ip in addresses.items():
        cmd('openssl','req','-newkey','rsa:2048','-nodes','-keyout',str(root/(name+'.key')),
            '-out',str(root/(name+'.csr')),'-subj','/CN='+name)
        ext=root/(name+'.ext'); ext.write_text('subjectAltName=IP:'+ip+'\nextendedKeyUsage=serverAuth,clientAuth\n')
        cmd('openssl','x509','-req','-in',str(root/(name+'.csr')),'-CA',str(root/'ca.crt'),'-CAkey',str(root/'ca.key'),
            '-CAcreateserial','-days','2','-out',str(root/(name+'.crt')),'-extfile',str(ext))
    cmd('openssl','genrsa','-out',str(root/'sign.key'),'2048')
    cmd('openssl','rsa','-in',str(root/'sign.key'),'-pubout','-out',str(root/'sign.pub'))

def bundles(root, signing_key):
    root=Path(root); root.mkdir(parents=True,exist_ok=True)
    app=Path(__file__).resolve().parents[1]/'fleetweft/worker.py'
    source=app.read_bytes().replace(b'import argparse',b'import argparse\nimport os')
    source=source.replace(b"a.release == 'bad'",b"(a.release == 'bad' or (a.release == 'badb' and os.environ.get('FLEETWEFT_NODE')=='b'))")
    catalog={}
    for release in ('v1','v2','v3','bad','badb','crash'):
        raw=build(b'raise RuntimeError("startup failure fixture")\n' if release=='crash' else source,release,signing_key); sha=digest(raw); catalog[release]=sha
        (root/(sha+'.zip')).write_bytes(raw)
    return catalog
