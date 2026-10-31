"""Key-text coverage (min_coverage): synthetic readings and synthetic ffmpeg media with a FAKE observer.
These tests check grid/decision/plumbing logic, not perception accuracy."""
from __future__ import annotations

import json
import shutil
import subprocess
import uuid

import pytest
from pydantic import ValidationError

from proofframe.interfaces import AssetInput
from proofframe.verify.compare import FrameReading, coverage_grid, decide_coverage
from proofframe.verify.pipeline import run_verification
from proofframe.verify.plan import RunPlan, Workload, estimate
from proofframe_contracts.models import Contract, ObservationSpec, fingerprint
from tests.test_core_pipeline import CONTRACT, CapBudget, DirStore

HAS_FFMPEG = shutil.which("ffmpeg") is not None
EXP = "Old lamp off. New lamp on!"


def readings(values, *, step=250):
    """values: approved text, other text, "" (clearly no text), None (not visible), "?" (partial)."""
    out = []
    for i, v in enumerate(values):
        visible, vis, val = True, "clear", v
        if v is None:
            visible, vis, val = False, "not_visible", ""
        elif v == "?":
            vis, val = "partial", ""
        out.append(FrameReading(label=f"F{i + 1}", evidence_id=f"ev-{i}", t_ms=i * step,
                                subject_visible=visible, visibility=vis, value=val))
    return out


def run(values, min_coverage=0.9, sampled=None):
    frames = readings(values)
    return decide_coverage("exact_text_nfc", EXP, frames, sampled=sampled or len(frames),
                           min_coverage=min_coverage, localized_values=[])


def test_grid_is_uniform_and_bounded():
    assert coverage_grid(0, 1000) == [125, 375, 625, 875]            # minimum 4 frames
    assert len(coverage_grid(0, 3000)) == 12                          # one per 250 ms
    assert len(coverage_grid(0, 60_000)) == 16                        # cap
    g = coverage_grid(10_000, 13_000)
    assert g[0] > 10_000 and g[-1] < 13_000 and len(set(g)) == len(g)


def test_full_coverage_passes_and_one_gap_in_twelve_still_passes():
    v, cov = run([EXP] * 12)
    assert v.status == "PASS" and cov.fraction_low == 1.0
    v, cov = run([None] + [EXP] * 11)                                 # 11/12 = 92 %
    assert v.status == "PASS" and cov.first_match_ms == 250


def test_caption_late_or_early_off_fails_with_times():
    v, cov = run([None, None, None] + [EXP] * 9)                      # appears 0.75 s late: 75 %
    assert v.status == "FAIL" and cov.missing_ms == (0, 250, 500)
    assert "missing at 0.00s, 0.25s, 0.50s" in v.rationale
    v, _ = run([EXP] * 9 + ["", "", ""])                              # clearly gone for the last 3 frames
    assert v.status == "FAIL"


def test_unreadable_and_misread_frames_never_fail_and_never_pass():
    v, cov = run([EXP] * 9 + ["?", "?", "?"])                         # upper bound 100 %: cannot FAIL
    assert v.status == "UNCERTAIN" and cov.fraction_high == 1.0
    v, cov = run([EXP] * 9 + ["Old lamp off. New lmap on!"] * 3)   # misread, not proven absent
    assert v.status == "UNCERTAIN" and cov.contradicted == 3
    v, _ = run([EXP] * 11 + ["Old lamp off."])                     # a differing frame blocks PASS
    assert v.status == "UNCERTAIN"
    v, cov = run([EXP] * 6, sampled=12)                               # frames the model did not return
    assert v.status == "UNCERTAIN" and cov.unreadable == 6


def test_never_seen_is_uncertain_but_consistent_wrong_text_fails():
    v, _ = run([None] * 12)
    assert v.status == "UNCERTAIN"
    v, _ = run(["New lamp on!"] * 12)                                # wrong sentence held all line
    assert v.status == "FAIL"


def _contract(min_coverage):
    c = json.loads(json.dumps(CONTRACT))
    cap = next(a for a in c["assertions"] if a["assertion_id"] == "caption-01")
    cap["observation"]["min_coverage"] = min_coverage
    c["assertions"] = [cap]
    return c


def test_schema_rules_and_fingerprint_stability():
    base = fingerprint(Contract.model_validate(CONTRACT))
    assert base == "c633262697111248d3f540c7920b0c1be5654b81009d58aa22b312c9eb1acc58"
    assert "min_coverage" not in json.dumps(Contract.model_validate(CONTRACT).model_dump(mode="json"))
    assert Contract.model_validate(_contract(0.9))
    for bad in (0, 1.5, float("nan")):
        with pytest.raises(ValidationError):
            Contract.model_validate(_contract(bad))
    with pytest.raises(ValidationError):
        ObservationSpec(kind="on_screen_text", subject="s", attribute="a", comparator="exact_text_nfc",
                        temporal="occurs", min_coverage=0.9)
    with pytest.raises(ValidationError):
        ObservationSpec(kind="dialogue", subject="s", attribute="a", comparator="dialogue_nfc", min_coverage=0.9)


def test_plan_counts_the_larger_confirmation():
    assert estimate(Workload(assertion_minutes=[1], coverage_frames=[16]), RunPlan()) > \
        estimate(Workload(assertion_minutes=[1]), RunPlan())


class GridObserver:
    """Fake observer: the caption is readable only from `appear_ms` on; frames before it show no text."""
    model = "fake-observer"

    def __init__(self, text, appear_ms):
        self.text, self.appear_ms, self.traces, self.frame_counts = text, appear_ms, [], []

    def _res(self, purpose, parsed):
        from proofframe.providers.meta import CallResult
        t = {"trace_id": f"tr-{uuid.uuid4().hex[:8]}", "purpose": purpose, "outcome": "ok", "cost_usd": 0.0}
        self.traces.append(t)
        return CallResult(ok=True, parsed=parsed, trace=t, outcome="ok")

    def observe_video(self, *, purpose, **_):
        return self._res(purpose, {"segments": [{"start_s": 0, "end_s": 5, "subject_visible": True,
                                                  "visibility": "clear", "value": self.text, "notes": ""}]})

    def observe_images(self, *, images, purpose, **_):
        self.frame_counts.append(len(images))
        frames = []
        for label, path in images:
            t_ms = self.times[label]
            shown = t_ms >= self.appear_ms
            frames.append({"label": label, "subject_visible": shown, "visibility": "clear" if shown else "not_visible",
                           "value": self.text if shown else ""})
        return self._res(purpose, {"frames": frames})


@pytest.mark.skipif(not HAS_FFMPEG, reason="needs ffmpeg (run in the app container)")
@pytest.mark.parametrize("appear_ms,status", [(10_000, "PASS"), (12_000, "FAIL")])
def test_pipeline_uses_uniform_grid_and_reports_coverage(tmp_path, appear_ms, status, monkeypatch):
    clip = tmp_path / "clip.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "testsrc2=size=320x180:rate=24:duration=30",
                    "-c:v", "libx264", str(clip)], check=True)
    store = DirStore(tmp_path)
    sha = store.put_file(clip, media_type="video/mp4")
    contract = _contract(0.9)
    scope = contract["assertions"][0]["scope"]
    grid = coverage_grid(scope["start_ms"], scope["end_ms"])
    obs = GridObserver(contract["assertions"][0]["expected"], appear_ms)
    obs.times = {f"F{i + 1}": t for i, t in enumerate(grid)}
    env = run_verification(run_id="cov", run_mode="synthetic_fixture", contract_json=contract,
                           assets=[AssetInput("shot-01", 1, sha, "video")], store=store,
                           budget=CapBudget(1.0), observer=obs).envelope
    row = env["checks"][0]
    assert row["status"] == status
    assert obs.frame_counts == [len(grid)] == [16]
    assert row["coverage"]["sampled"] == 16
    assert "uniform coverage grid" in row["rationale"]
    assert any("SAMPLED frames" in note for note in row["limitations"])
