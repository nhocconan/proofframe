from __future__ import annotations

import subprocess
import uuid
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError as JsonSchemaValidationError
from pydantic import ValidationError

from proofframe.interfaces import AssetInput
from proofframe.providers.meta import CallResult
from proofframe.verify import dialogue, plan
from proofframe.verify.pipeline import run_verification
from proofframe_contracts.models import Contract, ObservationSpec
from tests.test_core_pipeline import HAS_FFMPEG, CapBudget, DirStore


class FakeASR:
    model = "fake-asr"

    def __init__(self, transcripts):
        self.transcripts = transcripts
        self.traces = []

    def transcribe_wav(self, *, language_bias, purpose, **_):
        transcript = self.transcripts[purpose]
        trace = {"trace_id": f"tr-{uuid.uuid4().hex[:8]}", "purpose": purpose, "outcome": "ok",
                 "cost_usd": 0.0, "language_bias": language_bias}
        self.traces.append(trace)
        return CallResult(True, {"transcript": transcript, "audioDurationMs": 1000, "turns": []}, trace, "ok")


class FakeScribe:
    def __init__(self, transcript=None, *, outcome="ok", word_timestamps=True):
        self.transcript, self.outcome, self.word_timestamps = transcript, outcome, word_timestamps
        self.traces = []

    def transcribe_wav(self, *, purpose, **_):
        trace = {"trace_id": f"tr-{uuid.uuid4().hex[:8]}", "provider": "elevenlabs",
                 "model": "scribe_v2", "purpose": purpose, "outcome": self.outcome,
                 "cost_usd": 0.000061, "external_cost_usd": 0.000061,
                 "external_cost": True, "cost_basis": "audio_duration*$0.22/hour"}
        if self.outcome != "ok":
            trace["error"] = "fake Scribe failure"
        self.traces.append(trace)
        parsed = ({"transcript": self.transcript, "words": [{"text": "xin", "start": 0, "end": .1}],
                   "wordTimestampsAvailable": self.word_timestamps} if self.outcome == "ok" else None)
        return CallResult(self.outcome == "ok", parsed, trace, self.outcome)


def assertion(aid, start, end, expected="Xin chào", *, double=True, allow_repeat=False):
    return {"assertion_id": aid, "source_pointer": f"/script/{aid}", "target_asset_id": "delivery",
            "predicate": "spoken line matches locked script", "expected": expected, "allow_repeat": allow_repeat,
            "scope": {"start_ms": start, "end_ms": end},
            "observation": {"kind": "dialogue", "subject": "the scoped speaker",
                            "attribute": "spoken words", "comparator": "dialogue_nfc",
                            "double_transcription": double}}


def contract(*assertions):
    return {"schema_version": "proofframe.contract.v0.1", "contract_id": "dialogue-test", "revision": 1,
            "tenant_id": "t", "profile": "film", "profile_revision": "test",
            "assets": [{"asset_id": "delivery", "media_type": "audio"}], "assertions": list(assertions)}


def test_dialogue_compare_exact_variants_and_changed_word_diff():
    assert dialogue.decide('“Café”—đây', '"Cafe\u0301" - đây', '"Café" - đây').status == "PASS"
    result = dialogue.decide("xin chào bạn", "xin chào anh", "xin chào anh")
    assert result.status == "FAIL" and "expected [bạn] → heard [anh]" in result.rationale


def test_dialogue_uncertain_on_empty_or_double_pass_disagreement():
    assert dialogue.decide("xin chào", "", "").status == "UNCERTAIN"
    result = dialogue.decide("xin chào", "xin chào", "hoàn toàn khác")
    assert result.status == "UNCERTAIN" and "Possibly unintelligible" in result.rationale


def test_schema_dialogue_pair_and_unknown_comparator():
    ObservationSpec.model_validate({"kind": "dialogue", "subject": "speaker", "attribute": "words",
                                    "comparator": "dialogue_nfc"})
    Contract.model_validate(contract(assertion("a", 0, 1000)))
    with pytest.raises(ValidationError):
        ObservationSpec.model_validate({"kind": "dialogue", "subject": "speaker", "attribute": "words",
                                        "comparator": "unknown"})
    schema = json.loads((Path(__file__).parents[1] / "schemas/contract.schema.json").read_text())
    validator = Draft202012Validator(schema)
    validator.validate(contract(assertion("a", 0, 1000)))
    bad = contract(assertion("a", 0, 1000))
    bad["assertions"][0]["observation"]["comparator"] = "unknown"
    with pytest.raises(JsonSchemaValidationError):
        validator.validate(bad)


def test_plan_prices_both_asr_passes():
    assert plan.estimate(plan.Workload(asr_minutes=[1, 1]), plan.RunPlan()) == pytest.approx(0.00528)


def _audio(tmp_path):
    path = tmp_path / "delivery.wav"
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "sine=frequency=440:duration=3",
                    "-ac", "1", "-ar", "16000", "-y", str(path)], check=True)
    return path


def _run(tmp_path, assertions, transcripts, *, scribe=None):
    store = DirStore(tmp_path)
    source = _audio(tmp_path)
    sha = store.put_file(source, media_type="audio/wav")
    return run_verification(run_id="dialogue-run", run_mode="synthetic_fixture",
                            contract_json=contract(*assertions),
                            assets=[AssetInput("delivery", 1, sha, "audio")], store=store,
                            budget=CapBudget(1), observer=FakeASR(transcripts), scribe=scribe).envelope


@pytest.mark.skipif(not HAS_FFMPEG, reason="needs ffmpeg")
def test_pipeline_pass_fail_and_uncertain(tmp_path):
    env = _run(tmp_path, [assertion("pass", 0, 800, '“Café”—đây'),
                          assertion("fail", 900, 1700, "xin chào bạn"),
                          assertion("review", 1800, 2400, "nghe rõ"),
                          assertion("disagree", 2450, 2950, "một câu")],
               {"dialogue:pass:biased": '"Cafe\u0301" - đây', "dialogue:pass:unbiased": '"Café" - đây',
                "dialogue:fail:biased": "xin chào anh", "dialogue:fail:unbiased": "xin chào anh",
                "dialogue:review:biased": "", "dialogue:review:unbiased": "",
                "dialogue:disagree:biased": "một câu", "dialogue:disagree:unbiased": "khác hẳn"})
    rows = {x["assertion_id"]: x for x in env["checks"]}
    assert rows["pass"]["status"] == "PASS"
    assert rows["fail"]["status"] == "FAIL" and "expected [bạn] → heard [anh]" in rows["fail"]["rationale"]
    assert rows["review"]["status"] == "UNCERTAIN" and "Possibly unintelligible" in rows["review"]["rationale"]
    assert rows["disagree"]["status"] == "UNCERTAIN" and "two blind transcriptions disagree" in rows["disagree"]["rationale"]


@pytest.mark.skipif(not HAS_FFMPEG, reason="needs ffmpeg")
@pytest.mark.parametrize("allow,expected", [(False, "UNCERTAIN"), (True, "PASS")])
def test_duplicate_dialogue_review_and_approved_repeat(tmp_path, allow, expected):
    env = _run(tmp_path, [assertion("a", 0, 1000, double=False, allow_repeat=allow),
                          assertion("b", 1500, 2500, double=False)],
               {"dialogue:a:biased": "Xin chào", "dialogue:b:biased": "Xin chào"})
    rows = {x["assertion_id"]: x for x in env["checks"]}
    assert rows["a"]["status"] == rows["b"]["status"] == expected
    assert bool(rows["a"].get("findings")) is (not allow)


@pytest.mark.skipif(not HAS_FFMPEG, reason="needs ffmpeg")
def test_pipeline_scribe_vote_timestamps_and_external_cost(tmp_path):
    env = _run(tmp_path, [assertion("a", 0, 1000, "xin chào bạn")],
               {"dialogue:a:biased": "xin chào anh", "dialogue:a:unbiased": "xin chào anh"},
               scribe=FakeScribe("xin chào anh"))
    row = env["checks"][0]
    assert row["status"] == "FAIL"
    assert [item["provider"] for item in row["provider_transcripts"]] == ["meta", "meta", "elevenlabs"]
    assert "word-level ASR timing supplied" in row["limitations"][0]
    assert env["cost"]["external_cost_usd"] == pytest.approx(0.000061)
    assert env["cost"]["meta_budgeted_cost_usd"] == 0


@pytest.mark.skipif(not HAS_FFMPEG, reason="needs ffmpeg")
def test_pipeline_scribe_error_degrades_to_uncertain(tmp_path):
    env = _run(tmp_path, [assertion("a", 0, 1000, "xin chào bạn")],
               {"dialogue:a:biased": "xin chào bạn", "dialogue:a:unbiased": "xin chào bạn"},
               scribe=FakeScribe(outcome="http_error"))
    row = env["checks"][0]
    assert row["status"] == "UNCERTAIN"
    assert row["provider_transcripts"][-1]["provider"] == "elevenlabs"
    assert "ERROR" in row["rationale"]


def test_dialogue_ignores_case_and_punctuation():
    script = "K mười bảy. Nhật Tảo. Tháng mười năm chín mươi lăm."
    heard = "k mười bảy nhật tảo tháng mười năm chín mươi lăm"
    assert dialogue.decide(script, heard, heard).status == "PASS"
    assert dialogue.decide(script, "K mười bảy, Nhật Tảo! Tháng mười năm chín mươi lăm.",
                           "k mười bảy nhật tảo tháng mười năm chín mươi lăm").status == "PASS"


def test_dialogue_word_change_still_fails_with_punctuation_noise():
    result = dialogue.decide("K mười bảy. Nhật Tảo.", "k mười bảy. Sài Gòn.", "k mười bảy sài gòn")
    assert result.status == "FAIL" and "nhật tảo" in result.rationale


def test_dialogue_similarity_ignores_case_and_punctuation():
    assert dialogue.similarity("Xin chào.", "xin chào") == 1.0


@pytest.mark.parametrize(("spoken", "canonical"), [
    ("một chín chín lăm", ["1995"]),
    ("một hai", ["12"]),
    ("mười bảy", ["17"]),
    ("chín mươi lăm", ["95"]),
    ("hai mươi mốt", ["21"]),
    ("một trăm lẻ năm", ["105"]),
    ("một trăm linh tư", ["104"]),
    ("0005", ["5"]),
])
def test_vietnamese_number_canonicalization(spoken, canonical):
    assert dialogue.tokens(spoken) == canonical


def test_vietnamese_number_canonicalization_dates_times_and_real_differences():
    assert dialogue.tokens("hồi năm một chín chín lăm") == ["hồi", "năm", "1995"]
    assert dialogue.tokens("năm giờ mười bảy") == ["5", "giờ", "17"]
    assert dialogue.tokens("tháng mười năm chín mươi lăm") == ["tháng", "10", "năm", "95"]
    assert dialogue.tokens("bốn giờ rưỡi năm giờ mười bảy") == ["4", "giờ", "rưỡi", "5", "giờ", "17"]
    assert dialogue.tokens("một chín chín lăm") != dialogue.tokens("1999")
    assert dialogue.tokens("độ") != dialogue.tokens("đổ")


def test_provider_voting_replays_s05_as_uncertain():
    expected = "Ba mua trong lô đó bỏ kho tới giờ"
    result = dialogue.decide_provider_transcripts(
        expected, [("meta", "Ba mua trong lô lô đó bỏ kho tới giờ"),
                   ("meta", "Ba mua trong lô đó. Bỏ kho tới giờ.")],
        independent_provider_enabled=False)
    assert result.status == "UNCERTAIN" and "meta=" in result.rationale


def test_provider_voting_rules():
    expected = "xin chào bạn"
    differing = "xin chào anh"
    assert dialogue.decide_provider_transcripts(
        expected, [("meta", differing), ("meta", differing), ("elevenlabs", differing)]).status == "FAIL"
    assert dialogue.decide_provider_transcripts(
        expected, [("meta", expected), ("elevenlabs", differing)]).status == "UNCERTAIN"
    assert dialogue.decide_provider_transcripts(
        expected, [("meta", expected), ("meta", differing),
                   ("elevenlabs", expected)]).status == "PASS"
    assert dialogue.decide_provider_transcripts(
        expected, [("meta", expected), ("elevenlabs", expected)]).status == "PASS"
    assert dialogue.decide_provider_transcripts(
        expected, [("meta", differing), ("meta", differing)],
        independent_provider_enabled=False).status == "FAIL"
