"""Speech to text and text to speech through ElevenLabs. Uses only the standard library, and the app works without it."""
from __future__ import annotations

import json
import urllib.error
import urllib.request
import uuid

from . import config

STT_URL = "https://api.elevenlabs.io/v1/speech-to-text"
TTS_URL = "https://api.elevenlabs.io/v1/text-to-speech/{voice}?output_format=mp3_44100_64"
MAX_AUDIO = 3 * 1024 * 1024
MAX_SPEECH = 500


class VoiceUnavailable(RuntimeError):
    pass


def _post(request: urllib.request.Request) -> bytes:
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.read()
    except (urllib.error.URLError, OSError) as error:
        raise VoiceUnavailable(type(error).__name__) from None


class ElevenLabs:
    def transcribe(self, audio: bytes, content_type: str) -> str:
        boundary = uuid.uuid4().hex
        body = (f'--{boundary}\r\nContent-Disposition: form-data; name="model_id"\r\n\r\n{config.ELEVENLABS_STT_MODEL}\r\n'
                f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="reply"\r\nContent-Type: {content_type}\r\n\r\n').encode()
        body += audio + f"\r\n--{boundary}--\r\n".encode()
        raw = _post(urllib.request.Request(STT_URL, data=body, headers={"xi-api-key": config.ELEVENLABS_KEY, "Content-Type": f"multipart/form-data; boundary={boundary}"}))
        try:
            return str(json.loads(raw.decode())["text"]).strip()
        except (ValueError, KeyError) as error:
            raise VoiceUnavailable(type(error).__name__) from None

    def speak(self, text: str) -> bytes:
        body = json.dumps({"text": text[:MAX_SPEECH], "model_id": config.ELEVENLABS_TTS_MODEL}).encode()
        return _post(urllib.request.Request(TTS_URL.format(voice=config.ELEVENLABS_VOICE), data=body,
                                            headers={"xi-api-key": config.ELEVENLABS_KEY, "Content-Type": "application/json"}))
