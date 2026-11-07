> **Note:** this is the early plan. The final film (story, demo of the real app, what's next) and how it was made are
> described in [GENERATIVE_AI.md](GENERATIVE_AI.md).

# Connect Suggests: "Open Doors" (3:00 = 2:00 story film + 1:00 platform)

**Part 1 (0:00–2:00)** is a cinematic concept film that sells the idea and the feeling, winter against summer: a
holiday the owner forgot, and a warm evening worth staying open for. Its phone screens are designed overlays, and the
summer scenario shows where Connect is heading.

**Part 2 (2:00–3:00)** is the platform: screen recordings of the real, working app, covering the five steps, the
guardrails, learning and the measured value. It opens with *"That's the idea. Here's what's already working."*, which is
the honest line between concept and product.

Characters (fictional, the same in every shot, built from one reference portrait each):
- **Aleksi**, about 40, owner of Kahvila Aurora (winter). Dark blond hair and a short beard, a dark green apron over a grey shirt. `demo/assets/ref-aleksi-ebc94261.jpg`
- **Emma**, about 30, the winter customer. Long dark hair, a cream knitted hat and scarf, a camel winter coat. `demo/assets/ref-emma-3f1a3390.jpg`
- **Sanna**, about 35, owner of Terassi Ranta, a seaside summer terrace. Light brown hair tied up, a white linen shirt, a navy apron. `demo/assets/ref-sanna-036a51ed.jpg`
- **The waitress** at Aurora (finale only): young, friendly, a dark green apron like Aleksi's.

No real artists, brands or map apps.

# Part 1: the film (2:00)

## Act 1: winter, the problem (0:00–0:20)

| # | Time | Shot | Narration (Roger) | Sound |
|---|---|---|---|---|
| 1.1 | 0:00 | Wide: a snowy Helsinki street at blue hour; Emma walks towards Kahvila Aurora | – | Footsteps in snow |
| 1.2 | 0:06 | Close: Emma's phone, "Kahvila Aurora · Open until 18:00" | *"So, it's Christmas Eve... and the map says Kahvila Aurora's open till six."* | – |
| 1.3 | 0:13 | Emma pulls the handle of the dark café twice. Locked | *"...Yeah. The door doesn't agree."* | Rattled handle, a sigh |

## Act 2: winter, one tap (0:20–0:50)

| # | Time | Shot | Narration | Sound |
|---|---|---|---|---|
| 2.1 | 0:20 | Aleksi behind the busy counter on a December morning; his phone buzzes | *"Aleksi always closes early on Christmas Eve. He just never gets round to changing it online. This year, Connect noticed for him."* | Café bustle, notification |
| 2.2 | 0:31 | **Split screen.** Left: Aleksi reads, smiles slightly, nods, taps. Right: "Christmas Eve: you closed at 13 last year, but the map says 18. Update to 7.30–13?" **Yes · Edit · No thanks**, Yes pressed | *"One short message. One tap, and it's sorted. No login, no hassle."* | Soft tap |
| 2.3 | 0:40 | **Split screen.** Left: he pockets the phone and serves the next customer. Right: "Updated", with search, maps and directories ticking on one by one | *"Updated everywhere people look... and he's back to his customers."* | Soft ticks |

## Act 3: summer, an opportunity (0:50–1:20)

| # | Time | Shot | Narration | Sound |
|---|---|---|---|---|
| 3.1 | 0:50 | Wide: a Helsinki seaside park on a hot July afternoon, a stage being set up; Terassi Ranta by the water | *"Now, summer. The hottest evening of the year... and a concert in the park, just down the road."* | Seagulls, sound check |
| 3.2 | 1:00 | Sanna wipes tables in the sun; her phone buzzes, she shades the screen | *"Sanna usually closes at ten. Connect thinks tonight's worth more."* | Notification, glasses |
| 3.3 | 1:08 | **Split screen.** Left: Sanna grins, nods, taps. Right: "Tonight: 27°C and about 10,000 people at the concert nearby. Stay open until midnight?" **Yes · Edit · No thanks**, Yes pressed | *"Stay open till midnight? ... Yes."* | Soft tap |

## Finale: both doors open (1:20–2:00)

| # | Time | Shot | Narration | Sound |
|---|---|---|---|---|
| 4.1 | 1:20 | **Split screen.** Left: Christmas Eve noon, snow; Emma opens Aurora's warm door. Right: a summer night at 23:00; the concert crowd streams onto the terrace | *"Christmas Eve... or the hottest night of summer..."* | Door chime / crowd, music |
| 4.2 | 1:32 | **Split screen.** Left: the waitress sets down coffee and a cinnamon bun in front of Emma. Right: Sanna pours drinks at sunset | *"...the doors are open when people come."* | Cups, laughter |
| 4.3 | 1:48 | Title over both halves: **Connect suggests. The owner decides.** | *"Connect suggests. The owner decides."* | A soft tone |

# Part 2: the platform (2:00–3:00), the real app

Screen recordings of the real app (`python3 run.py`, Kahvila Aurora and the other demo businesses). The owner pages
are in the owner's language with English subtitles. Clean, calm, with one soft music bed under the whole minute.

| # | Time | On screen (real app) | Narration | What it proves |
|---|---|---|---|---|
| 5.1 | 2:00 | Console overview: all customers, suggestions, search views at stake | *"That's the idea. Here's what's already working."* | It's real |
| 5.2 | 2:04 | Kahvila Aurora → **Run detection**: the days found, each with its evidence | *"Connect watches every listing: last year's hours, reviews, calls, similar businesses, shopping centres and local events."* | 1 Detect |
| 5.3 | 2:15 | A stated suggestion next to one worded as a question (the no-history café) | *"It only states a suggestion when it's confident. Otherwise it asks... or stays quiet."* | 2 Suggest, reliability |
| 5.4 | 2:24 | **Send by SMS** → the phone → the approval page; quick cuts of the Finnish, Swedish and Norwegian versions | *"One message, in the owner's language. Approve, edit or decline. No login."* | 3 Contact, 4 Decide |
| 5.5 | 2:34 | Approve → written to the Yext sandbox, read back → "where it shows" | *"Approved changes go to Yext, get checked, and the owner's told where they're live."* | 5 Apply |
| 5.6 | 2:42 | Edit → "Detect the next dates" uses it; standing permission; one-tap undo; the audit trail | *"Every answer teaches it. Owners can even hand over holidays completely... with one-tap undo."* | Learning, last word |
| 5.7 | 2:51 | Value card: "74% of at-risk search views protected · 87% of closed-door visits prevented, measured on the organisers' scorer" · "Next: review replies, posts, seasonal hours" | *"Tested on the challenge data, it protects three quarters of the searches at risk. And the same loop works for reviews and posts next."* | Value, extensibility |
| 5.8 | 2:58 | Logo / title | – | – |

## How it's made

1. **Reference portraits** (done) keep the characters the same in every shot.
2. **Start frame per shot** (`p-image-edit` with the references, or `p-image-ideogram` for readable signs).
3. **Motion** (`p-video-2-pro`, image to video): speed or draft mode first, final quality once a shot is approved.
4. **Part 1 phone screens:** designed overlays in the editor. **Part 2:** a screen recording of the real app.
5. **Audio:** Roger's narration and the sound effects from `demo/audio/`, with the voice slightly under the ambience,
   and a soft music bed in part 2.
6. **Edit:** split screens, titles and the mix in a video editor (iMovie, DaVinci Resolve or CapCut).
