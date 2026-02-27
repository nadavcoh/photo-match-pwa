#!/usr/bin/env python3
"""
photo-match-pwa — Photo Matching PWA · Flask backend
Implements the /match workflow from gphoto-phash-flask as a modern PWA.
"""

import json
import os
import base64
import argparse
import socket
import sys
import signal
import subprocess
import threading
import hmac
import hashlib
import datetime
import functools
from io import BytesIO

from flask import (
    Flask, request, jsonify, render_template, g, send_from_directory, abort
)
from flask_caching import Cache

import psycopg2
import psycopg2.extras

# ─── APP SETUP ────────────────────────────────────────────────────────────────

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET", "photo-match-pwa-secret-key-change-me")

HAMMING_DISTANCE_THRESHOLD = int(os.environ.get("HAMMING_THRESHOLD", "10"))

# ─── CACHING ──────────────────────────────────────────────────────────────────
# Server-side cache: simple in-memory (swap to Redis by changing CACHE_TYPE)
cache_config = {
    "CACHE_TYPE": os.environ.get("CACHE_TYPE", "SimpleCache"),
    "CACHE_DEFAULT_TIMEOUT": int(os.environ.get("CACHE_TIMEOUT", "300")),
}
if cache_config["CACHE_TYPE"] == "RedisCache":
    cache_config["CACHE_REDIS_URL"] = os.environ.get("REDIS_URL", "redis://localhost:6379/0")

cache = Cache(app, config=cache_config)

# ─── VERSION ──────────────────────────────────────────────────────────────────

def get_version():
    """Return short git hash + date, or 'dev' if git unavailable."""
    try:
        app_dir = os.path.dirname(os.path.abspath(__file__))
        sha = subprocess.check_output(
            ["git", "-C", app_dir, "rev-parse", "--short", "HEAD"],
            stderr=subprocess.DEVNULL).decode().strip()
        date = subprocess.check_output(
            ["git", "-C", app_dir, "log", "-1", "--format=%cd", "--date=short"],
            stderr=subprocess.DEVNULL).decode().strip()
        return f"{sha} ({date})"
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "dev"

APP_VERSION = get_version()

# ─── DATABASE ─────────────────────────────────────────────────────────────────

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.json")

def get_db():
    """Get or create a database connection for this request context."""
    if "conn" not in g:
        if not os.path.exists(CONFIG_PATH):
            raise RuntimeError("config.json not found — copy config.example.json and fill in your credentials")
        with open(CONFIG_PATH) as f:
            cfg = json.load(f)
        g.conn = psycopg2.connect(
            database=cfg["DB_NAME"],
            user=cfg["DB_USER"],
            password=cfg["DB_PASSWORD"],
            host=cfg.get("DB_HOST", "localhost"),
            port=cfg.get("DB_PORT", 5432),
        )
        g.cur = g.conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        g.cur.execute("SET TIME ZONE 'UTC';")
    return g.conn, g.cur

@app.teardown_appcontext
def close_db(error):
    cur  = g.pop("cur",  None)
    conn = g.pop("conn", None)
    if cur:  cur.close()
    if conn: conn.close()

# ─── HELPERS ──────────────────────────────────────────────────────────────────

def hamming_distance(h1, h2):
    if h1 is None or h2 is None:
        return None
    return bin(int(h1) ^ int(h2)).count("1")

def row_to_dict(row):
    d = dict(row)
    for k, v in d.items():
        if isinstance(v, memoryview):
            d[k] = bytes(v)
        elif isinstance(v, datetime.datetime):
            d[k] = v.isoformat()
        elif isinstance(v, datetime.date):
            d[k] = v.isoformat()
    return d

def thumbnail_b64(data):
    if data is None:
        return None
    if isinstance(data, memoryview):
        data = bytes(data)
    return base64.b64encode(data).decode("utf-8")

# ─── WEBHOOK (auto-deploy on push) ────────────────────────────────────────────

WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET", "")

@app.route("/webhook", methods=["POST"])
def github_webhook():
    # Verify HMAC signature
    if WEBHOOK_SECRET:
        sig = request.headers.get("X-Hub-Signature-256", "")
        expected = "sha256=" + hmac.new(
            WEBHOOK_SECRET.encode(), request.data, hashlib.sha256
        ).hexdigest()
        if not hmac.compare_digest(sig, expected):
            return jsonify({"error": "bad signature"}), 403

    if request.headers.get("X-GitHub-Event") != "push":
        return jsonify({"ok": True, "action": "ignored"})

    def do_deploy():
        import platform, tempfile
        app_dir = os.path.dirname(os.path.abspath(__file__))
        subprocess.run(["git", "-C", app_dir, "pull"], check=True)
        if platform.system() == "Windows":
            python = os.path.join(app_dir, "venv", "Scripts", "python.exe")
            if not os.path.exists(python):
                python = sys.executable
            args = " ".join(f'"{a}"' for a in [python, os.path.join(app_dir, "app.py")] + sys.argv[1:])
            bat = os.path.join(tempfile.gettempdir(), "_photo_match_restart.bat")
            with open(bat, "w") as f:
                f.write(f"@echo off\ntimeout /t 2 /nobreak >nul\n{args}\n")
            subprocess.Popen(
                ["cmd", "/c", bat],
                creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP,
                close_fds=True,
            )
            os._exit(0)
        else:
            python = os.path.join(app_dir, "venv", "bin", "python")
            if not os.path.exists(python):
                python = sys.executable
            os.execv(python, [python, os.path.join(app_dir, "app.py")] + sys.argv[1:])

    threading.Thread(target=do_deploy, daemon=True).start()
    return jsonify({"ok": True, "action": "deploying"})

# ─── MANUAL DEPLOY ────────────────────────────────────────────────────────────

@app.route("/api/deploy", methods=["POST"])
def manual_deploy():
    """Manual deploy trigger from the UI."""
    def do_deploy():
        import platform, tempfile
        app_dir = os.path.dirname(os.path.abspath(__file__))
        subprocess.run(["git", "-C", app_dir, "pull"], check=True)
        if platform.system() == "Windows":
            python = os.path.join(app_dir, "venv", "Scripts", "python.exe")
            if not os.path.exists(python):
                python = sys.executable
            args = " ".join(f'"{a}"' for a in [python, os.path.join(app_dir, "app.py")] + sys.argv[1:])
            bat = os.path.join(tempfile.gettempdir(), "_photo_match_restart.bat")
            with open(bat, "w") as f:
                f.write(f"@echo off\ntimeout /t 2 /nobreak >nul\n{args}\n")
            subprocess.Popen(
                ["cmd", "/c", bat],
                creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP,
                close_fds=True,
            )
            os._exit(0)
        else:
            python = os.path.join(app_dir, "venv", "bin", "python")
            if not os.path.exists(python):
                python = sys.executable
            os.execv(python, [python, os.path.join(app_dir, "app.py")] + sys.argv[1:])

    threading.Thread(target=do_deploy, daemon=True).start()
    return jsonify({"ok": True, "action": "deploying"})

# ─── VERSION API ──────────────────────────────────────────────────────────────

@app.route("/api/version")
@cache.cached(timeout=60)
def api_version():
    return jsonify({"version": APP_VERSION})

# ─── THUMBNAIL SERVING (with disk cache) ──────────────────────────────────────

THUMB_CACHE_DIR = os.path.join("static", "thumbnails_cache")

@app.route("/api/thumbnail/<int:hash_id>")
def serve_thumbnail(hash_id):
    os.makedirs(THUMB_CACHE_DIR, exist_ok=True)
    cache_path = os.path.join(THUMB_CACHE_DIR, f"{hash_id}.jpg")
    if os.path.exists(cache_path):
        resp = send_from_directory(THUMB_CACHE_DIR, f"{hash_id}.jpg", mimetype="image/jpeg")
        resp.headers["Cache-Control"] = "public, max-age=86400"
        return resp
    try:
        conn, cur = get_db()
        cur.execute("SELECT thumbnail FROM hashes WHERE id = %s", (hash_id,))
        row = cur.fetchone()
        if row and row[0]:
            img_bytes = bytes(row[0]) if isinstance(row[0], memoryview) else row[0]
            with open(cache_path, "wb") as f:
                f.write(img_bytes)
            resp = send_from_directory(THUMB_CACHE_DIR, f"{hash_id}.jpg", mimetype="image/jpeg")
            resp.headers["Cache-Control"] = "public, max-age=86400"
            return resp
    except Exception:
        pass
    abort(404)

@app.route("/api/wa-thumbnail/<int:wa_id>")
def serve_wa_thumbnail(wa_id):
    os.makedirs(THUMB_CACHE_DIR, exist_ok=True)
    cache_path = os.path.join(THUMB_CACHE_DIR, f"wa_{wa_id}.jpg")
    if os.path.exists(cache_path):
        resp = send_from_directory(THUMB_CACHE_DIR, f"wa_{wa_id}.jpg", mimetype="image/jpeg")
        resp.headers["Cache-Control"] = "public, max-age=86400"
        return resp
    try:
        conn, cur = get_db()
        cur.execute("SELECT thumbnail FROM wa WHERE id = %s", (wa_id,))
        row = cur.fetchone()
        if row and row[0]:
            img_bytes = bytes(row[0]) if isinstance(row[0], memoryview) else row[0]
            with open(cache_path, "wb") as f:
                f.write(img_bytes)
            resp = send_from_directory(THUMB_CACHE_DIR, f"wa_{wa_id}.jpg", mimetype="image/jpeg")
            resp.headers["Cache-Control"] = "public, max-age=86400"
            return resp
    except Exception:
        pass
    abort(404)

# ─── MATCH API ────────────────────────────────────────────────────────────────

@app.route("/api/match")
@app.route("/api/match/<int:offset>")
def api_match(offset=0):
    """
    Return the next unmatched WA item and its candidate matches from hashes table.
    Uses server-side caching with a short TTL (clears on commit).
    """
    try:
        conn, cur = get_db()

        # Count remaining
        cur.execute("SELECT count(*) FROM wa WHERE id_hash IS NULL AND processed IS NULL")
        count = cur.fetchone()[0]

        if not count:
            return jsonify({"count": 0, "item": None, "candidates": [], "partner_candidates": []})

        # Fetch the item
        cur.execute("""
            SELECT id, filename, filetype, hash, video_thumb_hash, ids_hash, thumbnail, timestamp
            FROM wa
            WHERE id_hash IS NULL AND processed IS NULL
            ORDER BY timestamp DESC, id ASC
            LIMIT 1 OFFSET %s
        """, (offset,))
        row = cur.fetchone()
        if not row:
            return jsonify({"count": 0, "item": None, "candidates": [], "partner_candidates": []})

        wa_item = {
            "id":              row["id"],
            "filename":        row["filename"],
            "filetype":        row["filetype"],
            "timestamp":       row["timestamp"].isoformat() if row["timestamp"] else None,
            "thumbnail_url":   f"/api/wa-thumbnail/{row['id']}",
            "has_ids_hash":    row["ids_hash"] is not None,
        }

        # ── Fetch candidate matches ──────────────────────────────────────────
        candidates = []
        if row["ids_hash"] is not None:
            # Pre-filtered list
            cur.execute("""
                SELECT id, filename, filetype, hash, video_thumb_hash, camera_name, location,
                       timestamp, url, preview_url,
                       video_thumb_hash <-> %s AS thumb_dist
                FROM hashes
                WHERE id = ANY(%s)
                ORDER BY timestamp ASC, id DESC
            """, (row["video_thumb_hash"], row["ids_hash"]))
        else:
            filetype = row["filetype"] or ""
            if filetype in ("Video", "video/mp4"):
                cur.execute("""
                    SELECT id, filename, filetype, hash, video_thumb_hash, camera_name, location,
                           timestamp, url, preview_url,
                           video_thumb_hash <-> %s AS thumb_dist,
                           hash <-> %s AS thumb_to_hash
                    FROM hashes
                    WHERE video_thumb_hash <@ (%s, %s)
                       OR hash <@ (%s, %s)
                    ORDER BY timestamp ASC, id DESC
                """, (
                    row["video_thumb_hash"], row["video_thumb_hash"],
                    row["video_thumb_hash"], HAMMING_DISTANCE_THRESHOLD,
                    row["video_thumb_hash"], HAMMING_DISTANCE_THRESHOLD,
                ))
            elif filetype in ("Image", "image/jpeg"):
                cur.execute("""
                    SELECT id, filename, filetype, hash, video_thumb_hash, camera_name, location,
                           timestamp, url, preview_url,
                           video_thumb_hash <-> %s AS thumb_dist
                    FROM hashes
                    WHERE hash <@ (%s, %s)
                    ORDER BY timestamp ASC, id DESC
                """, (row["video_thumb_hash"], row["hash"], HAMMING_DISTANCE_THRESHOLD))
            else:
                return jsonify({"error": f"Unsupported filetype: {filetype}"}), 400

        raw_candidates = cur.fetchall()

        for c in raw_candidates:
            cd = {
                "id":            c["id"],
                "filename":      c["filename"],
                "filetype":      c.get("filetype"),
                "camera_name":   c.get("camera_name"),
                "location":      c.get("location"),
                "timestamp":     c["timestamp"].isoformat() if c.get("timestamp") else None,
                "url":           c.get("url"),
                "preview_url":   c.get("preview_url"),
                "thumb_dist":    float(c["thumb_dist"]) if c.get("thumb_dist") is not None else None,
                "thumb_to_hash": float(c["thumb_to_hash"]) if c.get("thumb_to_hash") is not None else None,
                "thumbnail_url": f"/api/thumbnail/{c['id']}",
                "hamming_distance": hamming_distance(row["hash"], c["hash"]),
            }
            candidates.append(cd)

        # ── Auto-select logic ────────────────────────────────────────────────
        auto_select_id = None
        filetype = row["filetype"] or ""

        if len(candidates) == 2:
            if filetype in ("Video", "video/mp4"):
                if candidates[0].get("location") and not candidates[1].get("location"):
                    auto_select_id = candidates[0]["id"]
            elif filetype in ("Image", "image/jpeg"):
                wa_ts = row["timestamp"]
                h_ts = candidates[0].get("timestamp")
                if (
                    candidates[0].get("camera_name")
                    and not candidates[1].get("camera_name")
                    and wa_ts and h_ts
                    and (wa_ts - datetime.datetime.fromisoformat(candidates[0]["timestamp"])).days < 60
                ):
                    auto_select_id = candidates[0]["id"]

        elif len(candidates) > 2:
            if filetype in ("Image", "image/jpeg"):
                with_camera = [c for c in candidates if c.get("camera_name")]
                if wa_ts := row["timestamp"]:
                    recent = [
                        c for c in with_camera
                        if c.get("timestamp") and (
                            wa_ts - datetime.datetime.fromisoformat(c["timestamp"])
                        ).days < 30
                    ]
                    if recent:
                        min_dist = min(c["hamming_distance"] or 999 for c in recent)
                        best = [c for c in recent if c["hamming_distance"] == min_dist]
                        if len(best) == 1:
                            auto_select_id = best[0]["id"]

            elif filetype in ("Video", "video/mp4"):
                with_location = [c for c in candidates if c.get("location")]
                if wa_ts := row["timestamp"]:
                    recent = [
                        c for c in with_location
                        if c.get("timestamp") and (
                            wa_ts - datetime.datetime.fromisoformat(c["timestamp"])
                        ).days < 30
                    ]
                    if recent:
                        min_dist = min(c.get("thumb_dist") or 999 for c in recent)
                        best = [c for c in recent if c.get("thumb_dist") == min_dist]
                        if len(best) == 1:
                            auto_select_id = best[0]["id"]

        # ── Partner candidates ───────────────────────────────────────────────
        partner_candidates = []
        filetype = row["filetype"] or ""
        try:
            if filetype in ("Video", "video/mp4"):
                cur.execute("""
                    SELECT id, filename, filetype, camera_name, location, timestamp, url,
                           video_thumb_hash <-> %s AS thumb_dist,
                           hash <-> %s AS thumb_to_hash
                    FROM partner
                    WHERE video_thumb_hash <@ (%s, %s)
                       OR hash <@ (%s, %s)
                    ORDER BY timestamp ASC, id DESC
                """, (
                    row["video_thumb_hash"], row["video_thumb_hash"],
                    row["video_thumb_hash"], HAMMING_DISTANCE_THRESHOLD,
                    row["video_thumb_hash"], HAMMING_DISTANCE_THRESHOLD,
                ))
            elif filetype in ("Image", "image/jpeg"):
                cur.execute("""
                    SELECT id, filename, filetype, camera_name, location, timestamp, url,
                           video_thumb_hash <-> %s AS thumb_dist
                    FROM partner
                    WHERE hash <@ (%s, %s)
                    ORDER BY timestamp ASC, id DESC
                """, (row["video_thumb_hash"], row["hash"], HAMMING_DISTANCE_THRESHOLD))
            partner_raw = cur.fetchall()
            for p in partner_raw:
                partner_candidates.append({
                    "id":           p["id"],
                    "filename":     p["filename"],
                    "camera_name":  p.get("camera_name"),
                    "location":     p.get("location"),
                    "timestamp":    p["timestamp"].isoformat() if p.get("timestamp") else None,
                    "url":          p.get("url"),
                    "thumb_dist":   float(p["thumb_dist"]) if p.get("thumb_dist") is not None else None,
                    "thumb_to_hash":float(p["thumb_to_hash"]) if p.get("thumb_to_hash") is not None else None,
                })
        except Exception:
            pass  # partner table may not exist

        return jsonify({
            "count":              count,
            "offset":             offset,
            "item":               wa_item,
            "candidates":         candidates,
            "partner_candidates": partner_candidates,
            "auto_select_id":     auto_select_id,
        })

    except Exception as e:
        app.logger.error(f"match error: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@app.route("/api/match/commit", methods=["POST"])
def api_commit():
    """Commit a hash match (or un-match) for a WA item."""
    data     = request.get_json(force=True)
    wa_id    = data.get("wa_id")
    hash_id  = data.get("hash_id")   # None = mark as unmatched (no match)
    rematch  = data.get("rematch", False)
    offset   = data.get("offset", 0)

    if not wa_id:
        return jsonify({"error": "wa_id required"}), 400

    try:
        conn, cur = get_db()
        if rematch:
            cur.execute("UPDATE wa SET ids_hash = NULL WHERE id = %s", (wa_id,))
        else:
            cur.execute("UPDATE wa SET id_hash = %s WHERE id = %s", (hash_id, wa_id))
        conn.commit()
        # Bust thumbnail cache entry
        for p in [f"wa_{wa_id}.jpg"]:
            cp = os.path.join(THUMB_CACHE_DIR, p)
            if os.path.exists(cp):
                os.remove(cp)
        return jsonify({"ok": True})
    except Exception as e:
        app.logger.error(f"commit error: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@app.route("/api/match/skip", methods=["POST"])
def api_skip():
    """Mark a WA item as processed (skip without matching)."""
    data  = request.get_json(force=True)
    wa_id = data.get("wa_id")
    if not wa_id:
        return jsonify({"error": "wa_id required"}), 400
    try:
        conn, cur = get_db()
        cur.execute("UPDATE wa SET processed = TRUE WHERE id = %s", (wa_id,))
        conn.commit()
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ─── FETCH A-SHELL DEPLOY SCRIPT ──────────────────────────────────────────────

@app.route("/api/deploy-script")
def deploy_script():
    """Serve the a-Shell deploy script for download."""
    script_path = os.path.join(os.path.dirname(__file__), "scripts", "deploy_patch.py")
    if not os.path.exists(script_path):
        abort(404)
    with open(script_path) as f:
        content = f.read()
    from flask import Response
    return Response(
        content,
        mimetype="text/plain",
        headers={"Content-Disposition": "attachment; filename=deploy_patch.py"}
    )

# ─── STATIC / PWA ROUTES ──────────────────────────────────────────────────────

@app.after_request
def pwa_headers(response):
    if request.path == "/static/sw.js":
        response.headers["Service-Worker-Allowed"] = "/"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response

@app.route("/")
def index():
    return render_template("index.html", version=APP_VERSION)

@app.route("/health")
@cache.cached(timeout=5)
def health():
    return jsonify({"ok": True, "version": APP_VERSION})

# ─── MAIN ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Photo Match PWA")
    p.add_argument("--host",  default="0.0.0.0")
    p.add_argument("--port",  type=int, default=5000)
    p.add_argument("--debug", action="store_true")
    p.add_argument("--cert",  default="", help="Path to TLS certificate (e.g. from tailscale cert)")
    p.add_argument("--key",   default="", help="Path to TLS private key")
    args = p.parse_args()

    try:
        local_ip = socket.gethostbyname(socket.gethostname())
    except socket.gaierror:
        local_ip = "?.?.?.?"

    scheme = "https" if args.cert else "http"
    print(f"\n  📷 Photo Match PWA  [{APP_VERSION}]")
    print(f"  Local:    {scheme}://localhost:{args.port}")
    print(f"  Network:  {scheme}://{local_ip}:{args.port}")
    print()

    ssl_ctx = (args.cert, args.key) if args.cert and args.key else None

    try:
        signal.pthread_sigmask(signal.SIG_UNBLOCK, {signal.SIGINT})
    except (AttributeError, OSError):
        pass
    signal.signal(signal.SIGINT, signal.default_int_handler)

    app.run(
        host=args.host,
        port=args.port,
        debug=args.debug,
        use_reloader=args.debug,
        threaded=True,
        ssl_context=ssl_ctx,
    )
