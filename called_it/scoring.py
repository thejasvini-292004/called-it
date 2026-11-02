"""Match IQ scoring. It scores the quality of the call, never the result of the over."""

from .scenario import CAPTAIN_CHOICE, OPTIONS, REASONS

BASE_IQ = 612
MAX_POINTS = 50

# Does the fan's stated reason hold up in the data pack for the bowler they picked?
REASON_FIT = {
    "bumrah": {
        "matchup": (True, "David has 19 runs off 15 balls against Bumrah [D11]."),
        "control": (True, "Best death economy in the pack, 6.9 [D3]."),
        "wicket":  (True, "Has dismissed David once [D11] and has a wicket today [D9]."),
        "save":    (False, "Bowling Bumrah now spends his last over [D2]."),
    },
    "kuldeep": {
        "matchup": (True, "David strikes at 118 against spin [D7]."),
        "control": (False, "Kuldeep's death economy is 9.4 [D5], and the ball is wet [D10]."),
        "wicket":  (True, "Two wickets today [D9] and has dismissed David once [D12]."),
        "save":    (True, "Keeps Bumrah's last over for the 19th or 20th [D2]."),
    },
    "arshdeep": {
        "matchup": (False, "No head-to-head data for Arshdeep against these batters [D13]."),
        "control": (False, "Death economy 8.9 [D4]; Bumrah's is 6.9 [D3]."),
        "wicket":  (False, "One wicket today and no head-to-head data [D9][D13]."),
        "save":    (True, "Keeps Bumrah's last over for later [D2]."),
    },
    "hardik": {
        "matchup": (False, "No head-to-head data for Hardik against these batters [D13]."),
        "control": (False, "Weakest death economy in the pack, 10.1 [D6]."),
        "wicket":  (False, "No wicket today [D9]."),
        "save":    (True, "Hardik has two overs, so Bumrah and Arshdeep stay available [D2]."),
    },
}

# How well each option fits this over on the data pack alone (0-20).
SITUATION_READ = {"bumrah": 20, "kuldeep": 13, "arshdeep": 11, "hardik": 6}
SITUATION_WHY = {
    "bumrah": "Best economy, dot and boundary rates at the death [D3].",
    "kuldeep": "Strong matchup against David [D7], offset by a small sample and dew [D5][D10].",
    "arshdeep": "Second-best death numbers [D4], no matchup data [D13].",
    "hardik": "Weakest death numbers of the four [D6].",
}

SKILLS_BEFORE = {"death": 58, "matchup": 71, "resource": 44, "pressure": 62}
SKILL_LABELS = {"death": "Death-over reads", "matchup": "Matchup reading",
                "resource": "Resource planning", "pressure": "Pressure calls"}


def score_call(pick: str | None, reason: str | None, on_time: bool) -> dict:
    if not pick:
        return {"total": 0, "rows": [], "note": "No call before the deadline, so nothing to score this time."}
    if not on_time:
        return {"total": 0, "rows": [], "note": "You picked after the deadline. The call is saved for your learning "
                                                "history but does not count toward Match IQ."}
    same = pick == CAPTAIN_CHOICE
    fit = REASON_FIT[pick].get(reason) if reason else None
    rows = [
        {"label": "Called before the deadline", "why": "Same window as every other fan.", "points": 10, "max": 10},
        {"label": "Situation read", "why": SITUATION_WHY[pick], "points": SITUATION_READ[pick], "max": 20},
        {"label": "Reason fits the data",
         "why": f"{REASONS[reason]}: {fit[1]}" if fit else "No reason picked.",
         "points": 5 if fit and fit[0] else 0, "max": 5},
        {"label": "Same call as the captain",
         "why": "You and the captain both chose Bumrah." if same
         else f"You chose {OPTIONS[pick]['short']}; the captain chose Bumrah.",
         "points": 15 if same else 0, "max": 15},
        {"label": "Result of the over",
         "why": "Not scored. One over is mostly luck, and the over you picked may never have been bowled.",
         "points": None, "max": None},
    ]
    return {"total": sum(r["points"] or 0 for r in rows), "rows": rows}


def skills_after(pick: str | None, reason: str | None, on_time: bool) -> dict:
    s = dict(SKILLS_BEFORE)
    if not pick or not on_time:
        return s
    s["death"] += round(SITUATION_READ[pick] / 4) - 2
    if reason == "matchup":
        s["matchup"] += 5 if REASON_FIT[pick]["matchup"][0] else -3
    if reason == "save":
        s["resource"] += 6 if REASON_FIT[pick]["save"][0] else -4
    elif pick != "bumrah":
        s["resource"] += 3
    s["pressure"] += 4 if pick == CAPTAIN_CHOICE else 1
    return {k: max(0, min(100, v)) for k, v in s.items()}


def insights(pick: str | None, on_time: bool) -> list[dict]:
    out = [{"kind": "strength", "text": "Matchup reading. You spot batter-versus-bowler edges, and they usually "
                                        "hold up in the data."}]
    p = pick if on_time else None
    if p == "bumrah":
        out += [{"kind": "strength", "text": "Pressure overs. You backed the most reliable death bowler when the "
                                             "chase was live."},
                {"kind": "watch", "text": "Planning ahead. Spending your best bowler early leaves weaker options for "
                                          "the last two overs; ask who bowls the 20th before you commit."}]
    elif p == "kuldeep":
        out += [{"kind": "strength", "text": "You thought two overs ahead by keeping Bumrah back."},
                {"kind": "watch", "text": "Conditions. Dew and small samples can turn a good matchup into a risky "
                                          "over. Check them before backing spin at the death."}]
    elif p in ("arshdeep", "hardik"):
        out += [{"kind": "strength", "text": "Resource planning. You kept your best bowler for later."},
                {"kind": "watch", "text": "Timing. In a live chase, the over in front of you can matter more than "
                                          "the last one. Weigh both before saving your best."}]
    else:
        out.append({"kind": "watch", "text": "Make the call in time. On-time calls are the only ones that build "
                                             "your Match IQ."})
    return out


def match_iq(pick, reason, on_time) -> dict:
    sc = score_call(pick, reason, on_time)
    return {
        "before": BASE_IQ, "after": BASE_IQ + sc["total"], "max_points": MAX_POINTS,
        "score": sc, "skills_before": SKILLS_BEFORE, "skills_after": skills_after(pick, reason, on_time),
        "skill_labels": SKILL_LABELS, "insights": insights(pick, on_time),
    }
