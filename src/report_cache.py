"""Bounded per-process response cache. It never acquires data from providers."""
from collections import OrderedDict
import hashlib
import json
from threading import Lock
from time import monotonic


class ReportCache:
    def __init__(self, ttl=60, max_entries=32, max_bytes=8 * 1024 * 1024):
        self.ttl = ttl
        self.max_entries = max_entries
        self.max_bytes = max_bytes
        self._entries = OrderedDict()
        self._bytes = 0
        self._revision = None
        self._lock = Lock()

    def get(self, key, revision, build):
        # Concurrent visitors share the calculation instead of starting duplicates.
        with self._lock:
            if revision != self._revision:
                self._entries.clear()
                self._bytes = 0
                self._revision = revision
            now = monotonic()
            for stale in [k for k, (expires, _, _) in self._entries.items() if expires <= now]:
                self._bytes -= len(self._entries.pop(stale)[1])
            if key in self._entries:
                self._entries.move_to_end(key)
                _, body, etag = self._entries[key]
                return body, etag, True
            body = json.dumps(build(), ensure_ascii=False, allow_nan=False,
                              separators=(",", ":")).encode("utf-8")
            etag = '"' + hashlib.sha256(body).hexdigest() + '"'
            if self.max_entries > 0 and len(body) <= self.max_bytes:
                while self._entries and (len(self._entries) >= self.max_entries or
                                         self._bytes + len(body) > self.max_bytes):
                    self._bytes -= len(self._entries.popitem(last=False)[1][1])
                self._entries[key] = (monotonic() + self.ttl, body, etag)
                self._bytes += len(body)
            return body, etag, False
