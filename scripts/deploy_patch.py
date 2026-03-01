#!/usr/bin/env python3
"""
deploy_patch.py — runs in a-Shell on iOS
Upload a patch tarball from iOS to the server via a PR.

Config file: ~/Documents/photo_match_config.txt
  GITHUB_TOKEN=ghp_yourtoken
  GITHUB_REPO=youruser/photo-match-pwa
  SERVER_URL=https://your-host:5000   (optional — for direct deploy)
"""

import os, sys, subprocess, tarfile, shutil, json, urllib.request, urllib.error
from datetime import datetime

# ── Config ───────────────────────────────────────────────────────────────────
CONFIG_PATH = os.path.expanduser("~/Documents/photo_match_config.txt")
config = {}
if os.path.exists(CONFIG_PATH):
    for line in open(CONFIG_PATH):
        line = line.strip()
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            config[k.strip()] = v.strip()

GITHUB_TOKEN = config.get("GITHUB_TOKEN", "")
GITHUB_REPO  = config.get("GITHUB_REPO", "")
SERVER_URL   = config.get("SERVER_URL", "")
TARBALL      = os.path.expanduser("~/Documents/photo_match_pwa.tar.gz")
BRANCH       = "patch/" + datetime.now().strftime("%Y%m%d-%H%M%S")
PR_TITLE     = "Patch from iOS " + datetime.now().strftime("%Y-%m-%d %H:%M")
WORK_DIR     = os.path.expanduser("~/Documents/photo_match_repo")

def die(msg):
    print("\n✗", msg, file=sys.stderr)
    sys.exit(1)

def run(*cmd, cwd=None):
    print("  $", " ".join(cmd))
    r = subprocess.run(list(cmd), cwd=cwd, capture_output=True, text=True)
    if r.returncode != 0:
        die((r.stderr or r.stdout or f"{cmd[0]} failed").strip())
    out = r.stdout.strip()
    if out:
        print(out)
    return out

print(f"\n=== 📷 Photo Match patch deployer ===")
print(f"Tarball : {TARBALL}")
print(f"Branch  : {BRANCH}")

# ── Option A: Direct webhook deploy (no GitHub needed) ────────────────────────
if SERVER_URL and not TARBALL.startswith("~/") and os.path.exists(TARBALL):
    print(f"\n→ Option A: Uploading patch directly to server {SERVER_URL}…")
    with open(TARBALL, "rb") as f:
        data = f.read()
    req = urllib.request.Request(
        f"{SERVER_URL}/api/patch",
        data=data,
        headers={
            "Content-Type":   "application/octet-stream",
            "X-Branch-Name":  BRANCH,
            "X-PR-Title":     PR_TITLE,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read())
        if result.get("ok"):
            print(f"✓ Patch applied! PR: {result.get('pr_url', 'n/a')}")
        else:
            print(f"✗ Server error: {result.get('error', 'unknown')}")
    except Exception as e:
        print(f"✗ Direct upload failed: {e}")
    sys.exit(0)

# ── Option B: GitHub PR flow ──────────────────────────────────────────────────
if not GITHUB_TOKEN:
    die(f"GITHUB_TOKEN missing. Create {CONFIG_PATH} with:\n  GITHUB_TOKEN=ghp_yourtoken\n  GITHUB_REPO=youruser/photo-match-pwa")
if not GITHUB_REPO:
    die(f"GITHUB_REPO missing in {CONFIG_PATH}")
if not os.path.exists(TARBALL):
    die(f"Tarball not found: {TARBALL}\nCreate it from the a-Shell shortcut or manually.")

AUTHED = f"https://x-access-token:{GITHUB_TOKEN}@github.com/{GITHUB_REPO}.git"

print(f"Repo    : {GITHUB_REPO}\n")

# Clone or pull
if os.path.isdir(os.path.join(WORK_DIR, ".git")):
    print("→ Updating existing clone...")
    run("lg2", "checkout", "master", cwd=WORK_DIR)
    run("lg2", "pull", cwd=WORK_DIR)
else:
    print("→ Cloning repo...")
    os.makedirs(os.path.dirname(WORK_DIR), exist_ok=True)
    run("lg2", "clone", AUTHED, WORK_DIR)

# Branch
print(f"→ Creating branch {BRANCH}...")
run("lg2", "checkout", "-b", BRANCH, cwd=WORK_DIR)

# Extract
print("→ Extracting patch...")
EXTRACT_TMP = os.path.expanduser("~/Documents/_photo_match_extract")
shutil.rmtree(EXTRACT_TMP, ignore_errors=True)
os.makedirs(EXTRACT_TMP)

SKIP = {"venv", "__pycache__", ".git", "thumbnails_cache"}

with tarfile.open(TARBALL) as t:
    members = t.getmembers()
    top = members[0].name.split("/")[0] if members else ""
    for m in members:
        parts = m.name.split("/", 1)
        if len(parts) > 1 and parts[0] == top:
            m.name = parts[1]
        elif parts[0] == top:
            continue
        if not m.name:
            continue
        if ".." in m.name or m.name.startswith("/"):
            print(f"  ⚠ Skipping suspicious path: {m.name}")
            continue
        t.extract(m, EXTRACT_TMP, filter="data")

for item in os.listdir(EXTRACT_TMP):
    if item in SKIP or item.endswith(".db"):
        continue
    src = os.path.join(EXTRACT_TMP, item)
    dst = os.path.join(WORK_DIR, item)
    if os.path.isdir(src):
        shutil.copytree(src, dst, dirs_exist_ok=True)
    else:
        shutil.copy2(src, dst)

shutil.rmtree(EXTRACT_TMP, ignore_errors=True)

# Commit
print("→ Committing...")
run("lg2", "add", ".", cwd=WORK_DIR)
status = run("lg2", "status", "--short", cwd=WORK_DIR)
if not status:
    run("lg2", "checkout", "master", cwd=WORK_DIR)
    run("lg2", "branch", "-d", BRANCH, cwd=WORK_DIR)
    die("No changes — tarball is identical to main.")

run("lg2", "commit", "-m", PR_TITLE, cwd=WORK_DIR)

# Push
print(f"→ Pushing {BRANCH}...")
run("lg2", "push", cwd=WORK_DIR)

# PR
print("→ Creating GitHub PR...")
payload = json.dumps({
    "title": PR_TITLE, "head": BRANCH, "base": "master",
    "body": "Automated patch from iOS via a-Shell 📱",
}).encode()
req = urllib.request.Request(
    f"https://api.github.com/repos/{GITHUB_REPO}/pulls",
    data=payload,
    headers={
        "Authorization":        f"Bearer {GITHUB_TOKEN}",
        "Accept":               "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "Content-Type":         "application/json",
    },
)
try:
    with urllib.request.urlopen(req) as resp:
        pr = json.loads(resp.read())
    pr_url = pr["html_url"]
except urllib.error.HTTPError as e:
    body = json.loads(e.read())
    die(f"GitHub API: {body.get('message', str(e))}")

run("lg2", "checkout", "master", cwd=WORK_DIR)
print(f"\n✓ Done! PR created: {pr_url}")
try:
    run("open", pr_url)
except Exception:
    pass
