# Handoff: review signals on LUMI (keyword filter + language model)

**Owner:** Juha · **Written:** Sat 7 Nov 2026, 09:30 · **Hard deadline:** Sun 8 Nov 2026, 09:00 (submission)
**Deliver to the team by:** Sat ~18:00, so the engine can use the signals in MVP3

This file is self-contained: it's meant to be pasted into a new chat or repository. Section 15 has a ready-made starting prompt for a new Claude session.

---

## 0. In one paragraph

Fonecta's challenge asks us to predict, for every business and every special day from 7 Nov 2026 to 6 Jan 2027, whether its listed opening hours are wrong, and what they should be. About 40% of the needed changes have no usable history, and reviews are one of the few sources that fill that gap. Reviews also give the earliest evidence that a business has **closed for good**. This workstream turns 59,856 synthetic reviews into structured, checked signals in three steps: a **keyword filter on a laptop**, then **an open language model run in one batch on LUMI**, then **a check against the dev labels**. The output is two small files that the engine reads. No live calls happen during the demo.

---

## 1. Context the team agreed on

**The challenge:** Fonecta "Connect Suggests – Customer Approves" at the Since AI 2026 hackathon, Turku.
- The demo must show five steps: **detect → suggest → contact → decide (no login) → apply via the Yext API and confirm.**
- **Judging criteria:** suggestion quality (a scorer runs on hidden test data), customer experience, reliability (the owner has the last word), extensibility, and learning (standing permission, and getting better after edits and declines).
- **Data:** the starter kit `Fonecta_SinceAI2026/FONECTA_CONNECT_SUGGESTS_2026/`. Everything is synthetic, with code under MIT and data under CC BY 4.0. Its own guide is `START_HERE.md`.

**What the team decided:**

| Topic | Decision |
|---|---|
| **No information** | We must always make a guess, pulling from other sources: own history → shopping centre → peers (city size + segment) → peers (country + segment) → segment. The wording softens when confidence is low. |
| **Confidence** | Built from many sources. Each source's measured reliability on dev data decides its weight. Sources that agree raise confidence, and conflicts lower it. |
| **Priority** | Comes from search volume, conflicting information, reviews and the date of the last update. More searches means it matters more to be right. A conflict raises priority but lowers confidence, so the owner gets an open question instead of a suggestion. |
| **Permanent closure** | **One strong signal is enough to FLAG** the business for a person. The listing is never closed automatically. |
| **Peer rule** | Use the cell's full distribution (`share_no_exception_entered`, `share_entered_closed`, `share_entered_special_hours`, `share_entered_regular`, `n_entity_days`), with fallback to broader cells. Tune on dev. |
| **Reviews** | Read them with a language model **now** (batch on LUMI). Fine-tuning a small 1–3B model is the "future" story, and done only if time allows. |
| **Channel** | **Telegram for the demo.** SMS and WhatsApp are shown as message previews. |
| **Libraries** | Any free library is OK. No GPL or AGPL without Fonecta's written approval. |
| **Way of working** | Iterative MVPs. MVP2 ~14:00 (engine v0 + loop), MVP3 ~20:00 (confidence, priority, **review signals**, learning, 4 languages), MVP4 ~03:00 (submission), freeze 06:00. |

**Earlier work:**
- `first_mvp/`: the V1 demo app (Python standard library). The team keeps its conversation flow, free-text edit with read-back, cooldowns, throttling, standing rules and Telegram bot.
- `second_mvp/`: empty, where the next MVP goes.
- `architecture_specification_md_technical_architecture_system_specification_v2.md`: the V2 spec. Known bugs:
  - It matches last year by `date - 364`. **Match on `day_key` instead.**
  - Its segment names are wrong. The data uses `bar_pub`, not `bar`/`pub`.
  - Its confidence formula silences history-only suggestions.
  - Its metric isn't the one the official scorer uses.

---

## 2. Where this workstream fits

```
data/reviews.json (59,856)
   │
   ▼  1. prefilter.py            laptop, seconds, standard library only
reviews_to_classify.jsonl (~3.9k; optionally all 41.5k with text)
   │
   ▼  2. classify.py on LUMI     open model, one batch job, JSON output
review_claims_raw.jsonl
   │
   ▼  3. postprocess.py          laptop: resolve dates, check against dev labels, measure precision
review_signals.jsonl   +   closure_flags.csv   +   review_evidence.csv   +   reliability.json
   │
   ▼  4. engine (second_mvp)     closure FLAGs, evidence where there's no history, priority, message reasons
```

**What the engine needs from this workstream** (section 9 has the exact formats):
1. `closure_flags.csv`: which businesses to FLAG, and why, with a quote.
2. `review_evidence.csv`: what reviewers saw on a specific special day, such as "FI-01281 was closed on PENTECOST 2026 although the listing said open".
3. `reliability.json`: how often each type of claim turned out true on dev data. This feeds the confidence calculation.

---

## 3. Input data facts (checked 7 Nov)

All paths are relative to `Fonecta_SinceAI2026/FONECTA_CONNECT_SUGGESTS_2026/`.

### 3.1 `data/reviews.json`

The file is in Yext shape: `{"meta": …, "response": {"count": N, "reviews": [ … ]}}`.

```json
{"id": 914014811, "locationId": "FI-00795", "accountId": "4415001", "rating": 2.0,
 "content": "Perheen kanssa. Valikoima oli suppea.", "authorName": "Sami V.", "url": "",
 "publisherDate": 1685611440000, "publisherId": "GOOGLEMYBUSINESS", "lastYextUpdateTime": 1685613660000,
 "status": "LIVE",
 "comments": [{"id": 514049695, "publisherDate": 1685978640000, "authorName": "Huoltamo Kielo",
               "authorRole": "BUSINESS_OWNER", "content": "Pahoittelut kokemuksesta, otamme palautteen vakavasti.",
               "visibility": "PUBLIC"}]}
```

| Fact | Value |
|---|---|
| Reviews | 59,856. **41,529 have text**, the rest are empty, and 13,568 have owner replies (`comments[]`) |
| Dates | `publisherDate` is epoch **milliseconds**, from 2023-06-01 to 2026-11-06 |
| By country (from the `locationId` prefix) | FI 35,718 · SE 16,177 · NO 7,961 |
| Languages | fi, sv, nb, en. English reviews also appear on FI and SE businesses, so the language doesn't follow the country |
| Publishers | GOOGLEMYBUSINESS 46,695 · FIRSTPARTY 6,228 · FACEBOOK 4,383 · TRIPADVISOR 2,550 |
| Ratings | 1★ 2,231 · 2★ 3,789 · 3★ 11,794 · 4★ 21,092 · 5★ 20,950 |
| Text length | median 82 characters, 99th percentile 165, max 196. Short, so cheap to classify |
| Status | all `LIVE` |

**The texts are templated.** The same sentence repeats with a different holiday. Real samples:

```
FI 2026-05-24 r2 FI-01281: Tultiin helluntaina paikan päälle, mutta ovi oli kiinni, vaikka Googlen mukaan piti olla auki. Päivittäkää aukioloajat!
FI 2025-12-31 r2 FI-01377: Välipäivinä kiinni vaikka kaikkialla netissä luki auki. Tarkistakaa tiedot.
FI 2024-01-05 r2 FI-01143: Tultiin loppiaisaattona klo 18.20 ja ovet olivat jo kiinni. Netissä oli eri ajat.
SE 2024-12-26 r1 SE-00517: Vi kom hit på annandag jul men det var stängt, trots att Google sa öppet. Uppdatera era öppettider!
SE 2026-04-04 r2 SE-00294: Fel öppettider på långfredagen. Stod framför en stängd dörr.
NO 2025-04-17 r2 NO-00063: Synd, stengt skjærtorsdag. Oppdater gjerne åpningstidene for helligdager.
NO 2026-05-14 r1 NO-00293: Kjørte hit Kristi himmelfartsdag, men alt var mørkt. Google viste 10–21.
NO 2026-05-11 r2 NO-00157: Nå bare åpent man–fre 8–23, lør 9–21.            ← regular hours changed
EN 2026-04-03 r2 FI-01532: Map said open on Good Friday. It wasn't.
EN 2026-05-14 r2 FI-00366: Map said open on the holiday. It wasn't.        ← no day named: resolve from the review date
FI 2026-10-18 r3 FI-01220: Lopettanut toimintansa, valitettavasti.          ← permanent closure
SE 2026-09-25 r1 SE-00551: Stället har stängt för gott, lokalen är tom.      ← permanent closure
```

**What that means for us:**
- **Easy to read, easy to overfit.** A keyword list tuned on these templates may fail on the hidden **test** businesses if their templates differ. A language model generalises better, so measure on dev and keep the patterns broad.
- **Noise is built in on purpose.** The kit's docs say there are "misleading reviews", so don't treat every claim as true. That's why step 3 measures how often each claim is right.
- **Some reviews name no day** ("on the holiday", "yesterday"). Resolve them from `publisherDate` against the calendar (section 7.1).

### 3.2 Other files used here

| File | Use here |
|---|---|
| `data/calendar_special_days.csv` | `country, date, weekday, day_key, day_class, day_type, name_local, name_en, official_public_holiday`. Used to resolve days that aren't named, and for the holiday names in section 4.2 |
| `data/entities.json` | `meta.id`, `meta.countryCode`, `closed` (already published as closed), `c_segment`. Skip businesses already published as closed |
| `data/splits.csv` | `entity_id, split`: dev 802 · test 2,198 · demo 17 · reference 15 (shopping centres). **Only dev has labels** |
| `data/publisher_suggestions.json` | Second closure signal: `fieldName == "closed"` (section 8) |
| `labels/dev_regular_hours_truth.csv` | `entity_id, split, true_regular_hours_now, listing_is_outdated, permanently_closed`, used to check closure claims |
| `labels/dev_truth_history.csv` | `entity_id, date, day_key, event_id, truth_hours, displayed_hours_that_day`, used to check claims about specific days, 2024 → 5 Nov 2026 |
| `labels/dev_labels_2026.csv` | `truth_hours, displayed_hours_at_snapshot, needs_action, expected_action, mismatch_type, expected_search_views` |

The data's hours format is `closed` · `09:00-17:00` · `10:00-14:00,17:00-22:00` · `18:00-02:00` (past midnight) · `00:00-23:59` (24 h).

### 3.3 What we've already measured (rough keyword test, dev businesses only)

| Signal | Closed for good (7 dev businesses) | Still open (795 dev businesses) |
|---|---|---|
| Clear closure phrase in a review | 4 | **0** |
| …posted in the last 90 days before 6 Nov 2026 | 3 | 0 |
| Just the word "closed" / "suljettu" / "kiinni" / "stängt" / "stengt" | 5 | **386** ← useless on its own |
| A Google user suggested `closed` (publisher suggestions) | 4 | 0 |

- **Publisher "closed" suggestions overall:** 20, by status ACCEPTED 9 · EXPIRED 6 · WAITING_ON_CUSTOMER 4 · REJECTED 1.
- **Already published as closed:** 5 dev businesses have `closed: true`. They need no action, so exclude them from flagging.
- **The filter:** our rough version kept **3,878 reviews**, the ones that mention hours, closing or holidays.

---

## 4. Step 1: keyword filter (`prefilter.py`, laptop)

**Goal:** a filter that keeps nearly every useful review, so the model reads ~4k reviews instead of 60k. Here, missing a useful review is worse than keeping a useless one, because the model handles precision.

### 4.1 Patterns

Use Python's `re` with `re.IGNORECASE`. Finnish inflects heavily, so match on word stems.

```python
PATTERNS = {
  # open / closed / hours words
  "state_fi": r"\bauki|\bavoinna|kiinni|suljet|sulki|aukiolo|aukeaa|aukesi|ovet? (oli|olivat)",
  "state_sv": r"öppet|öppna|stängt|stängd|stängde|öppettid",
  "state_nb": r"åpent|åpen\b|åpne|stengt|stengte|åpningstid|alt var mørkt|mørkt",
  "state_en": r"\bopen(ed)?\b|\bclosed\b|\bshut\b|opening hours|\bhours\b|wasted trip|it wasn'?t",
  # "the listing said…"
  "listing": r"google|kartta|kartalla|netissä|nettisivu|verkossa|\bmap\b|online|internet|nätet|hemsida|sidan|nettet|nettsiden|listing",
  # permanent closure (strong)
  "closure_fi": r"lopett|lopetti|toiminta (on )?päättynyt|konkurss|pysyvästi suljettu|ei enää (ole )?(auki|toiminnassa|olemassa)|tyhjä liiketila|liike on tyhjä",
  "closure_sv": r"stängt för gott|lagt ner|lagts ned|har stängt|finns inte längre|konkurs|lokalen är tom",
  "closure_nb": r"stengt for godt|lagt ned|nedlagt|finnes ikke lenger|konkurs|lokalet er tomt|har stengt",
  "closure_en": r"closed (down|for good|permanently)|permanently closed|out of business|no longer (open|exists|in business)|shut down|went bankrupt|empty premises",
  # temporary closure (must NOT be read as permanent)
  "temporary": r"remont|renovation|renover|tillfälligt|midlertidig|väliaikaisesti|tilapäisesti|temporar",
  # regular hours changed
  "regular_change": r"nykyään|nowadays|numera|nå bare|nå kun|only open|vain (ma|ti|ke|to|pe)|bara öppet|nya öppettider|uudet aukiolo",
  # relative days
  "relative_day": r"eilen|tänään|igår|idag|i går|i dag|yesterday|today|viime viikolla|förra veckan|forrige uke|last week",
}
```

**Holiday names:** also build one pattern from section 4.2 (and from `name_local`/`name_en` in `calendar_special_days.csv`), in every inflected form you can think of. Using stems helps: `jouluaatto|jouluaattona` → `jouluaat`, `helluntai` matches `helluntaina`, `juhannus` matches both midsummer days.

### 4.2 Holiday names by `day_key` (from `calendar_special_days.csv`)

| day_key | type | English | FI | SE | NO |
|---|---|---|---|---|---|
| `NEW_YEARS_DAY` | PUBLIC_HOLIDAY | New Year's Day | Uudenvuodenpäivä | Nyårsdagen | Første nyttårsdag |
| `EPIPHANY_EVE` | EVE | Epiphany Eve | Loppiaisaatto | Trettondagsafton | – |
| `EPIPHANY` | PUBLIC_HOLIDAY | Epiphany | Loppiainen | Trettondedag jul | – |
| `MAUNDY_THURSDAY` | EVE | Maundy Thursday | Kiirastorstai | Skärtorsdagen | Skjærtorsdag |
| `GOOD_FRIDAY` | PUBLIC_HOLIDAY | Good Friday | Pitkäperjantai | Långfredagen | Langfredag |
| `EASTER_SATURDAY` | EVE | Easter Saturday | Pääsiäislauantai | Påskafton | Påskeaften |
| `EASTER_SUNDAY` | PUBLIC_HOLIDAY | Easter Sunday | Pääsiäispäivä | Påskdagen | Første påskedag |
| `EASTER_MONDAY` | PUBLIC_HOLIDAY | Easter Monday | 2. pääsiäispäivä | Annandag påsk | Andre påskedag |
| `MAY_EVE` | EVE | May Day Eve | Vappuaatto | Valborgsmässoafton | – |
| `MAY_DAY` | PUBLIC_HOLIDAY | May Day | Vappu | Första maj | Arbeidernes dag |
| `ASCENSION` | PUBLIC_HOLIDAY | Ascension Day | Helatorstai | Kristi himmelsfärdsdag | Kristi himmelfartsdag |
| `MOTHERS_DAY` | OBSERVANCE | Mother's Day | Äitienpäivä | Mors dag | Morsdag |
| `PENTECOST_EVE` | EVE | Whitsun Eve | – | Pingstafton | Pinseaften |
| `PENTECOST` | PUBLIC_HOLIDAY | Pentecost | Helluntai | Pingstdagen | Første pinsedag |
| `WHIT_MONDAY` | PUBLIC_HOLIDAY | Whit Monday | – | – | Andre pinsedag |
| `NATIONAL_DAY` | PUBLIC_HOLIDAY | National Day | – | Sveriges nationaldag | Grunnlovsdag (17. mai) |
| `MIDSUMMER_EVE` | EVE | Midsummer Eve | Juhannusaatto | Midsommarafton | – |
| `MIDSUMMER_DAY` | PUBLIC_HOLIDAY | Midsummer Day | Juhannuspäivä | Midsommardagen | – |
| `ALL_SAINTS` | PUBLIC_HOLIDAY | All Saints' Day | Pyhäinpäivä | Alla helgons dag | – |
| `FATHERS_DAY` | OBSERVANCE | Father's Day | Isänpäivä | Fars dag | Farsdag |
| `BLACK_FRIDAY` | COMMERCIAL | Black Friday | Black Friday | Black Friday | Black Friday |
| `INDEPENDENCE_DAY` | PUBLIC_HOLIDAY | Independence Day | Itsenäisyyspäivä | – | – |
| `LUCIA` | OBSERVANCE | St Lucy's Day | – | Lucia | – |
| `DEC23` | COMMERCIAL | Day before Christmas Eve | Aatonaatto | Lillejulafton | Lille julaften |
| `XMAS_EVE` | EVE | Christmas Eve | Jouluaatto | Julafton | Julaften |
| `XMAS_DAY` | PUBLIC_HOLIDAY | Christmas Day | Joulupäivä | Juldagen | Første juledag |
| `BOXING_DAY` | PUBLIC_HOLIDAY | Boxing Day | Tapaninpäivä | Annandag jul | Andre juledag |
| `INTERDAY` | BETWEEN_HOLIDAYS | Between Christmas and New Year | Välipäivä | Mellandag | Romjul |
| `NYE` | EVE | New Year's Eve | Uudenvuodenaatto | Nyårsafton | Nyttårsaften |

The engine also has two `day_key` values that aren't on the calendar: `EVENT` (arena or festival nights near the business) and `SCHOOL_BREAK`.

### 4.3 Output: `reviews_to_classify.jsonl` (one JSON object per line)

```json
{"review_id": 123456789, "entity_id": "FI-01281", "country": "FI", "segment": "cafe", "split": "dev",
 "review_date": "2026-05-24", "review_ts": 1779580800000, "rating": 2.0, "publisher": "GOOGLEMYBUSINESS",
 "text": "Tultiin helluntaina paikan päälle, mutta ovi oli kiinni, vaikka Googlen mukaan piti olla auki. Päivittäkää aukioloajat!",
 "owner_replies": ["…"], "matched": ["state_fi", "listing", "holiday"],
 "before_snapshot_2025": false, "before_snapshot_2026": true,
 "recent_special_days": [{"date": "2026-05-24", "day_key": "PENTECOST"}]}
```

- **`review_date`** is in the business's local time zone: Europe/Helsinki, Europe/Stockholm or Europe/Oslo, by country.
- **`before_snapshot_2025`** means `publisherDate` < 2025-11-06 00:00 local. **`before_snapshot_2026`** means < 2026-11-06 00:00 local. These flags keep the back-test honest (section 10).
- **`recent_special_days`** lists the country's special days from 0 to 7 days before the review date. The model uses it to resolve "on the holiday" or "yesterday".
- **`owner_replies`** holds only the content of comments where `authorRole == "BUSINESS_OWNER"`.

### 4.4 Also measure what the filter misses

If LUMI time allows, run the model on **all 41,529 reviews with text** once, and compare: how many useful claims did the filter drop? That number goes in the README ("the keyword filter keeps X% of reviews and Y% of useful claims"). It's honest, and it shows the production cost trade-off.

---

## 5. Step 2: classification on LUMI (`classify.py` + `lumi_job.sh`)

### 5.1 Model choice

| Model | Licence | Why | Fits on |
|---|---|---|---|
| **Qwen2.5-7B-Instruct** (primary) | Apache 2.0 | Good at following instructions and producing JSON, and decent in fi/sv/nb | One MI250X half (64 GB) in bf16, about 15 GB |
| Qwen2.5-1.5B-Instruct (fallback) | Apache 2.0 | Fast, also runs on a laptop | Anything |
| Phi-3.5-mini-instruct (option) | MIT | The team tuned Phi-3 before. Weaker Nordic languages | Anything |
| Viking-7B (future fine-tune) | Apache 2.0 | Trained on LUMI for fi/sv/nb/da/en. **A base model, not an instruction model**, so it needs fine-tuning, which is the future story | One MI250X half |

**Avoid:** Qwen2.5-**3B** and -72B (they use the more restrictive Qwen licence, not Apache). Llama and Gemma aren't GPL, but their licences have extra conditions, so they need a licence check before use.

### 5.2 The prompt (one review per prompt, `temperature=0`)

```
You read customer reviews of Nordic businesses and extract facts about OPENING HOURS. Reviews may be in Finnish, Swedish, Norwegian or English.

Review written on {review_date} ({weekday}) about a {segment} in {country}. Rating: {rating}/5.
Review: """{text}"""
Owner replies: {owner_replies or "none"}
Special days in the 7 days before the review: {recent_special_days or "none"}

Answer with JSON only, using exactly these keys:
{
 "claim": one of "PERMANENTLY_CLOSED", "TEMPORARILY_CLOSED", "CLOSED_ON_DAY", "OPEN_ON_DAY", "DIFFERENT_HOURS_ON_DAY", "REGULAR_HOURS_DIFFERENT", "LISTING_WRONG_UNSPECIFIED", "NONE",
 "day_key": the special day the review is about, from this list, or null: {day_key_list},
 "day_named_in_text": true if the text names the day, false if you inferred it from the review date,
 "observed_hours": what the reviewer found: "closed", "HH:MM-HH:MM", or null,
 "listing_showed": what Google/the map/the internet showed according to the review: "open", "closed", "HH:MM-HH:MM", or null,
 "owner_reply_contradicts": true if an owner reply says the claim is wrong (e.g. "we are still open"),
 "language": "fi" | "sv" | "nb" | "en",
 "quote": the shortest exact phrase from the review that supports the claim,
 "certainty": "high" | "medium" | "low"
}
Rules: PERMANENTLY_CLOSED only if the business itself has stopped operating (not a holiday, not a renovation, not a move).
"Closed on Christmas Day" is CLOSED_ON_DAY, not PERMANENTLY_CLOSED. Reviews about food, staff or prices with no hours facts are "NONE".
```

**Decoding:**
- **Settings:** `temperature=0`, `max_new_tokens≈160`.
- **Parsing:** take the text from the first `{` to the last `}` and parse it as JSON. If it fails, or a value isn't in the allowed list, retry once with "Answer with valid JSON only." Write `claim: "PARSE_ERROR"` if it fails again.
- **vLLM:** it can force the shape (`guided_json` / structured outputs).
- **Output:** write one line per review to `review_claims_raw.jsonl`, keeping `review_id`, `entity_id`, `split`, `review_date` and both snapshot flags next to the model's JSON.

### 5.3 Running it on LUMI: the reliable path first

**Facts are marked VERIFY where we couldn't confirm them from LUMI's own docs.** Check `docs.lumi-supercomputer.eu`, especially *Software → Containers* and the PyTorch/AI material.

**1. Log in and prepare (login node).**

```bash
ssh -i ~/.ssh/<your_lumi_key> <username>@lumi.csc.fi
export PROJ=project_465XXXXXX            # VERIFY: your project number
mkdir -p /scratch/$PROJ/$USER/reviews && cd /scratch/$PROJ/$USER/reviews
```

**2. Pick a container.** LUMI ships ready-made ROCm/PyTorch images, reportedly under `/appl/local/containers/sif-images/` (VERIFY: list it with `ls /appl/local/containers/sif-images/`). These links can change without notice, so **copy the image you choose into `/scratch/$PROJ/…`** and use the copy.

```bash
ls /appl/local/containers/sif-images/ | grep -i pytorch
cp /appl/local/containers/sif-images/<lumi-pytorch-rocm-….sif> ./pytorch.sif
```

**3. Add the Python packages.** If the image lacks `transformers`/`accelerate`, install them into a folder on `/scratch` and point `PYTHONPATH` at it:

```bash
singularity exec pytorch.sif pip install --target /scratch/$PROJ/$USER/pylibs transformers accelerate
export PYTHONPATH=/scratch/$PROJ/$USER/pylibs
```

Some LUMI images need an environment activated inside the container first (VERIFY: check the image's README or the LUMI AI guide).

**4. Download the model on the login node.** Compute nodes may have no internet.

```bash
export HF_HOME=/scratch/$PROJ/$USER/hf
singularity exec pytorch.sif python -c "from huggingface_hub import snapshot_download as d; d('Qwen/Qwen2.5-7B-Instruct')"
```

**5. Copy the input up from your laptop.**

```bash
rsync -av reviews_to_classify.jsonl classify.py lumi_job.sh <username>@lumi.csc.fi:/scratch/project_465XXXXXX/<username>/reviews/
```

**6. The job script `lumi_job.sh`.**

```bash
#!/bin/bash
#SBATCH --account=project_465XXXXXX      # VERIFY
#SBATCH --partition=small-g              # single-GPU jobs (VERIFY: or dev-g for short tests)
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --gpus-per-node=1                # one MI250X half (64 GB)
#SBATCH --cpus-per-task=7
#SBATCH --mem=60G
#SBATCH --time=01:30:00
#SBATCH --output=classify_%j.log

export HF_HOME=/scratch/project_465XXXXXX/$USER/hf
export HF_HUB_OFFLINE=1
export PYTHONPATH=/scratch/project_465XXXXXX/$USER/pylibs
cd /scratch/project_465XXXXXX/$USER/reviews
srun singularity exec --bind /scratch pytorch.sif \
     python classify.py --input reviews_to_classify.jsonl --output review_claims_raw.jsonl \
                        --model Qwen/Qwen2.5-7B-Instruct --batch-size 32
```

- **Submit and watch:** `sbatch lumi_job.sh`, then `squeue --me`, then `tail -f classify_<jobid>.log`.
- **Test small first:** run 50 reviews with `--limit 50` (on `dev-g` if available) to check the JSON before the full job.

**7. `classify.py` (plain transformers version).**
- Load with `torch_dtype=bfloat16` and `device_map="cuda"`. ROCm PyTorch still calls the GPU `cuda`.
- Build prompts with `tokenizer.apply_chat_template`. Set `padding_side="left"` for batched generation.
- Generate in batches of 16–64.
- **Write each result as soon as it's done,** and **skip `review_id`s already in the output**, so a timeout or restart loses nothing.
- Log progress every 200 reviews.

**8. Bring the results back.**

```bash
rsync -av <username>@lumi.csc.fi:/scratch/project_465XXXXXX/<username>/reviews/review_claims_raw.jsonl .
```

**Time:** 3.9k short reviews at about 60 output tokens each should take **tens of minutes** on one GPU half with batched transformers. That's an estimate; time the 50-review test run. All 41.5k reviews with text would take roughly ten times as long.

### 5.4 Optional: vLLM (faster, riskier)

vLLM is Apache 2.0, and its ROCm builds support MI250X (gfx90a) in principle. LUMI has no Docker, so the `rocm/vllm` image would have to be converted with `singularity pull docker://rocm/vllm:<tag>`. AMD's current images target MI300 first, so **try this only if the transformers path works and there's time.** Its advantages are speed and forced JSON output.

### 5.5 Fallbacks, if LUMI access or the queue blocks you

1. **Qwen2.5-1.5B-Instruct on a laptop:** use Ollama (`ollama run qwen2.5:1.5b`) or llama.cpp. ~4k short prompts are feasible in about an hour on an Apple Silicon Mac (estimate).
2. **A free hosted API:** for example Google's Gemini free tier, Groq or the OpenRouter free models. **Their limits change, so check them on the day.** Send 20 reviews per call, which makes ~200 calls. Fine for this synthetic data, but **never send the Yext key or anything real.**
3. **Keywords only:** use the section 4.1 patterns plus the rules in 7.1, with lower reliability. This is the last resort.

---

## 6. Licences to list in the README

| Component | Licence |
|---|---|
| Starter-kit data (reviews, labels, calendar) | CC BY 4.0, attribution "Connect Suggests simulator, Since AI ry 2026" |
| Starter-kit code | MIT |
| Qwen2.5-7B-Instruct / 1.5B-Instruct | Apache 2.0 |
| Hugging Face transformers, accelerate | Apache 2.0 |
| PyTorch | BSD-3-Clause |
| vLLM (if used) | Apache 2.0 |
| Ollama / llama.cpp (fallback) | MIT |

No GPL or AGPL components.

---

## 7. Step 3: post-processing and checking (`postprocess.py`, laptop)

### 7.1 Resolving which day a review is about

1. **If the model returned a `day_key`** and it's a real special day for that country, use the most recent date with that `day_key` **on or before** `review_date`, within 10 days. Reviews about Christmas posted in early January belong to the season that started the previous November.
2. **If the model returned no `day_key` but the claim is about a specific day** (`*_ON_DAY`, `LISTING_WRONG_UNSPECIFIED`), use the special day 0–3 days before `review_date`, if there's exactly one. Otherwise mark the day as unresolved.
3. **`INTERDAY` covers several dates in one season.** Keep the exact date if the text or review date pins it down. Otherwise keep `day_key` only and let the engine match it to all of that season's in-between days.
4. **Season** = 7 Nov – 6 Jan. A date in January belongs to the season of the previous calendar year (`season = year - 1`).

### 7.2 Checking against the dev labels: dev businesses only (`split == "dev"`)

**Claims about a specific day** (`CLOSED_ON_DAY`, `OPEN_ON_DAY`, `DIFFERENT_HOURS_ON_DAY`): join to `labels/dev_truth_history.csv` on `(entity_id, date)`.
- `CLOSED_ON_DAY` is **true** if `truth_hours == "closed"`.
- `OPEN_ON_DAY` is true if `truth_hours != "closed"`.
- `DIFFERENT_HOURS_ON_DAY` counts as **exact** if `observed_hours == truth_hours`, and **near** if both ends are within 30 minutes (the same rule as `evaluation/evaluate.py`).
- Check `listing_showed` against `displayed_hours_that_day` too. That tells us whether reviews report what the listing really said.

**Closure claims** (`PERMANENTLY_CLOSED`): join to `labels/dev_regular_hours_truth.csv` and compare with `permanently_closed`. Report precision, recall, and how recent the review was.

**Regular-hours claims** (`REGULAR_HOURS_DIFFERENT`): compare with `listing_is_outdated` and `true_regular_hours_now`.

**Output: `reliability.json`.** One entry per claim type, with `certainty` as an optional finer key. The engine uses `p_true` as that source's weight.

```json
{"CLOSED_ON_DAY": {"n": 812, "p_true": 0.91},
 "PERMANENTLY_CLOSED": {"n": 6, "precision": 1.0, "recall": 0.57},
 "DIFFERENT_HOURS_ON_DAY": {"n": 140, "p_exact": 0.62, "p_near": 0.81}}
```

These numbers are placeholders showing the shape; fill in the measured values.

### 7.3 Does last year's review predict this year?

Owners repeat their habits: for dev businesses, true hours were the same in 2024 and 2025 on **87–98%** of special days (XMAS_EVE 96%, NYE 90%, INTERDAY 90%, DEC23 87%, FATHERS_DAY 98%, BLACK_FRIDAY 95%, INDEPENDENCE_DAY 89%, EPIPHANY 94%). A review saying "closed on Boxing Day 2025" is therefore evidence for **Boxing Day 2026**. Measure this directly: for 2025-season claims, how often does the 2026 truth match? Use `labels/dev_labels_2026.csv`, `truth_hours`.

---

## 8. Closure flags: the team's rule (one strong signal)

**FLAG the business if any one of these holds:**
1. **A review says `PERMANENTLY_CLOSED`** with `certainty` high or medium, was posted **within 90 days** before the snapshot, and has **no** owner reply contradicting it (`owner_reply_contradicts == false`).
2. **A publisher suggestion has `fieldName == "closed"`** and its status isn't `REJECTED`. On dev: 4 of 7 closed businesses, no false alarms.
3. **The analytics collapse** (`data/analytics_daily.parquet`, needs `pandas` + `pyarrow`): calls and actions near zero for 4+ weeks after a normal level. **Not yet tested,** so check it on dev before using it.

**Never flag:**
- A business already published as closed (`closed: true` in `entities.json`).
- A business whose only signal is `TEMPORARILY_CLOSED` (a renovation) or a holiday closure.

**Why false alarms cost so much:** a flag applies to every target row of that business, about 14 rows. Each correct flag earns +1. Each wrong one costs −0.1 on an open business, so about −1.4 in total. Suggesting open hours to a business that has closed for good costs −1 per row. In the product, a flag goes to a person and **never closes the listing automatically.**

---

## 9. Step 4: output files the engine reads

Put them in `second_mvp/data/review_signals/`. They're small, so commit them.

**`review_signals.jsonl`:** one line per review with a claim that isn't `NONE` (the raw evidence, used in the audit trail and message reasons):

```json
{"review_id": 123456789, "entity_id": "FI-01281", "split": "dev", "review_date": "2026-05-24",
 "claim": "CLOSED_ON_DAY", "day_key": "PENTECOST", "date": "2026-05-24", "season": 2025,
 "observed_hours": "closed", "listing_showed": "open", "owner_reply_contradicts": false,
 "language": "fi", "quote": "ovi oli kiinni, vaikka Googlen mukaan piti olla auki", "certainty": "high",
 "before_snapshot_2025": false, "before_snapshot_2026": true}
```

Seasons only make sense for Nov–Jan dates. For spring or summer days, `season` is simply that year, and the engine uses those reviews as general habit evidence: "this owner closes on public holidays".

**`closure_flags.csv`:**

```
entity_id,split,flag,signals,latest_evidence_date,quote,snapshot
FI-01220,dev,FLAG,REVIEW_PERMANENTLY_CLOSED|PUBLISHER_SUGGESTION_CLOSED,2026-10-22,"Lopettanut toimintansa, valitettavasti.",2026
```

**`review_evidence.csv`:** one row per business, `day_key` and season. This is what fills the no-history gap.

```
entity_id,day_key,season,date,evidence_hours,listing_showed,n_reviews,p_true,quote,snapshot
FI-01281,PENTECOST,2026,2026-05-24,closed,open,1,0.91,"ovi oli kiinni…",2026
SE-00517,BOXING_DAY,2024,2024-12-26,closed,open,1,0.91,"det var stängt, trots att Google sa öppet",2025
```

- **`p_true`** comes from `reliability.json`.
- **`snapshot`** is the latest snapshot this evidence may be used for (2025 or 2026), following section 10.

**`reliability.json`:** as in 7.2.

**How the engine uses them:**
- `closure_flags` → FLAG every target row of that business.
- `review_evidence` → a candidate source of hours, weighted by `p_true`, when no history exists. "Last year a customer found you closed on Boxing Day, although Google said open."
- The count of recent negative "listing wrong" reviews → the **reviews** part of priority.

---

## 10. Honest back-testing rules

The kit's own rule: when simulating 6 Nov 2025, use only rows with timestamps before it.
- **2025 back-test** (`evaluation/targets_2025_backtest.csv`, labels `labels/dev_labels_2025_backtest.csv`): use only reviews with `before_snapshot_2025 == true`.
- **2026 season** (`evaluation/targets_2026.csv`): use reviews with `before_snapshot_2026 == true`, which is all of them in practice. The data ends 6 Nov 2026.
- **Thresholds and keyword patterns** are tuned on dev businesses only. Never look at test or demo results to tune. Test has no labels anyway; the organisers score it.

---

## 11. Risks and what to do

| Risk | What to do |
|---|---|
| LUMI access, container setup or the queue takes hours | Start access and the 50-review test **first**. If it isn't running by ~13:00, use fallback 5.5 (1) or (2) in parallel |
| The model writes invalid JSON | Retry once, then `PARSE_ERROR`. vLLM can force the shape. Keep the output small |
| Templated synthetic reviews, so dev results look better than test | Prefer the model over regex, report precision on dev honestly, and don't tune only to the template sentences |
| Wrong closure flags | Recency + no owner rebuttal + no "temporary" words. A flag goes to a person, never closes the listing |
| "The holiday" with no day named | Rule 7.1(2). Unresolved claims count only for the reviews part of priority, not as hours evidence |
| Misleading reviews (built in on purpose) | Weight by the measured `p_true`, and require agreement with other sources before overriding history |
| Time | Ship the 3.9k filtered run first, and run all 41.5k only if time allows |

---

## 12. Checklist and timeline for this workstream (Saturday)

- [ ] **~10:00** LUMI: log in, project number, `/scratch` folder, container chosen and copied, model downloaded.
- [ ] **~10:30** `prefilter.py` written and run → `reviews_to_classify.jsonl`, with counts per country and language.
- [ ] **~11:00** `classify.py` 50-review test on LUMI (or a laptop): check the JSON and the speed.
- [ ] **~12:00** Full run on the ~3.9k filtered reviews submitted.
- [ ] **~14:00** `postprocess.py`: day resolution, dev check, `reliability.json`.
- [ ] **~15:00** `closure_flags.csv` + `review_evidence.csv` committed to `second_mvp/data/review_signals/`. Tell the engine owner.
- [ ] **~16:00–18:00** Optional: all 41.5k reviews for the filter-miss figure, the analytics closure signal, and ideas from section 13.
- [ ] **Before 03:00** README notes (section 14).

---

## 13. The future story: our own small model

What to say in the pitch and README:
- **Labels as training data:** the language model's checked labels become training data for a small, fast model, such as a fine-tuned Viking-7B (Nordic languages, Apache 2.0, trained on LUMI) or a 1–3B model.
- **Running it for real:** that model could run inside Fonecta's own systems on every new review, in real time, at no API cost.
- **Measuring it honestly:** the same dev check (section 7.2) measures whether it's good enough.
- **Only if time allows tonight:** a LoRA fine-tune of Qwen2.5-1.5B-Instruct on the labelled reviews, a couple of thousand examples and short. Compare it with the 7B on dev.

---

## 14. What goes into the submission README

- **Data sources that mattered:** the reviews row (signal, how it's used, where Connect would get it in production: Yext *Reviews: List*).
- **What didn't work:** the plain "closed" keyword hit 386 of 795 open dev businesses. Also report what the filter missed, if measured.
- **Customers with no history:** reviews as evidence. Show a FI-D0017-style example if reviews exist for it, otherwise any dev business.
- **Licences:** section 6.
- **Final customer messages:** include one that quotes a review in the reason (the engine and demo owners write these).

---

## 15. Starting prompt for a new Claude session

Paste this, along with this file:

```
I'm on a team doing the Fonecta "Connect Suggests" challenge at Since AI 2026 (deadline Sun 8 Nov 09:00).
My workstream: turn data/reviews.json from the starter kit into checked signals using a keyword filter
on my laptop and a batch run of Qwen2.5-7B-Instruct on the LUMI supercomputer. Everything is described
in the attached LUMI_REVIEW_SIGNALS_HANDOFF.md: follow its file formats exactly (sections 4.3, 5.2, 9).
The starter kit is at Fonecta_SinceAI2026/FONECTA_CONNECT_SUGGESTS_2026/. Write prefilter.py first
(standard library only), then classify.py and lumi_job.sh, then postprocess.py. Mark anything
LUMI-specific you're unsure of as VERIFY. Don't send any keys anywhere. Data is synthetic, CC BY 4.0.
```

---

## Sources used for the LUMI notes

- [LUMI-EasyBuild docs: ROCm (container base images in `/appl/local/containers/sif-images`, links may change)](https://klust.github.io/LUMI-EasyBuild-docs/r/rocm)
- [LUMI training material: AI containers](https://klust.github.io/LUMI-BE-training-materials/intro-evolving/12-FormerAIContainers)
- [cotainr (LUMI's container build tool): PyTorch example](https://github.com/DeiC-HPC/cotainr/pull/41)
- [Third-party LUMI Slurm notes (small-g, per-GPU binding), not official, verify](https://skills.cat/skills/dongzhuoyao/tao-research-skills/lumi-supercomputer)
- [AMD: running vLLM on Instinct GPUs (MI300X-focused, Docker)](https://instinct.docs.amd.com/projects/amdgpu-docs/en/latest/gpu-partitioning/mi300x/run-vllm.html)
