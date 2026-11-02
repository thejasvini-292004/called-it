"""Decision rounds. The server's clock is the only clock that counts.

Every fan in a round sees the same scenario and the same deadline. A pick made
before the deadline can be changed until the deadline (or until the fan locks
it early). A pick made after the deadline is stored as late and never scored.
The captain's call and the over are released on a fixed timeline after the
deadline, so nobody can see the captain's decision before their own call locks.
"""

from __future__ import annotations

import math
import threading
import time
import uuid
from dataclasses import dataclass, field

from . import scenario as sc


class RoundError(Exception):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


@dataclass
class Pick:
    option: str
    reason: str | None
    at: float
    on_time: bool
    locked_early_at: float | None = None


@dataclass
class Round:
    id: str
    opened_at: float
    deadline_at: float
    picks: dict[str, Pick] = field(default_factory=dict)
    events: list[dict] = field(default_factory=list)

    # ----- timeline -----
    def balls_bowled(self, now: float) -> int:
        start = self.deadline_at + sc.OVER_STARTS_AFTER
        if now < start:
            return 0
        return min(len(sc.OVER), int((now - start) // sc.BALL_INTERVAL) + 1)

    def phase(self, now: float) -> str:
        if now < self.deadline_at:
            return "open"
        if now < self.deadline_at + sc.REVEAL_AFTER:
            return "closed"
        if now < self.deadline_at + sc.OVER_STARTS_AFTER:
            return "reveal"
        return "done" if self.balls_bowled(now) >= len(sc.OVER) else "playing"

    def log(self, now: float, msg: str) -> None:
        self.events.append({"t": now, "msg": msg})

    # ----- fan actions -----
    def submit(self, fan_id: str, option: str, reason: str | None, now: float) -> Pick:
        if option not in sc.OPTIONS:
            raise RoundError(f"Unknown option '{option}'.")
        if reason is not None and reason not in sc.REASONS:
            raise RoundError(f"Unknown reason '{reason}'.")
        existing = self.picks.get(fan_id)
        if now < self.deadline_at:
            if existing and existing.locked_early_at is not None:
                raise RoundError("Your call is locked.", 409)
            self.picks[fan_id] = Pick(option, reason, now, True)
            return self.picks[fan_id]
        if existing:
            raise RoundError("The decision window has closed. Your call is locked.", 409)
        pick = Pick(option, reason, now, False)
        self.picks[fan_id] = pick
        self.log(now, f"Late call recorded after the deadline: {sc.OPTIONS[option]['short']}. Not scored.")
        return pick

    def lock(self, fan_id: str, now: float) -> Pick:
        pick = self.picks.get(fan_id)
        if not pick:
            raise RoundError("Pick a bowler before locking.")
        if now >= self.deadline_at:
            raise RoundError("The window has already closed.", 409)
        if pick.locked_early_at is None:
            pick.locked_early_at = now
            self.log(now, f"A fan locked {sc.OPTIONS[pick.option]['short']} "
                          f"{math.ceil(self.deadline_at - now)}s before the deadline.")
        return pick

    def skip_to_deadline(self, now: float) -> None:
        """Demo control: close the window now for everyone in this round."""
        if now < self.deadline_at:
            self.deadline_at = now
            self.log(now, "Demo: deadline brought forward.")

    # ----- views -----
    def crowd(self) -> dict:
        real = {k: 0 for k in sc.ORDER}
        for p in self.picks.values():
            if p.on_time:
                real[p.option] += 1
        return {"simulated_pct": sc.SIMULATED_CROWD, "simulated_fans": sc.SIMULATED_FANS,
                "real_counts": real, "real_fans": sum(real.values())}

    def public_state(self, fan_id: str | None, now: float) -> dict:
        phase = self.phase(now)
        after_deadline = phase != "open"
        captain_known = phase in ("reveal", "playing", "done")
        balls = self.balls_bowled(now)
        done = phase == "done"
        pick = self.picks.get(fan_id) if fan_id else None
        events = list(self.timeline_events(now)) + self.events
        events.sort(key=lambda e: e["t"])
        return {
            "round_id": self.id,
            "scenario": {"id": sc.SCENARIO_ID, "title": sc.TITLE, "summary": sc.SUMMARY},
            "phase": phase,
            "server_now": now,
            "deadline_at": self.deadline_at,
            "deadline_seconds": sc.DEADLINE_SECONDS,
            "remaining": max(0.0, self.deadline_at - now),
            "options": sc.OPTIONS, "order": sc.ORDER, "reasons": sc.REASONS,
            "your_pick": None if not pick else {
                "option": pick.option, "reason": pick.reason, "on_time": pick.on_time,
                "locked_early": pick.locked_early_at is not None,
                "locked_with_seconds_left": None if pick.locked_early_at is None
                else math.ceil(self.deadline_at - pick.locked_early_at),
            },
            "captain_choice": sc.CAPTAIN_CHOICE if captain_known else None,
            "crowd": self.crowd() if after_deadline else None,
            "balls": sc.OVER[:balls],
            "score": {"ind": "179-6", "aus": "154-6" if done else "148-5", "aus_overs": "18.0" if done else "17.0",
                      "need": "26 off 12" if done else "32 off 18", "rrr": "13.00" if done else "10.67"},
            "data_pack": sc.data_pack(include_result=done),
            "events": [{"t": e["t"], "msg": e["msg"]} for e in events if e["t"] <= now],
        }

    def timeline_events(self, now: float):
        yield {"t": self.opened_at, "msg": "Situation detected: death over, chase. Over 18 decision opened for all fans."}
        yield {"t": self.opened_at, "msg": f"Deadline set: bowler's run-up, {sc.DEADLINE_SECONDS}s from now."}
        yield {"t": self.deadline_at, "msg": "Decision window closed for everyone."}
        yield {"t": self.deadline_at + sc.REVEAL_AFTER,
               "msg": "Captain's call received from match feed: Bumrah to bowl over 18."}
        for i, b in enumerate(sc.OVER):
            t = self.deadline_at + sc.OVER_STARTS_AFTER + i * sc.BALL_INTERVAL
            r = b["runs"]
            yield {"t": t, "msg": f"{b['ball']}: " + ("Wicket" if r == "W" else f"{r} run" + ("" if r == 1 else "s"))}
        yield {"t": self.deadline_at + sc.OVER_STARTS_AFTER + (len(sc.OVER) - 1) * sc.BALL_INTERVAL,
               "msg": "Over complete: 6 runs, 1 wicket. AUS need 26 off 12. Analysis unlocked."}


class RoundStore:
    def __init__(self, clock=time.time):
        self.clock = clock
        self._rounds: dict[str, Round] = {}
        self._lock = threading.Lock()
        self.current_id: str | None = None

    def create(self) -> Round:
        now = self.clock()
        with self._lock:
            r = Round(id=uuid.uuid4().hex[:10], opened_at=now, deadline_at=now + sc.DEADLINE_SECONDS)
            self._rounds[r.id] = r
            self.current_id = r.id
            return r

    def current(self) -> Round:
        with self._lock:
            r = self._rounds.get(self.current_id) if self.current_id else None
        return r or self.create()

    def get(self, round_id: str) -> Round:
        r = self._rounds.get(round_id)
        if not r:
            raise RoundError("Round not found.", 404)
        return r

    def run(self, round_id: str, fn):
        """Run a mutation on a round under the store lock."""
        r = self.get(round_id)
        with self._lock:
            return fn(r, self.clock())
