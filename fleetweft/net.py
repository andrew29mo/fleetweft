import json
import urllib.request


def request(url, path, body=None, timeout=2):
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(url + path, data=data, headers={'Content-Type': 'application/json'})
    # Isolation experiments use literal IPs; never inherit a proxy configuration.
    with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(req, timeout=timeout) as r:
        raw = r.read(65537)
        if len(raw) > 65536:
            raise ValueError('Oversize response')
        return json.loads(raw)
