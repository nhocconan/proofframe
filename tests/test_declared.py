"""Declared-element suppression context: deterministic matching against a case contract.

Cases are the adjudicated false-positive families of the EP01 preview deep review
(2026-10-31): the taped story note and the radio's side box must match their
declaring assertions; the desk lamp (a real defect the audit caught) and the wall
calendar must NOT match anything, so their findings stay blocking.
"""
from types import SimpleNamespace

from proofframe.verify import declared


def _el(assertion_id, subject, attribute=""):
    return SimpleNamespace(assertion_id=assertion_id,
                           observation=SimpleNamespace(kind="visual_attribute", subject=subject,
                                                       attribute=attribute))


def _contract():
    return SimpleNamespace(assertions=[
        _el("r0-body-colour",
            "the main cassette-radio prop carried and used by the teenage characters throughout the episode",
            "the colour of the radio's main body casing"),
        _el("r0-side-box-closed",
            "the small scratched metal box attached to one side of the main cassette-radio prop, with two screws and no opening seam",
            "whether that metal side box is open or shut"),
        _el("r0-side-box-side",
            "the main cassette-radio prop carried and used by the teenage characters throughout the episode",
            "which side of the radio body the small metal side box sits on"),
        _el("plan-note-on-radio",
            "the small hand-written paper note taped to the body of the main cassette-radio prop, seen in close-up",
            "the exact text"),
        _el("minh-watch-strap-colour",
            "the wristwatch worn on the wrist of the slim teenage boy who is the main protagonist",
            "the colour of the watch strap"),
        _el("lamp-plug-dropped",
            "an electrical plug and the floor near the floor-level socket box in the hall climax",
            "whether a loose electrical plug is seen lying dropped on the floor"),
        SimpleNamespace(assertion_id="continuity",
                        observation=SimpleNamespace(kind="cross_shot_continuity", subject="the whole film",
                                                    attribute="cross-shot continuity")),
        SimpleNamespace(assertion_id="dlg-c01-s01",
                        observation=SimpleNamespace(kind="dialogue", subject="line one", attribute="spoken line")),
    ])


def test_from_contract_excludes_audit_and_dialogue_assertions():
    elements = declared.from_contract(_contract())
    assert {e.assertion_id for e in elements} == {
        "r0-body-colour", "r0-side-box-closed", "r0-side-box-side",
        "plan-note-on-radio", "minh-watch-strap-colour", "lamp-plug-dropped"}


def test_declared_story_elements_match():
    elements = declared.from_contract(_contract())
    assert declared.match("Paper Note on Boombox", elements) == "plan-note-on-radio"
    assert declared.match("paper note on radio", elements) == "plan-note-on-radio"
    assert declared.match("red boombox side box", elements) in ("r0-side-box-closed", "r0-side-box-side")
    assert declared.match("Minh wristwatch", elements) == "minh-watch-strap-colour"
    assert declared.match("man's left-wrist watch", elements) == "minh-watch-strap-colour"


def test_undeclared_elements_do_not_match():
    elements = declared.from_contract(_contract())
    # the desk lamp is a real continuity defect the audit caught on the preview;
    # the lamp-plug assertion is about a floor plug and must not shield it
    assert declared.match("Desk Lamp", elements) is None
    assert declared.match("September 1999 Wall Calendar", elements) is None
    assert declared.match("green desk fan", elements) is None
    # the bare hero prop needs its own assertions' judgement, not a blanket pass:
    # a one-token overlap with the radio elements is not a declaration match
    assert declared.match("Red Boombox", elements) is None


def test_video_only_auto_contract_declares_nothing():
    auto = SimpleNamespace(assertions=[
        SimpleNamespace(assertion_id="gen-artifacts",
                        observation=SimpleNamespace(kind="generation_artifact_scan", subject="the whole video",
                                                    attribute="visual generation defects")),
        SimpleNamespace(assertion_id="qc-black",
                        observation=SimpleNamespace(kind="technical", subject="delivery",
                                                    attribute="black intervals")),
    ])
    assert declared.from_contract(auto) == []
