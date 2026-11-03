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
- [Run it locally](#run-it-locally)
- [Deploy it](#deploy-it)
- [Scoring](#scoring-match-iq)
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


## Run it locally

Requires Python 3.10 or newer.

```bash
git clone https://github.com/thejasvini-292004/called-it.git
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

## Scoring (Match IQ)

| Part | Points | Why |
| --- | --- | --- |
| Called before the deadline | 10 | Rewards committing under the same pressure as the captain |
| Situation read | 0–20 | How well the pick suits this over on the data: Bumrah 20, Kuldeep 13, Arshdeep 11, Hardik 6 |
| Reason fits the data | 5 | The stated reason must be true for that bowler |
| Same call as the captain | 15 | Agreement with an expert matters, but isn't most of the score |
| Result of the over | 0 | One over is mostly luck |

Late or missing calls score 0. Example: Kuldeep with "Matchup edge" scores 10 + 13 + 5 + 0 = 28, taking Match IQ from 612 to 640.

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
