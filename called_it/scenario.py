"""The one scenario this prototype runs: who bowls over 18 of Australia's chase.

Everything the AI analyst may say comes from DATA_PACK. The values are
illustrative sample data for the prototype, not official records. In
production this module would be replaced by the live match feed and a
stats provider.
"""

SCENARIO_ID = "ind-aus-t20-over18"
TITLE = "Who bowls the 18th?"
SUMMARY = (
    "AUS need 32 off 18. Bumrah, Arshdeep and Kuldeep have one over each; "
    "Hardik has two. Pick before the bowler starts his run-up."
)

DEADLINE_SECONDS = 30          # same window for every fan
REVEAL_AFTER = 2.0             # seconds after deadline until captain's call arrives
OVER_STARTS_AFTER = 5.0        # seconds after deadline until ball 1
BALL_INTERVAL = 1.5            # seconds between balls

CAPTAIN_CHOICE = "bumrah"

OPTIONS = {
    "bumrah":   {"name": "Jasprit Bumrah", "short": "Bumrah",   "init": "JB", "role": "Right-arm fast",
                 "left": "1 over left",  "today": "3-0-18-1", "econ": 6.9,  "dot": 41, "bdry": 9,  "spin": False},
    "arshdeep": {"name": "Arshdeep Singh", "short": "Arshdeep", "init": "AS", "role": "Left-arm fast",
                 "left": "1 over left",  "today": "3-0-27-1", "econ": 8.9,  "dot": 33, "bdry": 15, "spin": False},
    "kuldeep":  {"name": "Kuldeep Yadav",  "short": "Kuldeep",  "init": "KY", "role": "Left-arm wrist spin",
                 "left": "1 over left",  "today": "3-0-22-2", "econ": 9.4,  "dot": 30, "bdry": 17, "spin": True},
    "hardik":   {"name": "Hardik Pandya",  "short": "Hardik",   "init": "HP", "role": "Right-arm fast-medium",
                 "left": "2 overs left", "today": "2-0-19-0", "econ": 10.1, "dot": 28, "bdry": 18, "spin": False},
}
ORDER = ["bumrah", "arshdeep", "kuldeep", "hardik"]

REASONS = {
    "matchup": "Matchup edge",
    "control": "Control the over",
    "wicket": "Hunt a wicket",
    "save": "Save a bowler for later",
}

# Simulated crowd split, shown alongside real picks made in this server.
SIMULATED_CROWD = {"bumrah": 54, "kuldeep": 21, "arshdeep": 17, "hardik": 8}
SIMULATED_FANS = 48210

OVER = [
    {"ball": "17.1", "runs": 0,   "text": "Bumrah to David. Yorker on off stump, dug out to cover. No run.", "angle": None},
    {"ball": "17.2", "runs": 1,   "text": "Full on the pads, David works it to deep square leg for one.", "angle": 95, "dist": 0.78},
    {"ball": "17.3", "runs": 4,   "text": "Low full toss to Stoinis, flicked fine. Four.", "angle": 158, "dist": 0.86},
    {"ball": "17.4", "runs": 0,   "text": "Slower ball. Stoinis swings across the line and misses.", "angle": None},
    {"ball": "17.5", "runs": "W", "text": "Yorker at 146 km/h. Stoinis is bowled. AUS 153-6.", "angle": None},
    {"ball": "17.6", "runs": 1,   "text": "Wade pushes to long-off for a single.", "angle": 338, "dist": 0.72},
]

DATA_PACK = [
    {"id": "D1",  "label": "Match state", "fact": "AUS 148-5 after 17 overs, chasing 180. Need 32 off 18 balls. Required rate 10.67."},
    {"id": "D2",  "label": "Overs left", "fact": "Bumrah 1, Arshdeep 1, Kuldeep 1, Hardik 2. India must bowl overs 18, 19 and 20."},
    {"id": "D3",  "label": "Bumrah, overs 16-20", "fact": "Economy 6.9, dot balls 41%, boundary balls 9% (T20Is since 2024)."},
    {"id": "D4",  "label": "Arshdeep, overs 16-20", "fact": "Economy 8.9, dot balls 33%, boundary balls 15% (T20Is since 2024)."},
    {"id": "D5",  "label": "Kuldeep, overs 16-20", "fact": "Economy 9.4, dot balls 30%, boundary balls 17%. Small sample: 14 overs."},
    {"id": "D6",  "label": "Hardik, overs 16-20", "fact": "Economy 10.1, dot balls 28%, boundary balls 18% (T20Is since 2024)."},
    {"id": "D7",  "label": "Tim David by bowling type", "fact": "Strike rate 118 against spin, 178 against pace (T20s since 2024)."},
    {"id": "D8",  "label": "Batters now", "fact": "David 24 off 12 balls, on strike. Stoinis 18 off 14 balls."},
    {"id": "D9",  "label": "Bowling today", "fact": "Bumrah 3-0-18-1, Arshdeep 3-0-27-1, Kuldeep 3-0-22-2, Hardik 2-0-19-0."},
    {"id": "D10", "label": "Conditions", "fact": "Heavy dew since over 12. The ball is wet, which usually makes grip harder for spinners."},
    {"id": "D11", "label": "Bumrah v David", "fact": "15 balls, 19 runs, 1 dismissal."},
    {"id": "D12", "label": "Kuldeep v David", "fact": "9 balls, 7 runs, 1 dismissal."},
    {"id": "D13", "label": "Missing data", "fact": "No head-to-head records for Arshdeep or Hardik against David, and none for any bowler against Stoinis."},
    {"id": "D14", "label": "Over 18 result", "after_over": True,
     "fact": "Bowled by Bumrah: 0, 1, 4, 0, W (Stoinis bowled), 1. 6 runs, 1 wicket. AUS 154-6 after 18 overs, need 26 off 12."},
]


def data_pack(include_result: bool) -> list[dict]:
    """The pack as a fan may see it: the over's result is withheld until it is bowled."""
    return [d for d in DATA_PACK if include_result or not d.get("after_over")]


def data_pack_text(include_result: bool = True) -> str:
    return "\n".join(f"[{d['id']}] {d['label']}: {d['fact']}" for d in data_pack(include_result))
