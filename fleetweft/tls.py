"""Mutually authenticated HTTPS, bounded reads, no proxy or redirects."""
import json
import ssl
from urllib.request import build_opener, ProxyHandler, HTTPSHandler, HTTPRedirectHandler, Request
from urllib.error import HTTPError
from .store import require

class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs): return None

class TLS:
    def __init__(self, ca, cert, key):
        self.client=ssl.create_default_context(cafile=str(ca))
        self.client.load_cert_chain(str(cert),str(key))
        self.server=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        self.server.load_cert_chain(str(cert),str(key)); self.server.load_verify_locations(str(ca))
        self.server.verify_mode=ssl.CERT_REQUIRED
        self.client.minimum_version=self.server.minimum_version=ssl.TLSVersion.TLSv1_2
        self.opener=build_opener(ProxyHandler({}), HTTPSHandler(context=self.client), NoRedirect())

    def request(self, origin, path, body=None, binary=False):
        require(origin.startswith('https://') and path.startswith('/') and not path.startswith('//'), 'HTTPS origin required')
        raw=None if body is None else json.dumps(body,allow_nan=False).encode()
        with self.opener.open(Request(origin+path,data=raw,headers={'Content-Type':'application/json'}),timeout=2) as r:
            value=r.read(131073)
            require(len(value)<=131072, 'Response too large')
            return value if binary else json.loads(value)

def peer_name(cert):
    names=[v for rdn in cert.get('subject',()) for k,v in rdn if k=='commonName']
    require(len(names)==1,'Missing unique peer identity')
    return names[0]
