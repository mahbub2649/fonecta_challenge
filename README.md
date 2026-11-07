# Connect Suggests

Wrong holiday hours send customers to a closed door, and most owners never get round to logging in to fix them. So Connect does the noticing: it spots hours that are about to be wrong and sends the owner a ready-made suggestion with the reason. The owner taps once, with no login, and Connect writes the change to Yext and says where it will show.

All data is synthetic: "Connect Suggests simulator, Since AI ry 2026".

## Run it

### 1. Set up

You need Python 3.9 or newer. The app uses only the standard library, so there's nothing to install (`requirements.txt` is there to confirm that).

The repository doesn't include the challenge data package. Put it next to this folder:

```text
parent-folder/
├── fonecta_challenge/                        # this repository
└── fonecta_data/
    └── FONECTA_CONNECT_SUGGESTS_2026/        # the challenge package
```

If it's somewhere else, set `CONNECT_DATA_DIR` to the `FONECTA_CONNECT_SUGGESTS_2026` folder.

### 2. Start the app

```bash
python3 run.py
```

Then open http://127.0.0.1:8080. Press `Ctrl+C` in the terminal to stop.

| Optional setting | What it does |
|---|---|
| `YEXT_API_KEY` | Also writes to your Yext sandbox. Copy `.env.example` to `.env` and set it there. Without a key, writes go to the local mock, and the top of the page shows which is active |
| `CONNECT_DATA_DIR` | Where the challenge package is |
| `CONNECT_PORT` | Uses another port instead of 8080 |
| `CONNECT_HOST=0.0.0.0` and `CONNECT_PUBLIC_URL=http://<laptop-ip>:8080` | Opens owner links on a phone on the same network. The console stays on the laptop |

### 3. Use the web page

1. Pick **Kahvila Aurora** on the left, then press **Run detection**.
2. Press **Send by SMS**. The message appears on the on-screen phone.
3. Tap the link in the message, then approve or edit.
4. Steps 4 and 5 fill in beside the phone, and the audit trail records each step.
5. Press **Detect the next dates** to see the next message use what the owner just said.

Press **Reset demo** to start again.

### 4. Or use the command line

With the app running, a second terminal can drive the same chain through its local API:

```bash
B=http://127.0.0.1:8080
J='Content-Type: application/json'

curl -s -X POST -H "$J" -d '{}' $B/api/reset
curl -s -X POST -H "$J" -d '{}' $B/api/business/FI-D0001/detect    # detect and suggest
curl -s -X POST -H "$J" -d '{}' $B/api/case/1/send                 # contact: returns the message and owner link

T=$(curl -s $B/api/business/FI-D0001 | python3 -c "import json,sys;print(json.load(sys.stdin)['cases'][0]['token'])")
curl -s $B/api/o/$T                                                # the dates waiting for a decision

curl -s -X POST -H "$J" \
  -d '{"decisions":[{"item":1,"action":"edit","hours":"07:30-14:00"},{"item":2,"action":"approve"}]}' \
  $B/api/o/$T/decide                                               # decide, apply and confirm
```

### 5. Run the tests and check the score

```bash
python3 -m unittest discover tests
python3 ../fonecta_data/FONECTA_CONNECT_SUGGESTS_2026/evaluation/evaluate.py --predictions predictions_2026.csv
```

### 6. Rebuild the model (optional)

The trained model's output is already in this repository, so the app doesn't need this. It takes about 5 minutes on a laptop CPU, and the last step overwrites `predictions_2026.csv` and `connect/model_decisions.json`.

```bash
pip install -r model/requirements.txt
python3 tools/build_views.py
python3 model/build_dataset.py
python3 model/past_days.py --before 2025-11-06    # first stage for the strict back-test
python3 model/past_days.py
python3 model/train.py --strict --write
```

### Businesses to try

| Business | Shows |
|---|---|
| `FI-D0001` Kahvila Aurora | Fonecta's own example |
| `FI-D0017` Kahvila Kipinä | New customer with no history |
| `FI-D0004` Muoti Lyhty | Follows the shopping centre's hours |
| `FI-D0006` Kesäravintola Ranta | Summer terrace with a forgotten winter closure |
| `FI-D0002` Ravintola Kanerva | Normally closed on Sundays, but opens on Father's Day |
| `FI-D0012` Tilitoimisto Otso | Standing permission: applied, then informed, with undo |
| `FI-D0011` Pizzeria Torni | Closed for good: goes to a person, not the owner |
| `NO-D0015` Trening Nordlys 24/7 | Nothing to change: stays quiet |
| `SE-D0008` Kafé Linnea, `NO-D0009` Bakeri Fjord | Swedish and Norwegian |

## The five steps

1. **Detect:** estimates, for each special day to 6 January 2027, whether the business will be closed, as shown, or open at other hours.
2. **Suggest:** picks the most likely exact hours and keeps the reason. Above 90% confidence it states the suggestion, below that it asks, and for weak guesses it stays quiet.
3. **Contact:** one message per group of nearby dates, in the owner's language, on their preferred channel. Opt-outs block it. Delivery is simulated on an on-screen phone.
4. **Decide:** a private link opens a phone page to approve, edit or decline, with no login. Opening the link changes nothing, and no reply never counts as a yes.
5. **Apply:** merges the change into the full hours, writes it to the Yext sandbox and reads it back. Only then is the owner told it's saved and where it should show. If the write fails, they're told nothing changed.

## How the AI works

The model only proposes. Nothing is published without the owner's approval or standing permission.

1. **Review reader:** reads closed-door complaints, closing times, thanks for being open and new weekly hours, in Finnish, Swedish, Norwegian and English, and ties each statement to the day it's about.
2. **Past-day estimator:** most special days never got an entry, so what the business really did is hidden. A LightGBM model estimates it from what the day left behind: reviews, user edits, and spikes in calls and clicks.
3. **Open or closed model:** LightGBM combines those estimates with history, peers, shopping centres, the 2025 pilot, events and weather.
4. **Hours picker:** builds candidate hours from every source and ranks them. The right hours are on the list 97% of the time.
5. **Decision layer:** chooses the action with the highest expected points, and holds back hours it thinks have under a 25% chance of being exactly right.

No business is ever scored by a model trained on it, and features only use data dated before the snapshot. The feature code has no path to the answer files, and we don't read the simulator's internals.

## How it learns

| Owner does | Next time |
|---|---|
| Edits the hours | Later suggestions move the same way, and that day uses their choice |
| Declines: "open as usual" | Connect stops asking about that day and needs more proof before suggesting "closed" |
| Declines: "stop" | The owner is opted out |
| Undoes a change | The earlier hours come back, and Connect stops asking about that day |
| Gives standing permission | Strong suggestions are applied, then the owner is told, with one-tap undo. Peer guesses are never applied this way |

## Results

Scored with the organisers' `evaluate.py`, on businesses each model never saw.

| Measure | Package baseline | Connect Suggests |
|---|---:|---:|
| **Score, 2026 season** | 54.49 | **67.66** |
| **Score, 2025 season** | 53.23 | **65.67** |
| Score, 2025, trained only on data from before that snapshot | | 59.41 |
| Exact recall, 2026 | 0.59 | 0.76 |
| Exact precision, 2026 | 0.90 | 0.85 |
| Search views protected, 2026 | 57.2% | 74.0% |
| Closed-door views prevented, 2026 | 69.2% | 86.5% |
| Wrong open or closed calls, 2026 | 224 | 389 |

We catch far more wrong hours, at the cost of more wrong calls, because the scorer rewards the trade. The owner sees each one with its reason before anything changes, and low-confidence suggestions are worded as questions. These are scores on synthetic data, and the owner simulator isn't real customer behaviour.

## Data sources that mattered most

| Signal | How we used it | Where Connect would get it in production |
|---|---|---|
| Exception-hour history | The strongest evidence, and the main source of suggested hours | Connect's audit log |
| Customer reviews | Past closures, exact closing times and new weekly hours | Yext Reviews |
| Calls and clicks | Traces of days when the listing was wrong | Yext Analytics |
| Peer benchmarks | The main evidence for a customer with no history | Connect's own anonymised data |
| Shopping-centre hours | Businesses that follow their centre | Yext Knowledge Graph, centre entities |

## What we tried that didn't work

- **A second pass of the past-day estimator**, letting each day read the business's other days. It made both seasons worse, by up to 1.5 points on 2025.
- **Rating-only reviews and calls on neighbouring days.** They added nothing.
- **Averaging more random seeds and tuning a decision margin.** Differences stayed within noise, so we kept the simpler version.
- **Larger, more detailed trees.** They scored worse on both seasons, and simpler trees did better.
- **Training the hours picker on the 2024 season.** It has too little history behind it, so that season is left out of the picker.
- **Norwegian test businesses in the sandbox.** Yext refuses them with `PROFILE_LANGUAGE_INELIGIBLE`, so that test record uses `en`. The owner's message is still Norwegian.

With perfect knowledge of last year's hidden behaviour, the same model reaches about 86 on 2026. We measured that on dev answers only, and it shows where the next gains are: better records of what businesses really did.

The review reader is built on the wording in this synthetic data. Real reviews are messier, so production would need a language model for this step, with code checking its output.

## Customer with no history

`FI-D0017` Kahvila Kipinä joined in October 2026. With no history of its own, the model leans on similar businesses. Connect says it has no earlier hours for them and asks instead of stating, and standing permission never applies a guess like this. On the other 10 days it stays quiet. Once the owner answers, later suggestions use that answer.

## Final customer messages

All of them, in every language, are in [docs/final_messages.md](docs/final_messages.md). The first message looks like this:

```text
Hei Aleksi! Kahvila Aurora näkyy Googlessa näinä päivinä todennäköisesti väärin:
• Jouluaatto to 24.12.: Google näyttää 7.30–18. Ehdotamme: 7.30–13. Viime vuonna: 7.30–13.
• Joulupäivä pe 25.12.: Google näyttää 7.30–18. Ehdotamme: kiinni. Viime vuonna: kiinni.
Emme ole tästä täysin varmoja, joten kerrothan, pitääkö ehdotus paikkansa.
Samoina päivinä viime vuonna yrityksellänne oli noin 43 hakunäyttöä Googlessa.
Hyväksy, muokkaa tai kieltäydy ilman kirjautumista: <link>
```

## Bonus: live source

Not attempted.

## What's real and what's simulated

| Part | Status |
|---|---|
| Sandbox write and read-back | Real, on labelled `TEST` businesses we create |
| Model, approval page, decisions, learning, audit trail | Real |
| Message delivery | Simulated, on the on-screen phone |
| Publisher timing in the confirmation | From the package's simulated listings, because the sandbox has none |
| Business history | The package's local Yext mock, because the sandbox has none |

## Extensibility

The loop isn't specific to hours: notice something, suggest it with a reason, get one tap, write it, confirm it, learn. Review replies and automatic posts fit the same flow. Each needs its own detection and wording, and reuses the approval page, standing permission, audit trail and undo.

## Third-party code, data and licences

| Component | Licence |
|---|---|
| Python standard library | PSF License |
| Challenge package: `mock_api`, run unmodified | MIT, © 2026 Since AI ry |
| Rule ladder in `connect/engine.py` and client in `connect/yext.py`, adapted from the package's `examples/` | MIT, © 2026 Since AI ry |
| Challenge data, including derived `connect/views.json`, `connect/model_decisions.json` and `predictions_2026.csv` | CC BY 4.0, "Connect Suggests simulator, Since AI ry 2026" |
| `model/` and `tools/build_views.py` only: LightGBM | MIT |
| `model/` and `tools/build_views.py` only: scikit-learn, pandas, NumPy | BSD-3-Clause |
| `model/` and `tools/build_views.py` only: PyArrow | Apache-2.0 |

The web app runs on the Python standard library alone. No GPL or AGPL components. No code from before the event is used.
