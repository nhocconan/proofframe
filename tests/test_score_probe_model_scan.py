import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location("score_probe", Path(__file__).resolve().parents[1] / "scripts" / "score_probe_model_scan.py")
sp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sp)


def chk(cid, status="PASS", findings=None, rationale=""):
    return {"assertion_id": cid, "status": status, "findings": findings or [], "rationale": rationale, "observed": "", "limitations": []}


def finding(category, verdict="review"):
    return {"category": category, "verdict": verdict, "start_ms": 0, "end_ms": 1000, "description": "x"}


def score(checks, label_classes, end_s=1.0):
    """Mirror main()'s per-clip class accounting on one synthetic report."""
    by_id = {c["assertion_id"]: c for c in checks}
    scored = []
    for c in checks:
        fl = []
        for i, f in enumerate(c["findings"]):
            cat = sp.scored_category(c["assertion_id"], f)
            if cat:
                fl.append({"id": f"{c['assertion_id']}:{i}", "category": cat, "verdict": f["verdict"], "start_ms": 0, "end_ms": 1000, "description": "x"})
        scored.append({"assertion_id": c["assertion_id"], "findings": fl})
    labels = [{"id": c, "class": c, "t": [0, end_s], "accept_categories": sp.ACCEPT[c]} for c in label_classes]
    res = sp.score_findings({"checks": scored}, {"defects": labels, "fully_annotated": False})
    matched = {k: v["matched_labels"] for k, v in res["surfaced"]["per_class"].items()}
    out = {}
    for c in label_classes:
        caught = matched.get(c, 0)
        checked = bool(caught) or any(sp.check_finished(by_id.get(k)) for k in sp.CHECKS_FOR_CLASS[c])
        out[c] = (caught if checked else 0, int(checked), 1)
    return out


def test_error_check_is_not_checked():
    assert score([chk("gen-artifacts", "ERROR")], ["artifact"]) == {"artifact": (0, 0, 1)}
    assert score([chk("gen-artifacts", "NOT_CHECKED")], ["artifact"]) == {"artifact": (0, 0, 1)}
    assert score([], ["artifact"]) == {"artifact": (0, 0, 1)}
    assert score([chk("gen-artifacts")], ["artifact"]) == {"artifact": (0, 1, 1)}


def test_vacuous_continuity_is_not_checked_even_when_pass():
    vac = chk("continuity", "PASS", rationale="2 keyframes over 1 detected shots, 0 shot pairs compared; 0 candidate(s)")
    assert not sp.check_finished(vac)
    assert score([vac], ["new_props", "scene_changed"]) == {"new_props": (0, 0, 1), "scene_changed": (0, 0, 1)}
    real = chk("continuity", "PASS", rationale="3 keyframes over 2 detected shots, 1 shot pairs compared")
    assert score([real], ["new_props"]) == {"new_props": (0, 1, 1)}


def test_reference_match_review_credits_matching_class():
    rm = chk("reference-match", "REVIEW", [finding("new_prop")])
    assert score([rm], ["new_props"]) == {"new_props": (1, 1, 1)}
    assert score([chk("reference-match", "REVIEW", [finding("missing_prop")])], ["new_props"]) == {"new_props": (1, 1, 1)}
    sc = chk("reference-match", "REVIEW", [finding("scene_changed")])
    assert score([sc], ["scene_changed", "new_props"]) == {"scene_changed": (1, 1, 1), "new_props": (0, 1, 1)}
    # PASS with no findings counts as checked, not caught
    assert score([chk("reference-match")], ["scene_changed"]) == {"scene_changed": (0, 1, 1)}


def test_gen_artifacts_object_does_not_credit_new_props():
    ga = chk("gen-artifacts", "FAIL", [finding("object", "confirmed")])
    assert score([ga], ["new_props"]) == {"new_props": (0, 0, 1)}
    assert score([ga], ["artifact"]) == {"artifact": (1, 1, 1)}
