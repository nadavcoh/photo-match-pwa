#!/usr/bin/env python3
"""
fetch_photo_match.py
--------------------
Downloads the photo-match-pwa source tarball from GitHub and opens it
with the Claude app via a-Shell's iOS share sheet.

Usage (in a-Shell):
    python3 fetch_photo_match.py

Or set a custom repo in ~/Documents/photo_match_config.txt:
    GITHUB_REPO=youruser/photo-match-pwa
"""

import urllib.request
import os
import subprocess
import sys

# ── Config ────────────────────────────────────────────────────────────────────
CONFIG_PATH = os.path.expanduser("~/Documents/photo_match_config.txt")
config = {}
if os.path.exists(CONFIG_PATH):
    for line in open(CONFIG_PATH):
        line = line.strip()
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            config[k.strip()] = v.strip()

GITHUB_REPO = config.get("GITHUB_REPO", "youruser/photo-match-pwa")
GITHUB_URL  = f"https://github.com/{GITHUB_REPO}/archive/refs/heads/main.tar.gz"
DEST_DIR    = os.path.expanduser("~/Documents")
DEST_FILE   = os.path.join(DEST_DIR, "photo_match_patch.tar.gz")
# ──────────────────────────────────────────────────────────────────────────────


def download(url: str, dest: str) -> None:
    """Stream-download *url* to *dest* with a progress bar."""
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    print(f"Downloading: {url}")

    def _reporthook(block_num, block_size, total_size):
        downloaded = block_num * block_size
        if total_size > 0:
            pct = min(downloaded / total_size * 100, 100)
            bar = "█" * int(pct // 5) + "░" * (20 - int(pct // 5))
            sys.stdout.write(f"\r  [{bar}] {pct:5.1f}%")
            sys.stdout.flush()

    urllib.request.urlretrieve(url, dest, reporthook=_reporthook)
    print(f"\nSaved → {dest}")


def open_with_claude(filepath: str) -> None:
    """Hand the file to Claude via a-Shell's native `open` command (iOS share sheet)."""
    print("\nOpening with Claude…")
    result = subprocess.run(["open", filepath], capture_output=True, text=True)
    if result.returncode == 0:
        print("✓ File sent to Claude — select Claude in the share sheet.")
    else:
        print(
            "\n⚠️  Could not open share sheet automatically.\n"
            f"   File is at: {filepath}\n"
            "   Long-press the file in the Files app and tap Share → Claude."
        )


def main() -> None:
    print()
    print("=== 📷 Photo Match PWA — fetch & open ===")
    print(f"Repo : {GITHUB_REPO}")
    print()

    download(GITHUB_URL, DEST_FILE)

    size_kb = os.path.getsize(DEST_FILE) / 1024
    print(f"Size : {size_kb:.1f} KB")

    open_with_claude(DEST_FILE)
    print()


if __name__ == "__main__":
    main()
