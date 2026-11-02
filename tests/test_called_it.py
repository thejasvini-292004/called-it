import json

import pytest
from fastapi.testclient import TestClient

from app import create_app
from called_it import scenario as sc
from called_it.analyst import Analyst, extract_json, grounding_check, normalise_citations, template_analysis
from called_it.rounds import RoundError, RoundStore
from called_it.scoring import score_call


class Clock:
    def __init__(self, t=1_000_000.0):
        self.t = t

    def __call__(self):
        return self.t


class FakeModel:
    """Stands in for a Hugging Face model: returns whatever text we give it."""
    kind = "local"
    model_id = "fake/test-model"
    ready = True

    def __init__(self, reply):
        self.reply = reply
        self.calls = 0

    def load(self):
        pass

    def generate(self, messages, max_new_tokens=700):
        self.calls += 1
        if isinstance(self.reply, Exception):
            raise self.reply
        return self.reply


GOOD = {
    "fan": "You played the matchup: David strikes at 118 against spin [D7] and Kuldeep has dismissed him once [D12].",
    "captain": "Bumrah offers control with a death economy of 6.9 [D3], with 32 needed off 18 [D1].",
    "tradeoff": "Spin risks boundaries, 17% at the death [D5], and the ball is wet [D10]. There is no data on Kuldeep against Stoinis [D13].",
    "outcome": "Bumrah's over cost 6 runs and took a wicket [D14]. We can't know how Kuldeep's over would have gone.",
    "takeaway": "A defensible call with a real matchup behind it.",
}


def after_over(clock):
    clock.t += sc.DEADLINE_SECONDS + sc.OVER_STARTS_AFTER + sc.BALL_INTERVAL * len(sc.OVER) + 1


# ---------------------------------------------------------------- fairness rules

def test_same_deadline_and_late_picks_not_scored():
    clock = Clock(); store = RoundStore(clock); r = store.create()
    r.submit("fan_a", "kuldeep", "matchup", clock())
    r.submit("fan_a", "bumrah", None, clock())          # can change before the deadline
    assert r.picks["fan_a"].option == "bumrah"
    r.lock("fan_a", clock())
    with pytest.raises(RoundError):
        r.submit("fan_a", "hardik", None, clock())        # locked early
    clock.t += sc.DEADLINE_SECONDS + 0.1
    with pytest.raises(RoundError):
        r.submit("fan_a", "kuldeep", None, clock())       # window closed
    late = r.submit("fan_b", "kuldeep", None, clock())
    assert late.on_time is False
    assert score_call("kuldeep", None, on_time=False)["total"] == 0


def test_captain_and_result_hidden_until_due():
    clock = Clock(); store = RoundStore(clock); r = store.create()
    s = r.public_state("x", clock())
    assert s["phase"] == "open" and s["captain_choice"] is None and s["crowd"] is None
    assert all(d["id"] != "D14" for d in s["data_pack"])
    clock.t += sc.DEADLINE_SECONDS + 0.5
    assert r.public_state("x", clock())["captain_choice"] is None      # closed, not yet revealed
    clock.t += sc.REVEAL_AFTER
    assert r.public_state("x", clock())["captain_choice"] == "bumrah"
    after_over(clock)
    s = r.public_state("x", clock())
    assert s["phase"] == "done" and len(s["balls"]) == 6 and any(d["id"] == "D14" for d in s["data_pack"])


def test_scoring_rewards_the_call_not_the_result():
    assert score_call("kuldeep", "matchup", True)["total"] == 10 + 13 + 5 + 0
    assert score_call("bumrah", "control", True)["total"] == 50
    assert score_call("bumrah", "save", True)["total"] == 45   # reason contradicts the data
    assert score_call(None, None, False)["total"] == 0

# ---------------------------------------------------------------- AI analyst

def test_template_analysis_is_itself_grounded():
    for p in [None, *sc.ORDER]:
        assert grounding_check(template_analysis(p))["passed"], p


def test_grounded_llm_draft_is_used():
    a = Analyst(FakeModel("Sure! ```json\n" + json.dumps(GOOD) + "\n```"))
    out = a.analyse("kuldeep", "matchup", True)
    assert out["source"] == "llm" and out["check"]["passed"] and out["model"] == "fake/test-model"


def test_hallucinated_stat_is_rejected(monkeypatch):
    bad = dict(GOOD, captain="Bumrah has taken 23 death wickets this year at an economy of 6.2 [D3].")
    out = Analyst(FakeModel(json.dumps(bad))).analyse("kuldeep", "matchup", True)
    assert out["source"] == "template" and "23" in out["note"] and "6.2" in out["note"]
    monkeypatch.setenv("GROUNDING_POLICY", "flag")
    out = Analyst(FakeModel(json.dumps(bad))).analyse("kuldeep", "matchup", True)
    assert out["source"] == "llm" and not out["check"]["passed"]


def test_bad_output_and_errors_fall_back():
    assert Analyst(FakeModel("I think Bumrah is great.")).analyse("bumrah", None, True)["source"] == "template"
    assert Analyst(FakeModel(OSError("no network"))).analyse("bumrah", None, True)["source"] == "template"
    out = Analyst(FakeModel(json.dumps(dict(GOOD, fan="Great pick [D99].")))).analyse("kuldeep", None, True)
    assert out["source"] == "template" and "D99" in out["note"]


def test_citation_normalisation_and_json_extraction():
    assert normalise_citations("economy 6.9 (D3) and D7, see [D4, D5]") == "economy 6.9 [D3] and [D7], see [D4][D5]"
    assert extract_json('noise {"a": "b",} tail') == {"a": "b"}


def test_question_with_invented_numbers_is_withheld():
    out = Analyst(FakeModel("Stoinis averages 41.5 against spin.")).ask("How does Stoinis play spin?", "kuldeep")
    assert out["source"] == "withheld"
    out = Analyst(FakeModel("There is no data on Stoinis against spin [D13].")).ask("How does Stoinis play spin?", None)
    assert out["source"] == "llm"

# ---------------------------------------------------------------- API end to end

def test_api_flow():
    clock = Clock(); model = FakeModel(json.dumps(GOOD))
    client = TestClient(create_app(RoundStore(clock), Analyst(model)))
    s = client.get("/api/rounds/current", params={"fan_id": "fan_1"}).json()
    rid = s["round_id"]
    assert s["phase"] == "open" and s["remaining"] == sc.DEADLINE_SECONDS
    s = client.post(f"/api/rounds/{rid}/picks", json={"fan_id": "fan_1", "option": "kuldeep", "reason": "matchup"}).json()
    assert s["your_pick"]["on_time"] is True
    assert client.post(f"/api/rounds/{rid}/analysis", json={"fan_id": "fan_1"}).status_code == 409
    client.post(f"/api/rounds/{rid}/lock", json={"fan_id": "fan_1"})
    assert client.post(f"/api/rounds/{rid}/picks", json={"fan_id": "fan_1", "option": "bumrah"}).status_code == 409
    after_over(clock)
    an = client.post(f"/api/rounds/{rid}/analysis", json={"fan_id": "fan_1"}).json()
    assert an["source"] == "llm"
    client.post(f"/api/rounds/{rid}/analysis", json={"fan_id": "fan_1"})
    assert model.calls == 1                                        # cached
    iq = client.get(f"/api/rounds/{rid}/iq", params={"fan_id": "fan_1"}).json()
    assert iq["after"] == 612 + 28
    assert client.get("/").status_code == 200

# ---------------------------------------------------------------- speed: prefetch, sharing, disk cache

class SlowModel(FakeModel):
    def __init__(self, reply, delay):
        super().__init__(reply); self.delay = delay

    def generate(self, messages, max_new_tokens=700):
        import time as _t
        _t.sleep(self.delay)
        return super().generate(messages, max_new_tokens)


def test_prefetch_runs_once_and_request_waits_for_it():
    import time as _t
    model = SlowModel(json.dumps(GOOD), delay=0.5)
    a = Analyst(model)
    a.prefetch("kuldeep", "matchup", True)          # call locks: generation starts in the background
    a.prefetch("kuldeep", "matchup", True)          # a second trigger doesn't start a second job
    _t.sleep(0.3)
    t0 = _t.time()
    out = a.analyse("kuldeep", "matchup", True)     # fan asks while it's still being written
    assert out["source"] == "llm" and out["prepared_early"] is True
    assert _t.time() - t0 < 0.45                    # waited only for the remainder
    assert model.calls == 1
    again = a.analyse("kuldeep", "matchup", True)
    assert again["cached"] is True and model.calls == 1


def test_disk_cache_survives_restart(tmp_path):
    path = tmp_path / "cache.json"
    first = FakeModel(json.dumps(GOOD))
    Analyst(first, cache_file=str(path)).analyse("kuldeep", "matchup", True)
    assert path.exists() and first.calls == 1
    second = FakeModel(json.dumps(GOOD))
    out = Analyst(second, cache_file=str(path)).analyse("kuldeep", "matchup", True)
    assert out["cached"] is True and second.calls == 0


def test_error_result_is_handed_over_then_retried():
    import time as _t
    model = FakeModel(OSError("offline"))
    a = Analyst(model)
    a.prefetch("bumrah", None, True); _t.sleep(0.1)
    assert a.analyse("bumrah", None, True)["source"] == "template"   # fan gets the fallback, no second wait
    assert model.calls == 1
    a.analyse("bumrah", None, True)                                  # next request retries the model
    assert model.calls == 2
