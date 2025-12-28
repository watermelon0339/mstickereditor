#!/usr/bin/env python3
"""
Set media attributes purpose to `pinned` to prevent being purged.

- 从 stickerpicker/packs/thumbnails 目录中读取媒体图片的文件名(即 media_id)，设置对应媒体的 purpose 为 pinned。
- - Sends request to:
        POST /_matrix/media/unstable/admin/media/<server>/<media id>/attributes?access_token=your_access_token

Usage:
        python keep_mmr.py <TOKEN> [--base-url URL] [--dry-run]

Optional flags:
        --server SERVER       Media repo server name (default: mtx01.cc)
        --thumbs-dir PATH     Thumbnails directory (default: ../stickerpicker/packs/thumbnails)
        --dry-run             Print the request that would be sent without sending it

Exit codes:
        0 on success (HTTP 2xx)
        non-zero on error
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from typing import Optional
import argparse
import os
from urllib import request, parse, error


@dataclass
class PurgeResult:
    status: int
    body: str


def _format_url(server: str, media_id: str, token: str) -> str:
    base = (
        f"https://matrix.{server}"
        if server.startswith("localhost") == False
        else f"http://{server}"
    )
    endpoint = (
        f"{base}/_matrix/media/unstable/admin/media/{server}/{media_id}/attributes"
    )
    query = {
        "access_token": token,
    }
    return f"{endpoint}?{parse.urlencode(query)}"


def set_media_purpose_pinned(token: str, server: str, media_id: str) -> PurgeResult:
    """Call the Matrix media admin set attributes API to set purpose to pinned."""
    url = _format_url(server, media_id, token)
    # If targeting localhost, add forwarded host header for upstream
    headers = (
        {"X-Forwarded-Host": "mtx01.cc"}
        if parse.urlparse(url).hostname == "localhost"
        else {}
    )
    # Send JSON body to set purpose
    body = json.dumps({"purpose": "pinned"}).encode("utf-8")
    headers = {**headers, "Content-Type": "application/json"}
    req = request.Request(url=url, method="POST", headers=headers, data=body)

    try:
        with request.urlopen(req, timeout=600) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            return PurgeResult(status=resp.getcode(), body=body)
    except error.HTTPError as e:
        body = (
            e.read().decode("utf-8", errors="replace") if hasattr(e, "read") else str(e)
        )
        return PurgeResult(status=e.code if hasattr(e, "code") else 0, body=body)
    except Exception as e:  # noqa: BLE001 (keep broad to surface errors to CLI)
        return PurgeResult(status=0, body=str(e))


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Set media purpose to pinned to prevent being purged from MMR",
    )
    parser.add_argument(
        "token",
        help="Access token for admin API (required)",
    )
    parser.add_argument(
        "--server",
        default="mtx01.cc",
        help="Server name for media IDs (default: %(default)s)",
    )
    # Default thumbs dir: ../stickerpicker/packs/thumbnails relative to this script
    default_thumbs = os.path.abspath(
        os.path.join(
            os.path.dirname(__file__), "..", "stickerpicker", "packs", "thumbnails"
        )
    )
    parser.add_argument(
        "--thumbs-dir",
        default=default_thumbs,
        help="Directory containing thumbnail files named by media_id (default: %(default)s)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the request instead of sending it",
    )
    return parser.parse_args(argv)


def main(argv: Optional[list[str]] = None) -> int:
    ns = parse_args(sys.argv[1:] if argv is None else argv)

    # Validate thumbs directory
    if not os.path.isdir(ns.thumbs_dir):
        print(f"Thumbnails directory not found: {ns.thumbs_dir}")
        return 1

    # Gather media IDs from filenames in thumbnails dir
    media_ids: list[str] = []
    for name in os.listdir(ns.thumbs_dir):
        path = os.path.join(ns.thumbs_dir, name)
        if os.path.isfile(path):
            media_ids.append(name)

    if not media_ids:
        print("No media IDs found in thumbnails directory.")
        return 0

    print(f"Found {len(media_ids)} media IDs in {ns.thumbs_dir}")

    # Preview or execute
    success = 0
    fail = 0
    for mid in media_ids:
        url_for_display = _format_url(ns.server, mid, ns.token)
        if ns.dry_run:
            body_str = json.dumps({"purpose": "pinned"}, ensure_ascii=False)
            print(f"[DRY-RUN] POST {url_for_display} body={body_str}")
            success += 1
            continue

        result = set_media_purpose_pinned(
            token=ns.token,
            server=ns.server,
            media_id=mid,
        )
        ok = 200 <= result.status < 300
        status_line = f"Status: {result.status}"
        if ok:
            print(f"POST {url_for_display}\n{status_line}")
            success += 1
        else:
            print(f"POST {url_for_display}\n{status_line}")
            if result.body:
                try:
                    parsed = json.loads(result.body)
                    print(json.dumps(parsed, ensure_ascii=False, indent=2))
                except Exception:
                    print(result.body)
            fail += 1

    print(f"Completed. Success: {success}, Failed: {fail}")
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
