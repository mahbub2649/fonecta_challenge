#!/usr/bin/env python3
"""Generate the demo's images and video clips with Pruna, from demo/scenes.json. Standard library only.

    python3 tools/pruna_assets.py --list              # scenes and whether they're generated yet
    python3 tools/pruna_assets.py hook-still          # generate one scene (or several names)
    python3 tools/pruna_assets.py hook-still --force  # generate again even if cached

The key comes from PRUNA_API_KEY in the environment or .env and is never printed. Results are cached by a hash of
the model and input, so running a scene twice costs nothing. The key is shared by every hackathon team, so this
script has no batch mode and runs one request at a time.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.dont_write_bytecode = True

from connect import config  # noqa: E402,F401  Loads .env into the environment.

API = "https://api.pruna.ai/v1"
SCENES = ROOT / "demo" / "scenes.json"
ASSETS = ROOT / "demo" / "assets"
INDEX = ASSETS / "index.json"
FAST_MODELS = {"p-image", "p-image-ideogram", "p-image-edit", "p-image-upscale"}  # Sync mode waits up to 60 s.
POLL_SECONDS = 5
POLL_LIMIT_SECONDS = 15 * 60


def key() -> str:
    value = os.environ.get("PRUNA_API_KEY", "")
    if not value:
        sys.exit("Set PRUNA_API_KEY in .env (never in code).")
    return value


def request(method: str, url: str, headers: dict | None = None, body: dict | None = None) -> tuple:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={
        "apikey": key(), "User-Agent": "connect-suggests-demo/1.0", **({"Content-Type": "application/json"} if data else {}),
        **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=120) as response:
            return response.read(), response.headers.get("Content-Type", "")
    except urllib.error.HTTPError as error:
        detail = error.read().decode(errors="replace")[:400]
        sys.exit(f"Pruna returned {error.code} for {method} {url.split('?')[0]}: {detail}")
    except urllib.error.URLError as error:
        sys.exit(f"Couldn't reach Pruna: {error.reason}")


def upload(path: Path) -> str:
    """POST /v1/files (form field `content`) and return the file's URL for use in input.images."""
    boundary = "----connectsuggests" + hashlib.sha256(path.read_bytes()).hexdigest()[:16]
    ctype = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png", "webp": "image/webp"}.get(path.suffix[1:].lower(), "application/octet-stream")
    body = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"content\"; filename=\"{path.name}\"\r\n"
            f"Content-Type: {ctype}\r\n\r\n").encode() + path.read_bytes() + f"\r\n--{boundary}--\r\n".encode()
    req = urllib.request.Request(f"{API}/files", data=body, method="POST", headers={
        "apikey": key(), "User-Agent": "connect-suggests-demo/1.0", "Content-Type": f"multipart/form-data; boundary={boundary}"})
    try:
        with urllib.request.urlopen(req, timeout=120) as response:
            result = json.loads(response.read())
    except urllib.error.HTTPError as error:
        sys.exit(f"Pruna returned {error.code} for the upload of {path.name}: {error.read().decode(errors='replace')[:400]}")
    urls = result.get("urls") if isinstance(result.get("urls"), dict) else {}
    url = result.get("url") or result.get("file_url") or result.get("uri") or urls.get("get")
    if not url:
        sys.exit(f"Upload worked but no file URL found in: {json.dumps(result)[:400]}")
    return url


def resolve_files(value):
    """Replace "@path" strings (local files) with uploaded file URLs."""
    if isinstance(value, str) and value.startswith("@"):
        return upload(ROOT / value[1:])
    if isinstance(value, list):
        return [resolve_files(v) for v in value]
    if isinstance(value, dict):
        return {k: resolve_files(v) for k, v in value.items()}
    return value


def generate(scene: dict) -> dict:
    model = scene["model"]
    headers = {"Model": model}
    if model in FAST_MODELS:
        headers["Try-Sync"] = "true"
    raw, _ = request("POST", f"{API}/predictions", headers, {"input": resolve_files(scene["input"])})
    result = json.loads(raw)
    started = time.time()
    poll = result.get("get_url")  # Status replies don't repeat it, so keep the first one.
    if poll and not result.get("generation_url"):
        print(f"  job: {poll}", flush=True)
    while not result.get("generation_url"):
        status = result.get("status")
        if status in ("failed", "canceled", "cancelled", "error"):
            sys.exit(f"Generation {status}: {json.dumps(result)[:400]}")
        poll = result.get("get_url") or poll
        if not poll:
            sys.exit(f"No generation_url or get_url in the response: {json.dumps(result)[:400]}")
        if time.time() - started > POLL_LIMIT_SECONDS:
            sys.exit(f"Still not done after {POLL_LIMIT_SECONDS // 60} minutes. Poll later: {poll}")
        print(f"  {status or 'waiting'}… ({time.time() - started:.0f}s)", flush=True)
        time.sleep(POLL_SECONDS)
        raw, _ = request("GET", poll)
        result = json.loads(raw)
    return result


def cache_key(scene: dict) -> str:
    """Hash of the model and input. Local "@path" inputs count by their content, so editing a source image re-runs."""
    def stable(value):
        if isinstance(value, str) and value.startswith("@") and (ROOT / value[1:]).exists():
            return "sha256:" + hashlib.sha256((ROOT / value[1:]).read_bytes()).hexdigest()
        if isinstance(value, list):
            return [stable(v) for v in value]
        if isinstance(value, dict):
            return {k: stable(v) for k, v in value.items()}
        return value
    return hashlib.sha256(json.dumps({"model": scene["model"], "input": stable(scene["input"])}, sort_keys=True).encode()).hexdigest()[:12]


def load_index() -> dict:
    return json.loads(INDEX.read_text(encoding="utf-8")) if INDEX.exists() else {}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("names", nargs="*")
    parser.add_argument("--list", action="store_true")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    scenes = {s["name"]: s for s in json.loads(SCENES.read_text(encoding="utf-8"))["scenes"]}
    index = load_index()

    if args.list or not args.names:
        for name, scene in scenes.items():
            done = index.get(cache_key(scene))
            print(f"{name:24s} {scene['model']:20s} {done['file'] if done else '-'}")
        return

    ASSETS.mkdir(parents=True, exist_ok=True)
    for name in args.names:
        if name not in scenes:
            sys.exit(f"No scene {name!r} in {SCENES}")
        scene = scenes[name]
        digest = cache_key(scene)
        if digest in index and (ASSETS / index[digest]["file"]).exists() and not args.force:
            print(f"{name}: cached, {ASSETS / index[digest]['file']}")
            continue
        print(f"{name}: generating with {scene['model']}…", flush=True)
        started = time.time()
        result = generate(scene)
        content, content_type = request("GET", result["generation_url"])
        ext = {"image/png": "png", "image/jpeg": "jpg", "image/webp": "webp", "video/mp4": "mp4"}.get(
            content_type.split(";")[0], scene.get("ext", "bin"))
        filename = f"{name}-{digest[:8]}.{ext}"
        (ASSETS / filename).write_bytes(content)
        index[digest] = {"file": filename, "scene": name, "model": scene["model"], "input": scene["input"],
                         "seconds": round(time.time() - started, 1)}
        INDEX.write_text(json.dumps(index, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"{name}: saved {ASSETS / filename} ({len(content) // 1024} KB, {time.time() - started:.0f}s)")


if __name__ == "__main__":
    main()
