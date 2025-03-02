import pathlib
import os
import sqlite3
import zlib

TABLES_SCHEMA="""
CREATE TABLE IF NOT EXISTS meta(key TEXT, value BLOB);
CREATE UNIQUE INDEX IF NOT EXISTS meta_key ON meta (key);

CREATE TABLE IF NOT EXISTS files(path TEXT, crc INTEGER, updated INTEGER);
CREATE UNIQUE INDEX IF NOT EXISTS files_path ON files (path);
"""

def fcrc32(fpath):
    """With for loop and buffer."""
    crc = 0
    with open(fpath, 'rb', 65536) as ins:
        for x in range(int((os.stat(fpath).st_size / 65536)) + 1):
            crc = zlib.crc32(ins.read(65536), crc)
    return (crc & 0xFFFFFFFF)

class FileDB:
    _conn: sqlite3.Connection
    def __init__(self) -> None:
        self._conn = sqlite3.connect("updatedata.db")
        self._populate_tables()
    def _populate_tables(self):
        self._conn.executescript(TABLES_SCHEMA)
    def get_meta(self, key, default=None):
        cur = self._conn.execute("SELECT value FROM meta WHERE key = ? LIMIT 1", (key,))
        result = cur.fetchall()
        cur.close()
        if len(result) == 0:
            return default
        return result[0][0]
    def set_meta(self, key, value):
        self._conn.execute("INSERT INTO meta VALUES(?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, value,)).close()
        self._conn.commit()
    def get_file(self, path):
        cur = self._conn.execute("SELECT * FROM files WHERE path = ? LIMIT 1", (path,))
        result = cur.fetchall()
        cur.close()
        if len(result) == 0:
            return None
        return result[0]
    def get_tracked_files(self):
        cur = self._conn.execute("SELECT * FROM files")
        files = cur.fetchall()
        cur.close()
        return files
    def index_files(self):
        files = self.get_tracked_files()
        modified, removed = [], []
        cur = self._conn.cursor()
        root = pathlib.Path(os.curdir)
        for f in files:
            spath, crc, updated = f
            path = root / spath
            if not path.exists():
                removed.append(path)
                continue
            pmtime = os.path.getmtime(path)
            if pmtime == float(updated):
                # last modification date not changed, assuming file contents weren't either
                continue
            ncrc = fcrc32(path)
            if ncrc != crc:
                modified.append(path)
                cur.execute("UPDATE files SET crc = ?, updated = ? WHERE path = ?", (ncrc, pmtime, spath)).close()
                continue
        cur.close()
        return files, modified, removed
    def track_file(self, relpath, crc, updated):
        cur = self._conn.execute("INSERT INTO files VALUES(?, ?, ?)", (relpath, crc, updated))
        self._conn.commit()
        cur.close()
    def update_tracked_file(self, relpath, crc, updated):
        cur = self._conn.execute("UPDATE files SET crc = ?, updated = ? WHERE path = ?", (crc, updated, relpath))
        self._conn.commit()
        cur.close()
    def clear_tracked_files(self):
        cur = self._conn.execute("DELETE FROM files")
        self._conn.commit()
        cur.close()