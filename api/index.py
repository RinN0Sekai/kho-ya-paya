"""
Vercel Python serverless entry point for Kho-Ya-Paya.

Vercel's @vercel/python runtime uses a `handler` subclassing BaseHTTPRequestHandler —
which is exactly what the app's server already is. We just put the data dirs on sys.path,
seed the two node replicas into /tmp on cold start, and expose the existing handler.

CAVEAT: Vercel is serverless/stateless. The seeded matching data, map, reachability,
hotspots and name-check all work per request. But mutable demo state (records added via
Load demo, the online/offline toggle, courier sync) lives in module memory and resets on
cold starts / across instances. For the full offline + partition demo, run it as a process
(locally, or on Render/Railway/Fly via the Procfile) — that is the app's real deploy target.
"""
import os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "kho-ya-paya"))
sys.path.insert(0, os.path.join(ROOT, "setu"))

import server  # noqa: E402

if not server.NODES:                 # seed once per cold start; /tmp is the only writable dir
    server.boot(dbdir="/tmp")

handler = server.H                   # Vercel invokes this BaseHTTPRequestHandler
