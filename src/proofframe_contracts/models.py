"""Original ProofFrame contract seed; this is NOT a video detector.

Schema validity and evidence metadata consistency do not prove visual truth.
Production code must populate these records from authenticated, real executions.
"""
from __future__ import annotations

import hashlib
import json
import math
from enum import Enum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_serializer, model_validator

Identifier = Annotated[str, Field(min_length=1, pattern=r"^[A-Za-z0-9_.:-]+$")]
Digest = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
Nonempty = Annotated[str, Field(min_length=1)]


def fingerprint(value: BaseModel) -> str:
    """Deterministic digest of a validated model, not a signature or permission."""
    raw = json.dumps(value.model_dump(mode="json"), sort_keys=True,
                     separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


class Record(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class AssetBinding(Record):
    asset_id: Identifier
    revision: int = Field(ge=1)
    sha256: Digest
    media_type: Literal["video", "audio", "image", "document", "composition"]
    duration_ms: int | None = Field(default=None, gt=0)


class AssetSpec(Record):
    """Logical slot in approved intent; output revisions live in run manifests."""
    asset_id: Identifier
    media_type: Literal["video", "audio", "image", "document", "composition"]
    role: Literal["output", "canonical_reference"] = "output"
    canonical_sha256: Digest | None = None

    @model_validator(mode="after")
    def reference_authority(self) -> AssetSpec:
        if self.role == "canonical_reference" and self.canonical_sha256 is None:
            raise ValueError("approved references must be hash-bound")
        if self.role == "output" and self.canonical_sha256 is not None:
            raise ValueError("output revisions belong in run manifests, not approved truth")
        return self


class Coverage(Record):
    """Availability/inspection requirement, never a statistical accuracy claim.

    'interval_scan' is reserved for exhaustive instrumented scans. A native
    video upload or a few frames cannot claim exhaustive visual inspection.
    """
    kind: Literal["artifact", "sampled", "interval_scan"] = "sampled"
    minimum_items: int = Field(default=1, ge=1)
    start_ms: int | None = Field(default=None, ge=0)
    end_ms: int | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def check_window(self) -> Coverage:
        if self.kind == "interval_scan":
            if self.start_ms is None or self.end_ms is None or self.end_ms <= self.start_ms:
                raise ValueError("interval_scan requires an increasing bounded window")
        elif self.start_ms is not None or self.end_ms is not None:
            raise ValueError("this seed only accepts explicit windows for interval_scan")
        return self


class TimeScope(Record):
    """Approved source-time window where the requirement applies (asset-local ms)."""
    start_ms: int = Field(ge=0)
    end_ms: int = Field(gt=0)

    @model_validator(mode="after")
    def increasing(self) -> TimeScope:
        if self.end_ms <= self.start_ms:
            raise ValueError("scope window must be increasing")
        return self


class ObservationSpec(Record):
    """How to observe an assertion WITHOUT revealing the expected value.

    The observer only receives `subject`, `attribute` and `vocabulary`; `expected`
    stays in deterministic comparison code. `technical` checks never call a model.
    """
    kind: Literal["visual_attribute", "on_screen_text", "technical", "generation_artifact_scan", "cross_shot_continuity", "dialogue"]
    subject: Nonempty
    attribute: Nonempty
    comparator: Literal["category_equals", "exact_text_nfc", "technical", "anomaly_scan", "continuity_audit", "dialogue_nfc"]
    vocabulary: tuple[Nonempty, ...] = ()
    technical_metric: Literal["duration_ms", "has_audio", "width", "height",
                              "black_duration_ms", "freeze_duration_ms", "silence_duration_ms",
                              "integrated_loudness_lufs", "true_peak_dbtp"] | None = None
    tolerance: int | float = Field(default=0, ge=0)
    technical_relation: Literal["equals", "at_most", "at_least"] = "equals"
    # throughout: the attribute must hold in every clear sampled frame of the scope (state).
    # occurs: an event/state reached at some point in the scope; sampled misses are UNCERTAIN, never FAIL.
    temporal: Literal["throughout", "occurs"] = "throughout"
    # coverage: the approved value must be visible in at least this fraction of a uniform frame grid over the
    # scope (e.g. 0.9 = a key caption held for >= 90 % of its spoken line). A fraction of SAMPLED frames.
    min_coverage: float | None = Field(default=None, gt=0, le=1)
    double_transcription: bool = True
    language_bias: tuple[Nonempty, ...] = Field(default=("Vietnamese",), min_length=1)

    @model_serializer(mode="wrap")
    def _stable_dump(self, handler):
        data = handler(self)
        if data.get("temporal") == "throughout":
            data.pop("temporal")  # keep fingerprints of pre-existing contracts unchanged
        if data.get("technical_relation") == "equals":
            data.pop("technical_relation")
        if data.get("min_coverage") is None:
            data.pop("min_coverage", None)
        if data.get("double_transcription") is True:
            data.pop("double_transcription")
        if data.get("language_bias") == ("Vietnamese",) or data.get("language_bias") == ["Vietnamese"]:
            data.pop("language_bias")
        return data

    @field_validator("tolerance")
    @classmethod
    def finite_tolerance(cls, value):
        if not math.isfinite(value):
            raise ValueError("tolerance must be finite")
        return int(value) if isinstance(value, float) and value.is_integer() else value

    @model_validator(mode="after")
    def consistent(self) -> ObservationSpec:
        if (self.kind == "technical") != (self.comparator == "technical"):
            raise ValueError("technical kind and comparator must agree")
        if (self.kind == "generation_artifact_scan") != (self.comparator == "anomaly_scan"):
            raise ValueError("artifact scan kind and comparator must agree")
        if (self.kind == "cross_shot_continuity") != (self.comparator == "continuity_audit"):
            raise ValueError("continuity kind and comparator must agree")
        if (self.kind == "dialogue") != (self.comparator == "dialogue_nfc"):
            raise ValueError("dialogue kind and comparator must agree")
        if self.kind == "technical" and self.technical_metric is None:
            raise ValueError("technical checks need a metric")
        if self.technical_relation != "equals" and (
            self.kind != "technical" or self.technical_metric == "has_audio"
        ):
            raise ValueError("directional relations require a numeric technical check")
        if self.min_coverage is not None and (
            self.kind not in ("on_screen_text", "visual_attribute") or self.temporal != "throughout"
        ):
            raise ValueError("min_coverage applies to on-screen text or visual attributes held throughout a scope")
        if self.min_coverage is not None and not math.isfinite(self.min_coverage):
            raise ValueError("min_coverage must be finite")
        if self.comparator == "category_equals" and not self.vocabulary:
            raise ValueError("category comparison needs a closed vocabulary")
        return self


class Assertion(Record):
    assertion_id: Identifier
    source_pointer: Nonempty
    target_asset_id: Identifier
    reference_asset_ids: tuple[Identifier, ...] = ()
    predicate: Nonempty
    expected: Nonempty
    blocking: bool = True
    stage: Literal["preflight", "shot", "assembly"] = "shot"
    depends_on: tuple[Identifier, ...] = ()
    coverage: Coverage = Field(default_factory=Coverage)
    approved_exclusion: Nonempty | None = None
    global_sentinel: bool = False
    scope: TimeScope | None = None
    observation: ObservationSpec | None = None
    allow_repeat: bool = False

    @model_serializer(mode="wrap")
    def _stable_dump(self, handler):
        data = handler(self)
        if data.get("allow_repeat") is False:
            data.pop("allow_repeat")
        return data

    @model_validator(mode="after")
    def expected_in_vocabulary(self) -> Assertion:
        obs = self.observation
        if obs is not None and obs.comparator == "category_equals" and self.expected not in obs.vocabulary:
            raise ValueError("expected category must be in the approved vocabulary")
        return self


class Contract(Record):
    schema_version: Literal["proofframe.contract.v0.1"] = "proofframe.contract.v0.1"
    contract_id: Identifier
    revision: int = Field(ge=1)
    tenant_id: Identifier
    profile: Literal["film", "brand", "educational"]
    profile_revision: Nonempty
    assets: tuple[AssetSpec, ...] = Field(min_length=1)
    assertions: tuple[Assertion, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def check_links(self) -> Contract:
        assets = {a.asset_id: a for a in self.assets}
        checks = {a.assertion_id: a for a in self.assertions}
        if len(assets) != len(self.assets) or len(checks) != len(self.assertions):
            raise ValueError("duplicate asset or assertion identifier")
        for check in self.assertions:
            if check.target_asset_id not in assets:
                raise ValueError("unknown target asset")
            if not set(check.reference_asset_ids) <= assets.keys():
                raise ValueError("unknown reference asset")
            if not set(check.depends_on) <= checks.keys():
                raise ValueError("unknown assertion dependency")
        active: set[str] = set()
        done: set[str] = set()

        def visit(key: str) -> None:
            if key in active:
                raise ValueError("cyclic assertion dependency")
            if key in done:
                return
            active.add(key)
            for dependency in checks[key].depends_on:
                visit(dependency)
            active.remove(key)
            done.add(key)

        for key in checks:
            visit(key)
        return self


class Evidence(Record):
    evidence_id: Identifier
    asset_id: Identifier
    asset_sha256: Digest
    artifact_sha256: Digest
    kind: Literal["metadata", "frame", "clip", "audio", "scan", "reference"]
    inspection: Literal["artifact", "sampled", "exhaustive"]
    uri: Nonempty
    extractor_version: Nonempty
    trace_id: Identifier
    start_ms: int | None = Field(default=None, ge=0)
    end_ms: int | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def check_interval(self) -> Evidence:
        if (self.start_ms is None) != (self.end_ms is None):
            raise ValueError("provide both interval bounds or neither")
        if self.start_ms is not None and self.end_ms <= self.start_ms:
            raise ValueError("evidence interval must be increasing")
        if self.inspection == "exhaustive" and self.kind != "scan":
            raise ValueError("only an instrumented scan can assert exhaustive inspection")
        if self.kind in {"frame", "clip", "audio", "scan"} and self.start_ms is None:
            raise ValueError("temporal evidence requires exact source interval bounds")
        return self


class Status(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    UNCERTAIN = "UNCERTAIN"
    NOT_CHECKED = "NOT_CHECKED"
    ERROR = "ERROR"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class CheckResult(Record):
    assertion_id: Identifier
    status: Status
    evidence_ids: tuple[Identifier, ...] = ()
    rationale: Nonempty
    evaluator_version: Nonempty

    @model_validator(mode="after")
    def require_evidence(self) -> CheckResult:
        if self.status in {Status.PASS, Status.FAIL} and not self.evidence_ids:
            raise ValueError("PASS and FAIL require inspectable evidence references")
        if len(set(self.evidence_ids)) != len(self.evidence_ids):
            raise ValueError("duplicate evidence does not increase coverage")
        return self


class VerificationReport(Record):
    schema_version: Literal["proofframe.report.v0.1"] = "proofframe.report.v0.1"
    run_id: Identifier
    run_mode: Literal["synthetic_fixture", "live", "recorded_replay"]
    contract_sha256: Digest
    assets: tuple[AssetBinding, ...]
    evidence: tuple[Evidence, ...]
    results: tuple[CheckResult, ...]

    @model_validator(mode="after")
    def reject_duplicates(self) -> VerificationReport:
        for collection, attr in ((self.assets, "asset_id"),
                                 (self.evidence, "evidence_id"),
                                 (self.results, "assertion_id")):
            if len({getattr(item, attr) for item in collection}) != len(collection):
                raise ValueError(f"duplicate {attr}")
        return self


class PolicyDecision(Record):
    decision: Literal["BLOCK", "REVIEW", "ELIGIBLE"]
    unresolved: tuple[Identifier, ...]
    blocking_failures: tuple[Identifier, ...]
    advisory_findings: tuple[Identifier, ...]
    run_mode: Literal["synthetic_fixture", "live", "recorded_replay"]
    publish_authorized: Literal[False] = False


class RepairAction(Record):
    action_id: Identifier
    action: Literal["FIX_COMPOSITE", "FIX_SUBTITLES", "REMIX_AUDIO", "REGENERATE_AUDIO",
                    "PATCH_GENERATION_SPEC", "REGENERATE_SHOT", "EDIT_VIDEO_REGION",
                    "REASSEMBLE", "HUMAN_REVIEW"]
    target_asset_id: Identifier
    expected_sha256: Digest
    requested_change: Nonempty
    finding_ids: tuple[Identifier, ...] = Field(min_length=1)
    preserve_assertions: tuple[Identifier, ...] = ()
    retest_assertions: tuple[Identifier, ...] = Field(min_length=1)
    requires_approval: Literal[True] = True


class RepairPlan(Record):
    schema_version: Literal["proofframe.repair.v0.1"] = "proofframe.repair.v0.1"
    plan_id: Identifier
    contract_sha256: Digest
    based_on_report_sha256: Digest
    max_attempts_per_target: int = Field(default=2, ge=1, le=2)
    actions: tuple[RepairAction, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def unique_actions(self) -> RepairPlan:
        if len({a.action_id for a in self.actions}) != len(self.actions):
            raise ValueError("duplicate repair action")
        return self


class Replacement(Record):
    target_asset_id: Identifier
    input_sha256: Digest
    output: AssetBinding


class RepairReceipt(Record):
    plan_sha256: Digest
    replacements: tuple[Replacement, ...] = Field(min_length=1)
    execution_mode: Literal["real", "staged_fixture"]

    @model_validator(mode="after")
    def unique_targets(self) -> RepairReceipt:
        if len({a.target_asset_id for a in self.replacements}) != len(self.replacements):
            raise ValueError("duplicate replacement target")
        return self
