# MVP ENGINEERS – Connect Suggests

**Challenge provider:** [Fonecta](https://www.fonecta.fi), at the Since AI Hackathon 2026 · **More detail:** [README_Detailed.md](README_Detailed.md) · **Pitch deck:** [PDF](Pitch_Deck_Team%20MVP%20Engineers.pdf) · **Video:** [Video](/demo/out/film-full.mp4) · **Demo:** [online](https://connect-suggests-demo-905296230419.europe-north1.run.app), Password provided separately. 

Connect spots discrepencies in publicly available business information and provides the owner a ready-made suggestion with the reason. The owner answers with one tap, in their own words or by voice, with no login. Our predictions score **68.62** on the organisers' `evaluate.py` for 2026, against the baseline's 54.49. All data is synthetic: "Connect Suggests simulator, Since AI ry 2026".

## Run it
We need only Python 3.9 or newer for the app and tests, with nothing to install:

```bash
git clone https://github.com/mahbub2649/fonecta_challenge.git
cd fonecta_challenge
./run_webui.sh
```

This opens http://127.0.0.1:8080, or the next free port, and writes to the local mock. We check the tests and score with:

```bash
python3 -m unittest discover tests
python3 fonecta_data/FONECTA_CONNECT_SUGGESTS_2026/evaluation/evaluate.py --predictions predictions_2026.csv
```

Optional settings in `.env` (see `.env.example`):

| Setting | What it adds |
|---|---|
| `YEXT_API_KEY` | Real writes to the Yext sandbox, started with `./run_webui.sh --sandbox` |
| `GEMINI_API_KEY` | Replies in the owner's own words |
| `ELEVENLABS_API_KEY` | Replies by voice, together with the Gemini key |

Without these keys, the buttons and the mock still work. [The walkthrough, command-line steps and live Yext checks](README_Detailed.md#how-we-run-it) are in the detailed README.

## The five steps
1. **Detect:** a transformer blend estimates, for each special day to 6 January 2027, whether the business will be closed, or has special operating hours.
2. **Suggest:** it picks the most likely hours and keeps the reason. It _states_ strong suggestions, _asks_ when it is moderately confident, and _stays quiet_ on weak guesses.
3. **Contact:** one message per group of nearby dates, in the owner's own language and on their preferred channel. Opt-outs are respected. Delivery is simulated on an on-screen phone.
4. **Decide:** a private link opens a phone page to approve, edit, or decline, without the need to log in. Owners can also **write or say** their answer, and they can confirm before anything is saved. No reply never counts as a yes.
5. **Apply + confirm:** Connect writes the change to the Yext sandbox and reads it back. The owner is given a confirmation and guidance about how long each different platform will take to update. If the write fails, they're told nothing changed.

More: [how the AI works](README_Detailed.md#how-the-ai-works), [how it learns](README_Detailed.md#how-it-learns), [results](README_Detailed.md#results) and [extensibility](README_Detailed.md#extensibility).

## Data sources that mattered most (3–5)
| Signal | How we used it | Where Connect would get it in production |
|---|---|---|
| Exception-hour history | The strongest evidence. Removing it and the estimates built from it costs 9.65 points on 2026 | Connect's audit log |
| Customer reviews and user edits | Past closures, closing times and new weekly hours. Removing them costs 0.63 and 0.37 | Yext Reviews and Publisher Suggestions |
| Calls and clicks | Traces of days when the listing was wrong. Removing them costs 0.85 | Yext Analytics |
| Peer benchmarks | The main evidence for a customer with no history, and never a rule alone. Removing them costs 0.38 | Connect's own anonymised data |
| Shopping-centre hours | Businesses that follow their centre. Removing them costs 0.60 | Yext Knowledge Graph, centre entities |

Costs come from retraining the model's LightGBM part with each source hidden. They overlap, and differences under about 0.2 are noise. [Full table and method](README_Detailed.md#data-sources-that-mattered-most).

## What we tried that didn't work
- **Moving later suggestions after one owner edit:** it lost 28 points on owners who replied, so we now offer the move instead of making it.
- **Outside data:** live holidays, city population and daylight added no clear gain, because the hidden answers are synthetic.
- **Prompting every low-data business:** it lowers the score, to 66.89 on 2026 at best.
- **A language model reading reviews:** even a perfect reader added less than a point on the 2026 data, and was computationally expensive.
- **RealMLP, row weighting, pseudo-labels and a hidden-habit model:** no clear gain.
- **The history transformer without the extra training days:** fewer wrong calls, but a lower strict score (59.74).
- **Stochastic, Brownian, and Sticky Behavioural cues:** as we hit the limits of what the data could provide, we looked for alternative ways to predict an owner's behaviour.

[The full list](README_Detailed.md#what-we-tried-that-didnt-work) is in the detailed README, and [REFERENCES.md](REFERENCES.md) has the research we considered.

## Customer with no history / no previous actions
`FI-D0017` Kahvila Kipinä joined in October 2026. With no history of its own, the model leans on similar businesses. Connect says it has no earlier hours for them and asks instead of stating, and standing permission never applies a guess like this. On the other 10 days it stays quiet. Once the owner answers, that response updates the model's future behaviour.

```text
Hei Aino! Kahvila Kipinä näkyy Googlessa näinä päivinä todennäköisesti väärin:
• Joulupäivä pe 25.12.: Google näyttää 8–17. Ehdotamme: kiinni. 86 % vastaavista yrityksistä, jotka merkitsivät aikansa, oli kiinni.
• Tapaninpäivä la 26.12.: Google näyttää 10–16. Ehdotamme: kiinni. 62 % vastaavista yrityksistä, jotka merkitsivät aikansa, oli kiinni.
Teiltä ei ole vielä aiempia poikkeusaikoja, joten vertasimme vastaaviin yrityksiin.
Emme ole tästä täysin varmoja, joten kerrothan, pitääkö ehdotus paikkansa.
Hyväksy, muokkaa tai kieltäydy ilman kirjautumista: https://connect.example/o/abc123
```

## Final customer messages (as text)
All messages, in every language, are in [docs/final_messages.md](docs/final_messages.md).

**Finnish**
```text
Hei Aleksi! Kahvila Aurora näkyy Googlessa näinä päivinä todennäköisesti väärin:
• Jouluaatto to 24.12.: Google näyttää 7.30–18. Ehdotamme: 7.30–13. Viime vuonna: 7.30–13.
• Joulupäivä pe 25.12.: Google näyttää 7.30–18. Ehdotamme: kiinni. Viime vuonna: kiinni.
Emme ole tästä täysin varmoja, joten kerrothan, pitääkö ehdotus paikkansa.
Samoina päivinä viime vuonna yrityksellänne oli noin 43 hakunäyttöä Googlessa.
Hyväksy, muokkaa tai kieltäydy ilman kirjautumista: https://connect.example/o/abc123
```

**Swedish** (email, so it has a subject line)
```text
Kafé Linnea: kontrollera era avvikande öppettider

Hej Maria! Kafé Linnea visas troligen fel på Google de här dagarna:
• Julafton tors 24/12: Google visar 8–18. Vi föreslår: stängt. Förra året: stängt.
• Juldagen fre 25/12: Google visar 8–18. Vi föreslår: stängt. 97 % av liknande företag som angav sina tider hade stängt.
Samma dagar förra året hade ert företag cirka 190 sökvisningar på Google.
Godkänn, ändra eller tacka nej utan inloggning: https://connect.example/o/abc123
```

**Norwegian**
```text
Hei Marte! Bakeri Fjord vises trolig feil på Google disse dagene:
• Julaften tor 24.12.: Google viser 7–18. Vi foreslår: 6–12. Basert på det vi vet om bedriften deres og lignende bedrifter.
• 1. juledag fre 25.12.: Google viser 7–18. Vi foreslår: stengt. I fjor: stengt.
Vi er ikke helt sikre, så si gjerne fra om forslaget stemmer.
De samme dagene i fjor hadde bedriften deres omtrent 24 søkevisninger på Google.
Godkjenn, endre eller takk nei uten innlogging: https://connect.example/o/abc123
```

**English**
```text
Hi Aleksi! Kahvila Aurora probably shows the wrong hours on Google on these days:
• Christmas Eve Thu 24 Dec: Google shows 7:30–18. We suggest: 7:30–13. Last year: 7:30–13.
• Christmas Day Fri 25 Dec: Google shows 7:30–18. We suggest: closed. Last year: closed.
We're not fully sure, so please tell us if this is right.
On the same days last year, your business had about 43 search views on Google.
Approve, edit or decline with no login: https://connect.example/o/abc123
```

**After approving**
```text
Thanks Aleksi! We've updated Kahvila Aurora:
• Christmas Eve Thu 24 Dec: 7:30–13
• Christmas Day Fri 25 Dec: closed
The new hours will show: Google (Search & Maps) about 2 min, Finder.fi / Fonecta.fi about 10 min, Fonecta Caller about 1 h, Bing about 1 day and 5 more.
Want us to handle public holidays for you from now on? We always tell you about a change, and you can undo it in one tap: https://connect.example/o/abc123
```

**After editing** (Christmas Eve changed to close at 14)
```text
Thanks Aleksi! We've updated Kahvila Aurora:
• Christmas Eve Thu 24 Dec: 7:30–14
• Christmas Day Fri 25 Dec: closed
The new hours will show: Google (Search & Maps) about 2 min, Finder.fi / Fonecta.fi about 10 min, Fonecta Caller about 1 h, Bing about 1 day and 5 more.
```

**After declining**
```text
OK Aleksi, we didn't change anything. We'll remember this next time.
```

## Bonus: live source
We replaced the public holidays in `data/calendar_special_days.csv` with live data from [Nager.Date](https://date.nager.at), saved to `connect/live_calendar.csv` by `tools/live_calendar.py`.

- **Coverage:** all 137 live dates were in the package, and none of its 125 official holidays were missing. It covers only 16 of this season's 39 special-day rows, with no eves, in-between or commercial days such as Black Friday, so those stay from the package.
- **Quality:** the dates agreed. 12 names differ, and it lists 12 dates as holidays that the package doesn't count as official, such as Julafton.
- **Gaps:** it has no hours or business data, and it doesn't raise the score. None of our 41,755 decisions changed.

We also tried the Yext sandbox: a new test business returned no reviews, listings or publisher suggestions. [More detail](README_Detailed.md#bonus-live-source).

## Third-party code, data and licences
| Component | Licence |
|---|---|
| Python standard library (web app and tests) | PSF License |
| Challenge package: `mock_api`, run unmodified | MIT, © 2026 Since AI ry |
| Rule ladder in `connect/engine.py` and client in `connect/yext.py`, adapted from the package's `examples/` | MIT, © 2026 Since AI ry |
| Challenge data, including derived `connect/views.json`, `connect/model_decisions.json` and `predictions_2026.csv` | CC BY 4.0, "Connect Suggests simulator, Since AI ry 2026" |
| LightGBM | MIT |
| scikit-learn, pandas, NumPy, seaborn | BSD-3-Clause |
| PyArrow, pytabkit | Apache-2.0 |
| TabICL and its model weights | BSD-3-Clause |
| PyTorch | BSD-style, with Apache-2.0 parts |
| Matplotlib | Matplotlib License, BSD-style |
| Holiday data from Nager.Date | The project is MIT. We found no separate terms for the API's data |
| Gemini API, ElevenLabs API, Google Cloud Run | Online services under their own terms |
| NVIDIA CUDA libraries, for local training only | NVIDIA's proprietary licence |

No GPL/AGPL components, based on a scan of the licences each Python package declares. The scan can't see inside compiled libraries bundled in a package, and the demo's hosting image includes Debian's own system tools. [Details](README_Detailed.md#third-party-code-data-and-licences).
