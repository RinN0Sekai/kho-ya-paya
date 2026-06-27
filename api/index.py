"""
Vercel Python serverless entry point for Kho-Ya-Paya.

Vercel's @vercel/python runtime detects a top-level `handler` subclassing
BaseHTTPRequestHandler at BUILD time, so we must NOT do heavy imports / data loading at
module import. Instead `handler` is a thin shell: on the first request it lazily imports
the real app (server.H, which loads the engine + seeds the two node replicas into /tmp),
rebinds itself to that class, and re-dispatches. Subsequent requests reuse the warm app.

CAVEAT: Vercel is serverless/stateless. Search, map, reachability, hotspots and the
name-check work per request. Mutable demo state (records added via Load demo, the
online/offline toggle, courier sync) lives in module memory and resets on cold starts.
For the full offline + partition demo, run it as a process (locally, or on Render/Railway
via the Procfile) — that is the app's real deploy target.
"""
from http.server import BaseHTTPRequestHandler
import os, sys

_APP = {"H": None}

def _load():
    if _APP["H"] is None:
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        for d in ("kho-ya-paya", "setu"):
            p = os.path.join(root, d)
            if p not in sys.path:
                sys.path.insert(0, p)
        import server
        if not server.NODES:
            server.boot(dbdir="/tmp")          # /tmp is the only writable dir on Vercel
        _APP["H"] = server.H
    return _APP["H"]


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.__class__ = _load()
        self.do_GET()

    def do_POST(self):
        self.__class__ = _load()
        self.do_POST()
