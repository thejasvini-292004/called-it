# Called It

**Don't just watch the game. Lead it.**

Called It is an AI-powered decision simulator for live cricket, built as a Dream11 experience. At a match-deciding moment, the fan becomes the captain for 30 seconds. They make the call, the real captain makes theirs, the over plays out, and an open-source AI model explains both decisions using only real match data. Every call builds the fan's **Match IQ**, which scores the quality of the decision, never the luck of the result.

![Called It: the fan's app on the left, the system behind it on the right](docs/screenshots/overview.png)

| Play Captain | The over | AI Match Analyst | My Match IQ |
| --- | --- | --- | --- |
| ![Play Captain](docs/screenshots/1-play-captain.png) | ![The over](docs/screenshots/2-the-over.png) | ![AI Match Analyst](docs/screenshots/3-ai-analyst.png) | ![Match IQ](docs/screenshots/4-match-iq.png) |

## Contents

- [The fan problem](#the-fan-problem)
- [Workflow](#workflow)
- [Architecture](#architecture)
- [How a round works, request by request](#how-a-round-works-request-by-request)
- [The AI analyst pipeline](#the-ai-analyst-pipeline)
- [Run it locally](#run-it-locally)
- [Deploy it](#deploy-it)
- [Configuration](#configuration)
- [Scoring](#scoring-match-iq)
- [API](#api)
- [Tests](#tests)
- [Project layout](#project-layout)

## The fan problem

During a live match, fans argue with the TV about who should bowl, then the captain does something else and the moment passes. Nobody tells them whether their instinct was good, why the captain chose differently, or whether they're getting better at reading the game. Polls never close the loop, and chatbots give the fan nothing at stake.

Called It gives fans three things:

| Part | What the fan does | What it solves |
| --- | --- | --- |
| **Play Captain** | Makes the tactical call under a shared 30-second deadline | No stake in the moment |
| **AI Match Analyst** | Reads why each choice made sense and what it risked | No explanation |
| **My Match IQ** | Sees a score and a profile of their decision style | No feedback, no way to improve |

This version runs one scenario end to end, done properly: Australia need 32 off 18, and India must choose who bowls the 18th over.

## Workflow

The fan's journey through one round:

```mermaid
flowchart LR
    A["1. Scenario appears<br/>same for every fan"] --> B["2. Fan makes the call<br/>bowler + optional reason"]
    B --> C{"Deadline<br/>30 s"}
    C -->|"call locked"| D["3. Captain's call revealed"]
    C -->|"no call"| D
    D --> E["4. The over plays out<br/>ball by ball"]
    E --> F["5. AI explains both calls<br/>cited, checked"]
    F --> G["6. Match IQ updated<br/>decision scored, not luck"]
```

Four rules shape every step:

1. **Same scenario, same deadline for everyone.** A vote cast after seeing the captain's choice is hindsight, so late picks are kept but never scored.
2. **Judge the decision, not the result.** One over is mostly luck; the result scores zero points.
3. **The AI only says what the data supports.** Every number it writes is checked against the data pack before a fan sees it.
4. **Admit what is unknown.** The bowler who didn't bowl never had an over, so the AI never guesses how it would have gone.

## Architecture

```mermaid
flowchart TB
    UI["Fan's browser: templates/index.html<br/>renders the 6 steps, polls state every 0.6 s"]

    subgraph Server["FastAPI server: app.py"]
        direction TB
        API["Routes + request validation<br/>server clock decides what each fan sees"]
        RD["rounds.py<br/>shared deadline, picks,<br/>reveal timeline"]
        SG["scoring.py<br/>Match IQ,<br/>skill profile"]
        AN["analyst.py<br/>prompt, grounding check,<br/>fallback, cache"]
        SC["scenario.py<br/>options, the over, 14-row data pack"]
        API --> RD
        API --> SG
        API --> AN
        RD --> SC
        AN --> SC
    end

    UI <-->|"HTTP + JSON"| API
    AN <--> CACHE[("analysis_cache.json")]

    subgraph Model["Open-source model (pick one with LLM_BACKEND)"]
        direction LR
        LOCAL["local: Qwen2.5-1.5B-Instruct<br/>via transformers"]
        HF["hf_api: Qwen2.5-7B-Instruct<br/>Hugging Face Inference API"]
    end

    AN --> LOCAL
    AN --> HF
```

**The server decides, the browser displays.** Time, the pick rules, the captain's choice, scoring and the AI all live on the server. The browser only sends what the fan did and draws what comes back.

| Module | Its one job |
| --- | --- |
| `app.py` | HTTP routes; wires the modules together; starts loading the model at startup |
| `called_it/scenario.py` | The match situation, four bowlers, six balls and the 14-row data pack (D1–D14) |
| `called_it/rounds.py` | Rounds, the shared deadline, picks, locks, and which facts each fan may see when |
| `called_it/scoring.py` | Match IQ points, skill profile, strengths and watch-outs |
| `called_it/analyst.py` | Model backends, prompts, citation tidying, grounding check, fallback, prefetch and cache |
| `templates/index.html` | Everything the fan sees |

**Phases are computed, never stored.** A round holds a single `deadline_at` timestamp. Each request compares the server's clock with it to work out the phase, so there is no background timer to fail and every fan sees the same phase at the same moment.

| Server time | Phase | What the fan may see |
| --- | --- | --- |
| 0–30 s | `open` | Scenario, options, countdown. `captain_choice` is `null` |
| 30–32 s | `closed` | Their locked call and the fan split |
| 32–35 s | `reveal` | The captain's choice, for the first time |
| 35–42.5 s | `playing` | One more ball every 1.5 s |
| 42.5 s on | `done` | The over's result (D14), AI analysis, Match IQ |

## How a round works, request by request

```mermaid
sequenceDiagram
    participant F as Fan's browser
    participant S as FastAPI (app.py)
    participant R as rounds.py
    participant A as analyst.py
    participant M as HF model

    F->>S: GET /api/rounds/current
    S->>R: create round, deadline = now + 30 s
    S-->>F: state (phase open, captain hidden)
    F->>S: POST /picks {option: kuldeep, reason: matchup}
    S->>R: submit(): now < deadline, so on_time = true
    S-->>F: state with your_pick
    F->>S: POST /lock
    S->>R: lock(), so further changes are refused (409)
    S->>A: prefetch(kuldeep, matchup)
    A->>M: generate in background
    loop every 0.6 s
        F->>S: GET /api/rounds/{id}
        S->>R: phase(now): closed, reveal, playing, done
        S-->>F: only what this phase allows
    end
    F->>S: GET /iq
    S-->>F: 10 + 13 + 5 + 0 = 28, Match IQ 612 to 640
    F->>S: POST /analysis
    S->>A: analyse(): cached, or wait for the job already running
    M-->>A: JSON draft
    A->>A: parse, tidy citations, grounding check
    A-->>S: AI text if checked, else verified template + note
    S-->>F: analysis with [D7] citations
```

## The AI analyst pipeline

```mermaid
flowchart LR
    P["Build prompt<br/>data pack + rules"] --> G["Model generates<br/>local or HF API"]
    G --> J["Parse JSON<br/>tidy citations"]
    J --> C{"Grounding<br/>check passes?"}
    C -->|"yes"| OK["Fan sees the AI text<br/>with citations"]
    C -->|"no"| T["Verified template<br/>+ note saying why"]
    G -->|"error or bad JSON"| T
```

1. **Prompt.** The model sees only the 14-row data pack, the fan's pick and reason, and the captain's pick. It's told to cite a row ID after every fact, say "no data" when a stat is missing, never guess the unbowled over, and judge the decision rather than the result. It must return JSON with `fan`, `captain`, `tradeoff`, `outcome` and `takeaway`.
2. **Generate.** `LocalBackend` runs Qwen2.5-1.5B-Instruct with `transformers` on the best available device (NVIDIA GPU, Apple GPU or CPU), with deterministic output. `HFApiBackend` calls a larger open model through Hugging Face Inference Providers.
3. **Parse and tidy.** Code fences and trailing commas are tolerated. `(D3)`, `D3` and `[D4, D5]` are normalised to `[D3]`, `[D4][D5]`.
4. **Grounding check.** A draft passes only if every number in it appears in the data pack, every citation points to a real row, and at least one citation is present. A draft claiming "23 death wickets at 6.2" is rejected.
5. **Fallback.** With `GROUNDING_POLICY=reject` (default), a failed draft or a model error is replaced by a hand-written analysis that passes the same check, with a note naming what failed. The fan always gets something correct.

Follow-up questions ("Ask the analyst") go through the same model and the same check; answers with invented figures are withheld.

**Speed.** The analysis starts generating the moment a fan's call locks, during the roughly 12 seconds of reveal and over. Requests for the same pick share one job, and finished analyses are saved to `analysis_cache.json` and reloaded at startup. Run `python warm_cache.py` before a demo to pre-generate all 20 combinations.

## Run it locally

Requires Python 3.10 or newer.

```bash
git clone https://github.com/<your-username>/called-it.git
cd called-it
python3 -m venv .venv
source .venv/bin/activate              # Windows: .venv\Scripts\activate
pip install -r requirements-local.txt  # includes the model runtime (PyTorch)
uvicorn app:app --reload
```

Open http://127.0.0.1:8000. The first start downloads Qwen/Qwen2.5-1.5B-Instruct (about 3 GB) from the Hugging Face Hub in the background.

No download? Use the Hugging Face API instead:

```bash
pip install -r requirements.txt
LLM_BACKEND=hf_api HF_TOKEN=hf_yourtoken uvicorn app:app --reload
```

Or with no model at all (verified template analysis): `LLM_BACKEND=template uvicorn app:app --reload`.

## Deploy it

A 3 GB model doesn't fit on free hosting tiers, so the cloud deployment runs the same app with the model served by Hugging Face (`LLM_BACKEND=hf_api`). The deployed app installs only `requirements.txt` (no PyTorch), so it builds in about a minute.

### Render (free, deploys from GitHub)

1. Create a free Hugging Face token: huggingface.co, then **Settings → Access Tokens → Create new token** (type "Read" is enough; make sure it can call Inference Providers).
2. Push this repo to GitHub.
3. On [render.com](https://render.com), sign in with GitHub and choose **New → Blueprint**, then pick this repository. Render reads `render.yaml`.
4. When asked for `HF_TOKEN`, paste your token, then click **Apply**.
5. After the build, open the `.onrender.com` URL. Check `/api/health`: it should report `"backend": "hf_api"`.

Every push to `main` redeploys automatically. On the free plan the app sleeps after 15 minutes without visits, and the first visit after that takes about a minute to wake it.

If analyses always fall back to the template, the chosen model may not be served for your account. Open the model's page on Hugging Face, check the **Inference Providers** panel, and set `HF_MODEL` on Render to a model that is served there.

### Docker (any host)

```bash
docker build -t called-it .
docker run -p 8000:8000 -e LLM_BACKEND=hf_api -e HF_TOKEN=hf_yourtoken called-it
```

To run the open-source model inside the container instead (needs about 6 GB of RAM), build with `--build-arg LOCAL_MODEL=1` and run with `-e LLM_BACKEND=local`. This also works on Hugging Face Spaces (Docker Space, free 16 GB CPU), where the app should listen on port 7860: add `-e PORT=7860`, or set `PORT=7860` in the Space's variables.

## Configuration

All settings are environment variables. Never commit tokens: set them on the host.

| Variable | Default | Meaning |
| --- | --- | --- |
| `LLM_BACKEND` | `auto` | `local`, `hf_api`, `template`, or `auto` (local if PyTorch is installed, else `hf_api` if `HF_TOKEN` is set, else template) |
| `HF_MODEL` | Qwen2.5-1.5B-Instruct (local), Qwen2.5-7B-Instruct (API) | Any chat model on the Hugging Face Hub |
| `HF_TOKEN` | none | Hugging Face token, needed for `hf_api` |
| `GROUNDING_POLICY` | `reject` | `reject` replaces drafts that fail the check; `flag` shows them with a warning |
| `ANALYSIS_MAX_TOKENS` | `450` | Upper limit on the length of an analysis |
| `ANALYSIS_CACHE` | `analysis_cache.json` | Where finished analyses are saved |
| `WARM_MODEL` | `1` | Load the local model at startup (`0` to load on first use) |
| `PORT` | `8000` (Docker) | Port for the container or host |

## Scoring (Match IQ)

| Part | Points | Why |
| --- | --- | --- |
| Called before the deadline | 10 | Rewards committing under the same pressure as the captain |
| Situation read | 0–20 | How well the pick suits this over on the data: Bumrah 20, Kuldeep 13, Arshdeep 11, Hardik 6 |
| Reason fits the data | 5 | The stated reason must be true for that bowler |
| Same call as the captain | 15 | Agreement with an expert matters, but isn't most of the score |
| Result of the over | 0 | One over is mostly luck |

Late or missing calls score 0. Example: Kuldeep with "Matchup edge" scores 10 + 13 + 5 + 0 = 28, taking Match IQ from 612 to 640.

## API

Interactive docs are served at `/docs`.

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/api/rounds/current?fan_id=` | Current round, as this fan may see it |
| POST | `/api/rounds` | Start a new round (replay) |
| POST | `/api/rounds/{id}/picks` | `{fan_id, option, reason}`; the server decides if it was on time |
| POST | `/api/rounds/{id}/lock` | Lock early |
| POST | `/api/rounds/{id}/skip` | Demo only: close the window now for everyone |
| POST | `/api/rounds/{id}/analysis` | AI analysis for this fan (after the over) |
| POST | `/api/rounds/{id}/ask` | `{fan_id, question}`: follow-up question |
| GET | `/api/rounds/{id}/iq?fan_id=` | Match IQ breakdown |
| GET | `/api/health` | Which model backend is active |

## Tests

```bash
pip install -r requirements-dev.txt
pytest -q
```

The 13 tests use a fake clock and a fake model, so they need no download and run in about a second. They cover the deadline and lock rules, that nothing leaks early, scoring, rejection of invented statistics and fake citations, fallback when the model fails, background prefetch, shared jobs, the disk cache, and the full API flow. GitHub Actions runs them on every push (`.github/workflows/tests.yml`).

## Project layout

```
app.py                     FastAPI app and routes
called_it/scenario.py      the scenario, options, the over and the data pack
called_it/rounds.py        server-side rounds, deadline, reveal timeline
called_it/scoring.py       Match IQ scoring and decision-profile insights
called_it/analyst.py       Hugging Face model backends, prompts, grounding check, cache
templates/index.html       the fan-facing web app
tests/test_called_it.py    test suite
warm_cache.py              pre-generates every analysis for an instant demo
requirements.txt           web app only (cloud deploys)
requirements-local.txt     + PyTorch and transformers to run the model locally
requirements-dev.txt       + pytest
Dockerfile, render.yaml    deployment
docs/screenshots/          images used in this README
```

## Data note

The fixture, scores and player statistics are illustrative sample values written for this prototype, not official records. In production, `scenario.py` would be fed by a live match feed and a stats provider. Rounds are held in memory, so restarting the server clears them.
