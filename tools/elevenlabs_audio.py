#!/usr/bin/env python3
"""Narration, voices and sound effects for the demo video with ElevenLabs, from demo/audio.json. Standard library only.

    python3 tools/elevenlabs_audio.py --voices            # voices on the account, to pick from
    python3 tools/elevenlabs_audio.py --list              # clips and whether they're generated yet
    python3 tools/elevenlabs_audio.py n01-christmas-eve   # generate one clip (or several names)

A clip is {"name", "kind": "speech", "voice_id", "text"[, "model_id", "voice_settings"]} or
{"name", "kind": "sfx", "text", "duration_seconds"}. The key comes from ELEVENLABS_API_KEY in the environment or .env
and is never printed. Results are cached by a hash of the request, so rerunning a clip costs nothing.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.dont_write_bytecode = True

from connect import config  # noqa: E402,F401  Loads .env into the environment.

API = "https://api.elevenlabs.io/v1"
CLIPS = ROOT / "demo" / "audio.json"
OUT = ROOT / "demo" / "audio"
INDEX = OUT / "index.json"
DEFAULT_MODEL = "eleven_multilingual_v2"  # Handles English and Finnish with the same voices.


def key() -> str:
    value = os.environ.get("ELEVENLABS_API_KEY", "")
    if not value:
        sys.exit("Set ELEVENLABS_API_KEY in .env (never in code).")
    return value


def call(method: str, path: str, body: dict | None = None, query: dict | None = None) -> bytes:
    url = f"{API}{path}" + (f"?{urllib.parse.urlencode(query)}" if query else "")
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={
        "xi-api-key": key(), "User-Agent": "connect-suggests-demo/1.0", "Accept": "*/*",
        **({"Content-Type": "application/json"} if data else {})})
    try:
        with urllib.request.urlopen(req, timeout=180) as response:
            return response.read()
    except urllib.error.HTTPError as error:
        sys.exit(f"ElevenLabs returned {error.code} for {method} {path}: {error.read().decode(errors='replace')[:400]}")
    except urllib.error.URLError as error:
        sys.exit(f"Couldn't reach ElevenLabs: {error.reason}")


def request_for(clip: dict) -> tuple:
    if clip["kind"] == "speech":
        body = {"text": clip["text"], "model_id": clip.get("model_id", DEFAULT_MODEL)}
        if clip.get("voice_settings"):
            body["voice_settings"] = clip["voice_settings"]
        return f"/text-to-speech/{clip['voice_id']}", body
    if clip["kind"] == "sfx":
        return "/sound-generation", {"text": clip["text"], "duration_seconds": clip.get("duration_seconds", 4)}
    sys.exit(f"Unknown kind {clip['kind']!r} in clip {clip['name']}")


def cache_key(clip: dict) -> str:
    path, body = request_for(clip)
    return hashlib.sha256(json.dumps({"path": path, "body": body}, sort_keys=True).encode()).hexdigest()[:12]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("names", nargs="*")
    parser.add_argument("--voices", action="store_true")
    parser.add_argument("--list", action="store_true")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    if args.voices:
        voices = json.loads(call("GET", "/voices"))["voices"]
        for v in sorted(voices, key=lambda v: v["name"]):
            labels = v.get("labels") or {}
            traits = ", ".join(str(labels[k]) for k in ("gender", "age", "accent", "description", "use_case") if labels.get(k))
            print(f"{v['voice_id']}  {v['name']:22s} {traits}")
        return

    clips = {c["name"]: c for c in json.loads(CLIPS.read_text(encoding="utf-8"))["clips"]}
    index = json.loads(INDEX.read_text(encoding="utf-8")) if INDEX.exists() else {}
    if args.list or not args.names:
        for name, clip in clips.items():
            done = index.get(cache_key(clip))
            print(f"{name:26s} {clip['kind']:6s} {done['file'] if done else '-'}")
        return

    OUT.mkdir(parents=True, exist_ok=True)
    for name in args.names:
        if name not in clips:
            sys.exit(f"No clip {name!r} in {CLIPS}")
        clip = clips[name]
        digest = cache_key(clip)
        if digest in index and (OUT / index[digest]["file"]).exists() and not args.force:
            print(f"{name}: cached, {OUT / index[digest]['file']}")
            continue
        path, body = request_for(clip)
        audio = call("POST", path, body, {"output_format": "mp3_44100_128"})
        filename = f"{name}-{digest[:8]}.mp3"
        (OUT / filename).write_bytes(audio)
        index[digest] = {"file": filename, "clip": name, "request": body, "path": path}
        INDEX.write_text(json.dumps(index, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"{name}: saved {OUT / filename} ({len(audio) // 1024} KB)")


if __name__ == "__main__":
    main()
