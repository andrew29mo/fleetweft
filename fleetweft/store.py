import contextlib
import fcntl
import json
import os
from pathlib import Path
import sqlite3


def require(ok, message):
    if not ok:
        raise ValueError(message)


class Store:
    """One durable snapshot per process; filesystem lock excludes another owner."""
    def __init__(self, root, initial):
        self.root = Path(root)
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.fd = os.open(self.root / 'owner.lock', os.O_CREAT | os.O_RDWR, 0o600)
        try:
            fcntl.flock(self.fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BaseException:
            os.close(self.fd)
            raise
        self.path = self.root / 'state.sqlite'
        with self.db() as db:
            db.execute('CREATE TABLE IF NOT EXISTS snapshot (id INTEGER PRIMARY KEY CHECK(id=1), data TEXT NOT NULL)')
            db.execute('INSERT OR IGNORE INTO snapshot VALUES (1,?)', (json.dumps(initial),))

    @contextlib.contextmanager
    def db(self):
        db = sqlite3.connect(self.path, timeout=2)
        try:
            db.execute('PRAGMA synchronous=FULL')
            with db:
                yield db
        finally:
            db.close()

    def read(self):
        with self.db() as db:
            return json.loads(db.execute('SELECT data FROM snapshot WHERE id=1').fetchone()[0])

    def save(self, state):
        with self.db() as db:
            db.execute('UPDATE snapshot SET data=? WHERE id=1', (json.dumps(state, allow_nan=False),))

    def close(self):
        os.close(self.fd)
