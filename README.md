# 📷 Photo Match PWA

A **Progressive Web App** for matching media items (photos/videos from WhatsApp or similar) to their counterparts in a photo library, using perceptual hashing (pHash + Hamming distance).

Adapted from [gphoto-phash-flask](https://github.com/…/gphoto_phash_flask), rewritten as a modern PWA with offline support, service worker, HTTPS, and auto-deploy.

---

## Features

| Feature | Description |
|---|---|
| 📱 PWA | Installable on iPhone, Android, desktop |
| 🔌 Offline mode | Service worker shows offline shell + cached thumbnails when server is down |
| 🟢 Status indicator | Real-time online/offline dot in the status bar |
| 🚀 Auto-deploy | GitHub Actions + webhook — push to main → server auto-restarts |
| 🔧 Manual deploy | One-tap deploy button in the admin panel |
| 📥 Fetch a-Shell script | Download `deploy_patch.py` for iOS patching via a-Shell |
| 🔢 Version display | Git commit hash shown in status bar and admin panel |
| 🔒 HTTPS | `--cert` / `--key` flags for TLS (works with Tailscale certs) |
| ⚡ Caching | Server-side (Flask-Caching) + client-side (service worker + JS Map) |
| 📸 Thumbnail cache | Disk cache for DB thumbnails + HTTP cache headers |
| ⌨️ Keyboard shortcuts | `Enter/c` commit, `n/p` next/prev, `1-9` select candidate |

---

## Quick Start

```bash
git clone https://github.com/youruser/photo-match-pwa
cd photo-match-pwa

# Copy and fill in your database config
cp config.example.json config.json
nano config.json

# Setup (creates venv, installs deps)
./setup.sh

# Run
./run.sh

# With HTTPS (e.g. Tailscale cert)
./run.sh --cert /path/to/cert.pem --key /path/to/key.pem
```

Open `http://localhost:5000` in your browser.

---

## Database Requirements

The app expects a PostgreSQL database with the **pgvector** or **smlar** extension for hash similarity queries, and at minimum these tables:

### `wa` table
| Column | Type | Description |
|---|---|---|
| `id` | integer | Primary key |
| `filename` | text | Media filename |
| `filetype` | text | `"Image"`, `"Video"`, `"image/jpeg"`, `"video/mp4"` |
| `hash` | bigint | 64-bit pHash as signed integer |
| `video_thumb_hash` | bigint | Video thumbnail pHash |
| `ids_hash` | integer[] | Pre-filtered candidate IDs |
| `id_hash` | integer | Matched hash ID (NULL = unmatched) |
| `processed` | boolean | Skip flag |
| `thumbnail` | bytea | JPEG thumbnail blob |
| `timestamp` | timestamptz | Media timestamp |

### `hashes` table
| Column | Type | Description |
|---|---|---|
| `id` | integer | Primary key |
| `filename` | text | Photo filename |
| `hash` | bigint | 64-bit pHash |
| `video_thumb_hash` | bigint | Video thumbnail pHash |
| `camera_name` | text | EXIF camera model |
| `location` | text | GPS location string |
| `timestamp` | timestamptz | Photo timestamp |
| `url` | text | Link to photo |
| `preview_url` | text | Preview link |
| `thumbnail` | bytea | JPEG thumbnail blob |

The `<@` operator is used for Hamming distance queries (`hash <@ (target, threshold)`), which requires the [pg_similarity](https://github.com/eulerto/pg_similarity) or custom operator class.

---

## Configuration

### `config.json`
```json
{
  "DB_NAME":     "your_database",
  "DB_USER":     "your_user",
  "DB_PASSWORD": "your_password",
  "DB_HOST":     "localhost",
  "DB_PORT":     5432
}
```

### Environment variables

| Variable | Default | Description |
|---|---|---|
| `FLASK_SECRET` | (random) | Flask session secret |
| `WEBHOOK_SECRET` | `""` | GitHub webhook HMAC secret |
| `HAMMING_THRESHOLD` | `10` | Max Hamming distance for candidates |
| `CACHE_TYPE` | `SimpleCache` | `SimpleCache` or `RedisCache` |
| `CACHE_TIMEOUT` | `300` | Server cache TTL in seconds |
| `REDIS_URL` | `redis://localhost:6379/0` | Redis URL (if using Redis cache) |

---

## Auto-Deploy (GitHub Actions + Webhook)

### Setup

1. **GitHub Secrets** (Settings → Secrets → Actions):
   - `TS_OAUTH_CLIENT_ID` — Tailscale OAuth client ID
   - `TS_OAUTH_SECRET` — Tailscale OAuth secret
   - `WEBHOOK_SECRET` — Random secret (also set on server as env var)
   - `SERVER_CERT` — Your server's TLS certificate PEM (for HTTPS verify)

2. **GitHub Variables**:
   - `SERVER_HOST` — e.g. `your-host.ts.net`
   - `SERVER_PORT` — e.g. `5000`

3. **On the server**, set `WEBHOOK_SECRET`:
   ```bash
   export WEBHOOK_SECRET="your-random-secret"
   ./run.sh
   ```

Every push to `main` will trigger the webhook, which `git pull`s and restarts the server in-place.

---

## HTTPS with Tailscale

```bash
# Get a cert from Tailscale (free, auto-renewed)
tailscale cert your-host.ts.net

# Run with TLS
./run.sh --cert your-host.ts.net.crt --key your-host.ts.net.key
```

---

## iOS a-Shell Deployment

1. From the admin panel (⚙️), tap **Fetch script** to download `deploy_patch.py`
2. Save it to `~/Documents/` in a-Shell
3. Create `~/Documents/photo_match_config.txt`:
   ```
   GITHUB_TOKEN=ghp_yourtoken
   GITHUB_REPO=youruser/photo-match-pwa
   ```
4. Create a tarball of your changes in `~/Documents/photo_match_patch.tar.gz`
5. Run: `python3 ~/Documents/deploy_patch.py`

---

## Keyboard Shortcuts

| Key | Action |
|---|---|
| `Enter` or `c` | Commit selected match |
| `n` / `→` | Next item |
| `p` / `←` | Previous item |
| `r` | Refresh current item |
| `s` | Skip item |
| `1`–`9` | Select candidate #N |

---

## Systemd Service

```bash
cp photo-match.service /etc/systemd/system/
# Edit WorkingDirectory and User
sudo systemctl enable photo-match
sudo systemctl start photo-match
```

---

## Caching Architecture

| Layer | Mechanism | TTL |
|---|---|---|
| Server API responses | Flask-Caching (in-memory or Redis) | 300s |
| Thumbnail disk cache | `static/thumbnails_cache/*.jpg` | Permanent |
| HTTP thumbnail headers | `Cache-Control: public, max-age=86400` | 24h |
| Client match responses | JS Map in memory | 30s |
| SW thumbnail cache | Service worker `CacheStorage` | Until evicted |
| SW static assets | Cache-first with background update | Permanent |
