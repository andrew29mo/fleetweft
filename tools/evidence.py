import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


def manifest(root=ROOT):
    paths=[p for d in ('fleetweft','tests','tools') for p in (root/d).rglob('*.py')]
    paths += [root/'pyproject.toml'] + list((root/'deploy').glob('*.service'))
    return {str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(paths)}


def fingerprint(source):return hashlib.sha256(json.dumps(source,sort_keys=True).encode()).hexdigest()
