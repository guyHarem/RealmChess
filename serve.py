"""
Run the game for real visitors: one program serving the built pages and the API.

    npm --prefix realmchess-frontend run build     # once, and after every change to the pages
    venv/bin/python serve.py                       # then open http://localhost:8000

Settings (environment variables):
    PORT                    port to listen on (default 8000)
    HOST                    address to listen on (default 0.0.0.0: reachable from other machines)
    REALMCHESS_THINKERS      computer moves thought about at the same time, one CPU core each
                            (default: the number of cores minus one, at most 4)
    REALMCHESS_TRUST_PROXY   how many proxies stand in front of this server (default 1; 0 for
                            none). The visitor's address is read that many entries from the
                            end of X-Forwarded-For. Check it at /api/health, which shows the
                            address the server takes you for

    REALMCHESS_HANDOFF_KEY   a shared secret that lets a stopping server hand its games to the
                            one replacing it (see api/handoff.py); without it they are lost
    REALMCHESS_HANDOFF_URL   where to hand them (default RENDER_EXTERNAL_URL, set by Render)

The server is a single process on purpose: games live in its memory, so two processes would
each have their own set. On a deploy they are handed to the new server; a crash ends them.
"""
import os
import signal

os.environ["REALMCHESS_ENV"] = "production"   # must be set before api.app is imported


def start(host, port, thinkers=None):
    """Serve pages and API until the program is told to stop"""
    from waitress import serve

    from api import handoff
    from api.app import app, rooms
    from api.thinker import ProcessThinker, default_workers

    workers = thinkers or default_workers()
    thinker = ProcessThinker(workers=workers)
    rooms.set_thinker(thinker)
    thinker.warm_up()

    def stop(*_):
        # A deploy: the new server already has the visitors; give it the games (api/handoff.py)
        try:
            handoff.send(rooms)
        except Exception as e:   # never let a failed handover keep the server from stopping
            print(f"handoff: {e}", flush=True)
        raise SystemExit(0)
    signal.signal(signal.SIGTERM, stop)   # how a host stops the server; waitress then winds down

    print(f"Serving on http://{host}:{port} with {workers} computer thinker(s)", flush=True)
    try:
        # Plenty of threads: a computer move holds one for seconds while the pages keep asking
        # for news. Waitress would strip X-Forwarded-For as coming from an unknown proxy;
        # api.app needs it to tell visitors apart, and decides itself how far to trust it.
        serve(app, host=host, port=port, threads=32, ident=None, clear_untrusted_proxy_headers=False)
    finally:
        thinker.close()


if __name__ == "__main__":
    from api.app import app

    if not os.path.isfile(os.path.join(app.config["DIST"], "index.html")):
        raise SystemExit("The pages are not built yet. Run: npm --prefix realmchess-frontend run build")

    start(os.environ.get("HOST", "0.0.0.0"), int(os.environ.get("PORT", 8000)),
          thinkers=int(os.environ.get("REALMCHESS_THINKERS", 0)))
