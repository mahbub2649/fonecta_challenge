# How generative AI was used to make the demo film

The demo film ([demo/out/film-full.mp4](out/film-full.mp4), 2 minutes, committed) has three parts:

1. **The story** (0:00–0:39): a concept film. Emma finds a café locked on Christmas Eve; Aleksi and Sanna update their hours in one tap; the doors are open when people come.
2. **The demo** (0:39–1:26): a screen recording of the real, working app, with narration.
3. **What's next** (1:26–1:59): slide 7 of the pitch deck as animated graphics, with Linnea from the Connect team.

Generative AI made the people, the moving footage, the voice, the sound effects and the music. Everything that carries
facts was made without it, so it can't be garbled or invented:

- the app in part 2 is a real screen recording;
- the phone screens and the slide graphics are drawn by code;
- the numbers come from the team's measurements and pitch deck.

Everything was made on Saturday 7 November 2026, during the Since AI hackathon.

## At a glance

| Service | Models | What it made | In the final film |
|---|---|---|---|
| **Pruna** (image) | `p-image`, `p-image-edit` | Character portraits, and a start frame for every shot | 15 images (4 portraits, 11 start frames) |
| **Pruna** (video) | `p-video-2-pro`, image to video | Every moving shot in parts 1 and 3 | 11 clips, 5–8 s each |
| **ElevenLabs** (voice) | Text to speech, `eleven_multilingual_v2`, voice "Roger" | All narration | 21 lines |
| **ElevenLabs** (sound) | Sound generation | Sound effects and the music | 4 effects, 4 music pieces |
| **Claude Code** (Anthropic) | Claude Opus | The script, storyboard and every prompt, plus the tools that call the APIs and cut the film | – |

Not generative: [tools/render_screens.py](../tools/render_screens.py) draws the phone and app screens, and
[tools/render_next.py](../tools/render_next.py) draws the slide-7 graphics, both with Pillow. The film is cut with
ffmpeg. Part 2 is a real screen recording.

## Pruna: people and moving footage

**Why Pruna:** it was the hackathon's tech partner and covered the usage with shared credits. Images come back in about
4–9 seconds and a 5-second video clip in about 20–30 seconds, so a shot could be tried, judged and retaken within a few
minutes.

**How it was used, in three steps:**

1. **A reference portrait for each character** (`p-image`): Emma, Aleksi, Sanna and Linnea. All are fictional.
2. **A start frame for each shot** (`p-image-edit`, with the portrait as the input image). This keeps a character the same
   person in every shot. Without a reference, each generation invents a new face.
3. **Motion** (`p-video-2-pro`, image to video): the start frame becomes the clip's first frame, and the prompt describes
   the action. Drafts used `"mode": "speed"`; the shots that matter most were redone with `"mode": "quality"`.

**Lessons learned:**

- **Never ask a video model for readable text.** A phone screen or monitor full of words comes out garbled. Screens in the
  film are drawn by code and laid over the footage, or kept out of focus.
- **Ask for what shouldn't happen, too.** Retakes needed negative instructions, for example *"no steam"*, *"no glare, no
  light reflecting on her face"*, *"only one person, no mirrors"* and *"the door does not move at all"*.
- **The motion model's own timing is approximate.** A nod or a tap lands wherever it lands. We found the exact frame
  afterwards and timed the "Yes" on the phone and the tap sound to it.
- **Character consistency comes from the reference portrait,** not from describing the person again in each prompt.

**Where:** [tools/pruna_assets.py](../tools/pruna_assets.py) runs every request listed in
[demo/scenes.json](scenes.json). The results are cached by a hash of the request, so a rerun costs nothing.

### Example: a reference portrait (`p-image`)

```json
{"prompt": "Photorealistic cinematic portrait of a fictional young woman about 30 with long dark hair, wearing a cream knitted hat and scarf and a camel winter coat, standing in a snowy Helsinki street at blue hour, snowflakes in the air, warm street lights behind her, shallow depth of field, 50mm, natural skin texture, film still.",
 "aspect_ratio": "16:9"}
```

### Example: a start frame with the same character (`p-image-edit`)

```json
{"prompt": "The same woman standing at a wooden table in the soft shade of a large beige umbrella on her seaside terrace on a hot summer evening, her smartphone lying face down on the table in front of her, a cloth in her hand. Soft, even, matte light on her face, no lens flare, no glare, no sparkling reflections, the sea calm and softly out of focus behind her. Medium shot. Photorealistic cinematic film still, 35mm, shallow depth of field, natural skin, 16:9.",
 "images": ["<URL of the uploaded reference portrait>"],
 "aspect_ratio": "16:9"}
```

### Example: the start frame in motion (`p-video-2-pro`)

```json
{"image": "<URL of the uploaded start frame>",
 "prompt": "The woman wipes the table once, then the phone lying on the table lights up. She puts the cloth down, picks up the phone and reads the message, a warm smile spreads across her face, she nods once and, near the end, taps the screen with her thumb. Soft even shade light under the umbrella, no glare, no lens flare, no light reflecting on her face; the phone screen faces away from the camera. Steady camera, cinematic, photorealistic, natural human motion.",
 "duration": 8, "resolution": "768p", "mode": "quality"}
```

### Try it yourself

Set your key first (`export PRUNA_API_KEY=...`, never in code or a commit). The hackathon key is shared by every team,
so try one request at a time, not loops.

```bash
# An image: fast models answer directly ("Try-Sync").
curl -s -X POST https://api.pruna.ai/v1/predictions \
  -H "apikey: $PRUNA_API_KEY" -H "Model: p-image" -H "Try-Sync: true" -H "Content-Type: application/json" \
  -d '{"input": {"prompt": "Photorealistic cinematic portrait of a fictional Finnish cafe owner, a man about 40 with dark blond hair and a short beard, dark green apron over a grey shirt, behind a wooden cafe counter, soft morning light, film still.", "aspect_ratio": "16:9"}}'
# -> {"generation_url": "..."}  Download it with: curl -H "apikey: $PRUNA_API_KEY" -o out.jpg "<generation_url>"

# A video: upload the start frame, start the job, then poll it.
curl -s -X POST https://api.pruna.ai/v1/files -H "apikey: $PRUNA_API_KEY" -F "content=@frame.jpg"   # -> the file's URL
curl -s -X POST https://api.pruna.ai/v1/predictions \
  -H "apikey: $PRUNA_API_KEY" -H "Model: p-video-2-pro" -H "Content-Type: application/json" \
  -d '{"input": {"image": "<file URL>", "prompt": "He hands a cup of coffee to a customer with a friendly smile, steam rises from the espresso machine.", "duration": 5, "resolution": "768p", "mode": "speed"}}'
# -> {"get_url": "..."}  Poll it until "status" is "succeeded", then download "generation_url".
```

Or with the project's tool, after adding a scene to `demo/scenes.json`: `python3 tools/pruna_assets.py <scene-name>`.

## ElevenLabs: narration, sound effects and music

**Why ElevenLabs:**

- **One narrator across the whole film.** The parts were recorded on different days and from different material, but
  they sound like one film.
- **One line per file.** Each line can be retimed or rewritten on its own without touching the others.
- **Sound effects and music from the same service,** described in plain words.

**How it was used:**

- **Choosing the voice.** We compared several voices on the same opening line, including two models, and picked
  **"Roger" (laid-back, casual)**, because the others sounded read aloud.
  - Low *stability* (0.25–0.45) keeps the delivery natural.
  - A low *style* value avoids an over-acted feel.
  - The script is written to be *spoken*: short lines, contractions, pauses (`...`).
- **Fitting the picture.** Each line is short enough to fit inside its shot (about 2.5 words per second), with a pause
  before the cut.
- **Sounds tied to moments.** The story keeps only four sound effects, each made for one moment in the picture: a locked
  handle rattling, a soft notification chime, the tap on "Yes", and a door bell. Each is placed on that exact frame.
  Background noise (footsteps, wind, café and terrace chatter) was tried and removed: with music underneath, it only
  cluttered the sound.
- **Music.** All music is made with the same sound-generation endpoint, and it's piano throughout, so the three parts feel
  like one film:
  - **the story:** sparse, wistful felt piano in winter, crossfading into the same piano with soft strings where summer
    begins;
  - **the demo:** a calm piano bed;
  - **What's next:** hopeful piano and strings.

  Each choice was made by ear from three short samples (for example piano, electronic and acoustic). The winter take came
  out about 23 dB quieter than the warm one, so each piece has its own level, about 14 dB under the narration.

**Guardrails we kept:**

- **No imitation of real people.** Celebrity, politician and cartoon-character voices were ruled out. Library voices only.
- **Keys stay local.** Keys live in `.env` and are never printed or committed.
- **Check the plan's terms.** Depending on the ElevenLabs plan, generated audio may need attribution.

**Where:** [tools/elevenlabs_audio.py](../tools/elevenlabs_audio.py) runs every clip listed in
[demo/audio.json](audio.json), cached the same way as the Pruna tool.

### Example: a narration line (text to speech)

```json
{"text": "Christmas Eve. The map says open till six.",
 "model_id": "eleven_multilingual_v2",
 "voice_settings": {"stability": 0.25, "similarity_boost": 0.75, "style": 0.1, "use_speaker_boost": true}}
```

### Example: a sound effect and the music (sound generation)

```json
{"text": "A soft, gentle, warm phone notification: a single mellow marimba note, quiet and pleasant, no vibration",
 "duration_seconds": 1.5}
```

```json
{"text": "Hopeful, uplifting instrumental music: gentle piano melody with soft strings slowly building, warm and forward-looking, cinematic, no drums, no vocals",
 "duration_seconds": 22}
```

### Try it yourself

```bash
export ELEVENLABS_API_KEY=...   # never in code or a commit

# Narration with "Roger"
curl -s -X POST "https://api.elevenlabs.io/v1/text-to-speech/CwhRBWXzGAHq8TQ4Fs17?output_format=mp3_44100_128" \
  -H "xi-api-key: $ELEVENLABS_API_KEY" -H "Content-Type: application/json" \
  -d '{"text": "So... what is next?", "model_id": "eleven_multilingual_v2", "voice_settings": {"stability": 0.4, "similarity_boost": 0.75, "style": 0.08}}' \
  -o line.mp3

# A sound effect
curl -s -X POST "https://api.elevenlabs.io/v1/sound-generation" \
  -H "xi-api-key: $ELEVENLABS_API_KEY" -H "Content-Type: application/json" \
  -d '{"text": "Slow footsteps crunching on fresh snow on a quiet winter night street", "duration_seconds": 5}' \
  -o footsteps.mp3
```

Or with the project's tool: `python3 tools/elevenlabs_audio.py --voices` lists the voices on the account, and
`python3 tools/elevenlabs_audio.py <clip-name>` makes a clip from `demo/audio.json`.

## Claude Code: script, prompts and tools

**What it did:**

- Wrote the storyboard ([demo/STORYBOARD.md](STORYBOARD.md)), the narration script and every image, video, voice and
  sound prompt above, iterating on the team's feedback after each cut.
- Built the tools that call Pruna and ElevenLabs, draw the screens, and cut the film with ffmpeg:
  [tools/build_film.py](../tools/build_film.py), [tools/build_platform.py](../tools/build_platform.py) and
  [tools/build_next.py](../tools/build_next.py).
- Checked each cut by looking at frames: measuring movement between frames, finding the exact frame of a tap, measuring
  how loud the sound effects were against the voice.

**How the team worked with it:** the team decided the story, the tone, the voice, the music and every change. Each round
of feedback was a list of notes on the latest cut, which Claude turned into prompt changes, retakes and re-cuts.

## What we'd tell another team

- **Keep facts out of generated pixels.** Draw screens and numbers with code, and record the real product.
- **Build each character from one reference portrait** and edit from it, so every shot shows the same person.
- **Prototype on images, then make video.** An image takes seconds; a video retake takes half a minute or more.
- **Write narration to be spoken,** fit each line inside its shot, and tie every sound to a visible moment.
- **Cache every generation and commit the prompts** (`scenes.json`, `audio.json`), so the film can be rebuilt and
  audited.

## Rebuild the film

```bash
pip install pillow imageio-ffmpeg                  # demo tools only, not the app
python3 tools/build_film.py                        # part 1, the story      -> demo/out/film-story.mp4
python3 tools/build_platform.py                    # part 2, the demo       -> demo/out/film-platform.mp4
python3 tools/render_next.py && python3 tools/build_next.py   # part 3 and the full film -> demo/out/film-full.mp4
```

The generated clips and audio are already in `demo/assets/` and `demo/audio/`, so a rebuild needs no API calls. The raw
screen recording (`demo/implementation_demonstration.mov`) is git-ignored. Ask the team for it if you need to rebuild
part 2.
