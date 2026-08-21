"""Closed, immutable in-memory values for the VS-02 diagnostic event domain."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
import hashlib
import re
from types import MappingProxyType
from typing import Literal, NoReturn, cast
from unicodedata import normalize

from stm32_toolkit.evidence import ArtifactRef, EvidenceIdentity, EvidenceValidationError
from stm32_toolkit.evidence import canonical_json_bytes as _evidence_canonical_json_bytes


DIAGNOSTIC_SCHEMA = "stm32-diagnostic-event/1"

DIAGNOSTIC_NOT_FOUND = "DIAGNOSTIC_NOT_FOUND"
DIAGNOSTIC_INVALID_EVENT = "DIAGNOSTIC_INVALID_EVENT"
DIAGNOSTIC_INVALID_TRANSITION = "DIAGNOSTIC_INVALID_TRANSITION"
DIAGNOSTIC_REVISION_CONFLICT = "DIAGNOSTIC_REVISION_CONFLICT"
DIAGNOSTIC_CHAIN_CORRUPT = "DIAGNOSTIC_CHAIN_CORRUPT"
DIAGNOSTIC_LIMIT_EXCEEDED = "DIAGNOSTIC_LIMIT_EXCEEDED"
DIAGNOSTIC_EVIDENCE_MISSING = "DIAGNOSTIC_EVIDENCE_MISSING"
DIAGNOSTIC_IDENTITY_MISMATCH = "DIAGNOSTIC_IDENTITY_MISMATCH"
DIAGNOSTIC_PLAN_INVALID = "DIAGNOSTIC_PLAN_INVALID"
DIAGNOSTIC_OPERATION_CONFLICT = "DIAGNOSTIC_OPERATION_CONFLICT"

SOURCE_CHANGE_DECLARATION_SCHEMA = "stm32-source-change-declaration/1"
VERIFICATION_PLAN_SCHEMA = "stm32-verification-plan/1"
DIAGNOSTIC_MARKER_SCHEMA = "stm32-diagnostic-marker-ref/1"
FIX_VERIFICATION_SCHEMA = "stm32-fix-verification/1"

DIAGNOSTIC_CODES = frozenset(
    {
        DIAGNOSTIC_NOT_FOUND,
        DIAGNOSTIC_INVALID_EVENT,
        DIAGNOSTIC_INVALID_TRANSITION,
        DIAGNOSTIC_REVISION_CONFLICT,
        DIAGNOSTIC_CHAIN_CORRUPT,
        DIAGNOSTIC_LIMIT_EXCEEDED,
        DIAGNOSTIC_EVIDENCE_MISSING,
        DIAGNOSTIC_IDENTITY_MISMATCH,
        DIAGNOSTIC_PLAN_INVALID,
        DIAGNOSTIC_OPERATION_CONFLICT,
    }
)

_MESSAGES = {
    DIAGNOSTIC_NOT_FOUND: "session does not exist",
    DIAGNOSTIC_INVALID_EVENT: "event/model/operation intent is invalid",
    DIAGNOSTIC_INVALID_TRANSITION: "event is illegal in current state",
    DIAGNOSTIC_REVISION_CONFLICT: "expected revision is stale or future",
    DIAGNOSTIC_CHAIN_CORRUPT: "event/checkpoint/root chain is missing or contradictory",
    DIAGNOSTIC_LIMIT_EXCEEDED: "a diagnostic collection or byte limit is exceeded",
    DIAGNOSTIC_EVIDENCE_MISSING: "required TestRun evidence is absent or damaged",
    DIAGNOSTIC_IDENTITY_MISMATCH: "project/workspace/TestRun identity is incompatible",
    DIAGNOSTIC_PLAN_INVALID: "selector, expected value, plan, or step reference is invalid",
    DIAGNOSTIC_OPERATION_CONFLICT: "an operation ID was reused with different intent",
}

MAX_STRING_BYTES = 64 * 1024
MAX_EVENT_BYTES = 1024 * 1024
MAX_JSON_DEPTH = 32
MAX_JSON_NODES = 100_000
MAX_EVENTS = 10_000
MAX_HYPOTHESES = 256
MAX_PLANS = 64
MAX_PLAN_STEPS = 64
MAX_RESULTS = MAX_PLAN_STEPS * MAX_PLANS
MAX_ASSESSMENTS = 1_024

RUN_STATES = ("discovered", "running", "passed", "failed", "error", "cancelled")
CASE_STATES = ("passed", "failed", "skipped", "error", "timeout")
EVENT_TYPES = (
    "session.created",
    "investigation.started",
    "hypothesis.added",
    "observation.plan_added",
    "observation.plan_executed",
    "hypothesis.assessed",
    "source_change.declared",
    "verification.plan_added",
    "verification.started",
    "analysis.marker_attached",
    "verification.completed",
)
ACTORS = ("user", "tool", "ai-client")
STATES = ("OPEN", "INVESTIGATING", "FIX_PROPOSED", "VERIFYING", "RESOLVED", "ABANDONED")

_HASH = re.compile(r"^[0-9a-f]{64}$")
_HEX_ID = re.compile(r"^[0-9a-f]{32}$")
_SAFE_ID = re.compile(r"^[a-z0-9][a-z0-9._-]{0,127}$")
_RUN_ID = re.compile(r"^[a-z0-9][a-z0-9._-]*$")
_UTC = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}Z$")


class DiagnosticValidationError(ValueError):
    """Stable diagnostic validation failure with no caller-controlled details."""

    def __init__(self, code: str, message: str | None = None) -> None:
        if code not in DIAGNOSTIC_CODES:
            raise ValueError("unknown diagnostic validation error code")
        fixed = _MESSAGES[code]
        super().__init__(fixed)
        self._code = code
        self._message = fixed

    @property
    def code(self) -> str:
        return self._code

    @property
    def message(self) -> str:
        return self._message


def _fail(code: str) -> NoReturn:
    raise DiagnosticValidationError(code)


def _string(value: object, *, allow_empty: bool = False, limit: int = MAX_STRING_BYTES) -> str:
    if not isinstance(value, str) or (not allow_empty and not value):
        _fail(DIAGNOSTIC_INVALID_EVENT)
    if normalize("NFC", value) != value:
        _fail(DIAGNOSTIC_INVALID_EVENT)
    try:
        length = len(value.encode("utf-8"))
    except UnicodeEncodeError:
        _fail(DIAGNOSTIC_INVALID_EVENT)
    if length > limit:
        _fail(DIAGNOSTIC_LIMIT_EXCEEDED)
    if any(ord(character) < 32 or ord(character) == 127 for character in value):
        _fail(DIAGNOSTIC_INVALID_EVENT)
    return value


def _hash(value: object) -> str:
    text = _string(value)
    if _HASH.fullmatch(text) is None:
        _fail(DIAGNOSTIC_INVALID_EVENT)
    return text


def _hex_id(value: object) -> str:
    text = _string(value, limit=32)
    if _HEX_ID.fullmatch(text) is None:
        _fail(DIAGNOSTIC_INVALID_EVENT)
    return text


def _safe_id(value: object) -> str:
    text = _string(value, limit=128)
    if _SAFE_ID.fullmatch(text) is None:
        _fail(DIAGNOSTIC_INVALID_EVENT)
    return text


def _run_id(value: object) -> str:
    text = _string(value)
    if _RUN_ID.fullmatch(text) is None:
        _fail(DIAGNOSTIC_INVALID_EVENT)
    return text


def _integer(value: object, *, minimum: int = 0, maximum: int = MAX_EVENTS) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        _fail(DIAGNOSTIC_INVALID_EVENT)
    return cast(int, value)


def _sequence(value: object) -> int:
    if type(value) is not int or not 0 <= value < MAX_EVENTS:
        _fail(DIAGNOSTIC_INVALID_EVENT)
    return cast(int, value)


def _utc(value: object) -> str:
    text = _string(value)
    if _UTC.fullmatch(text) is None:
        _fail(DIAGNOSTIC_INVALID_EVENT)
    try:
        datetime.strptime(text, "%Y-%m-%dT%H:%M:%S.%fZ")
    except ValueError:
        _fail(DIAGNOSTIC_INVALID_EVENT)
    return text


def _keys(value: object, expected: set[str]) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or set(value) != expected:
        _fail(DIAGNOSTIC_INVALID_EVENT)
    return cast(Mapping[str, object], value)


def _reject_tuples(value: object, *, depth: int = 1, nodes: list[int] | None = None) -> None:
    if nodes is None:
        nodes = [0]
    if depth > MAX_JSON_DEPTH:
        _fail(DIAGNOSTIC_LIMIT_EXCEEDED)
    nodes[0] += 1
    if nodes[0] > MAX_JSON_NODES:
        _fail(DIAGNOSTIC_LIMIT_EXCEEDED)
    if isinstance(value, tuple):
        _fail(DIAGNOSTIC_INVALID_EVENT)
    if isinstance(value, Mapping):
        for key, item in value.items():
            _reject_tuples(key, depth=depth + 1, nodes=nodes)
            _reject_tuples(item, depth=depth + 1, nodes=nodes)
    elif isinstance(value, list):
        for item in value:
            _reject_tuples(item, depth=depth + 1, nodes=nodes)


def _thaw(value: object) -> object:
    if isinstance(value, Mapping):
        return {str(key): _thaw(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw(item) for item in value]
    return value


def _freeze(value: object) -> object:
    if isinstance(value, Mapping):
        return MappingProxyType({str(key): _freeze(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item) for item in value)
    return value


def canonical_diagnostic_json_bytes(value: object) -> bytes:
    """Return compact canonical JSON bytes for a JSON value."""

    _reject_tuples(value)
    try:
        encoded = _evidence_canonical_json_bytes(value)
    except EvidenceValidationError as error:
        if error.code == "EVIDENCE_LIMIT_EXCEEDED":
            _fail(DIAGNOSTIC_LIMIT_EXCEEDED)
        _fail(DIAGNOSTIC_INVALID_EVENT)
    except (TypeError, ValueError, UnicodeEncodeError):
        _fail(DIAGNOSTIC_INVALID_EVENT)
    if len(encoded) > MAX_EVENT_BYTES:
        _fail(DIAGNOSTIC_LIMIT_EXCEEDED)
    return encoded


def _identity(value: object) -> EvidenceIdentity:
    try:
        identity = value if isinstance(value, EvidenceIdentity) else EvidenceIdentity.from_dict(value)
    except Exception:
        _fail(DIAGNOSTIC_INVALID_EVENT)
    assert isinstance(identity, EvidenceIdentity)
    return identity


def _selector(value: object) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        _fail(DIAGNOSTIC_INVALID_EVENT)
    selector = dict(value)
    kind = selector.get("kind")
    if kind == "run-state":
        if set(selector) != {"kind"}:
            _fail(DIAGNOSTIC_INVALID_EVENT)
    elif kind == "case-state":
        if set(selector) != {"kind", "case_id"}:
            _fail(DIAGNOSTIC_INVALID_EVENT)
        _string(selector.get("case_id"))
    elif kind == "case-count":
        if set(selector) != {"kind", "state"}:
            _fail(DIAGNOSTIC_INVALID_EVENT)
        if selector.get("state") not in CASE_STATES:
            _fail(DIAGNOSTIC_PLAN_INVALID)
    else:
        _fail(DIAGNOSTIC_PLAN_INVALID)
    return cast(Mapping[str, object], MappingProxyType({key: _freeze(item) for key, item in selector.items()}))


def _value_for_selector(selector: Mapping[str, object], value: object) -> object:
    kind = selector["kind"]
    if kind == "run-state":
        if value not in RUN_STATES or not isinstance(value, str):
            _fail(DIAGNOSTIC_PLAN_INVALID)
        return value
    if kind == "case-state":
        if value not in CASE_STATES or not isinstance(value, str):
            _fail(DIAGNOSTIC_PLAN_INVALID)
        return value
    if type(value) is not int or value < 0 or value > 100_000:
        _fail(DIAGNOSTIC_PLAN_INVALID)
    return value


@dataclass(frozen=True)
class ObservationStep:
    step_id: str
    selector: Mapping[str, object]
    expected_value: str | int
    purpose: str

    def __post_init__(self) -> None:
        _safe_id(self.step_id)
        selector = _selector(self.selector)
        expected = _value_for_selector(selector, self.expected_value)
        purpose = _string(self.purpose)
        object.__setattr__(self, "selector", selector)
        object.__setattr__(self, "expected_value", expected)
        object.__setattr__(self, "purpose", purpose)

    @classmethod
    def from_value(cls, value: object) -> "ObservationStep":
        _reject_tuples(value)
        data = _keys(value, {"step_id", "selector", "expected_value", "purpose"})
        return cls(data["step_id"], data["selector"], data["expected_value"], data["purpose"])

    def to_dict(self) -> dict[str, object]:
        return {
            "step_id": self.step_id,
            "selector": cast(dict[str, object], _thaw(self.selector)),
            "expected_value": self.expected_value,
            "purpose": self.purpose,
        }


def _steps(value: object) -> tuple[ObservationStep, ...]:
    if not isinstance(value, tuple) or len(value) > MAX_PLAN_STEPS:
        _fail(DIAGNOSTIC_LIMIT_EXCEEDED if isinstance(value, tuple) else DIAGNOSTIC_INVALID_EVENT)
    result = tuple(value)
    if not result:
        _fail(DIAGNOSTIC_PLAN_INVALID)
    if not all(isinstance(item, ObservationStep) for item in result):
        _fail(DIAGNOSTIC_INVALID_EVENT)
    if len({item.step_id for item in result}) != len(result):
        _fail(DIAGNOSTIC_PLAN_INVALID)
    return result


def _plan_fields(value: object) -> dict[str, object]:
    if isinstance(value, ObservationPlan):
        raw = value.to_dict()
    elif isinstance(value, Mapping):
        raw = dict(value)
    else:
        _fail(DIAGNOSTIC_INVALID_EVENT)
    raw.pop("plan_id", None)
    raw.pop("digest", None)
    if set(raw) != {"diagnostic_session_id", "created_revision", "steps"}:
        _fail(DIAGNOSTIC_INVALID_EVENT)
    steps_value = raw["steps"]
    if not isinstance(steps_value, (list, tuple)):
        _fail(DIAGNOSTIC_INVALID_EVENT)
    if isinstance(steps_value, tuple):
        steps = _steps(steps_value)
    else:
        steps = tuple(
            item if isinstance(item, ObservationStep) else ObservationStep.from_value(item)
            for item in steps_value
        )
    return {
        "diagnostic_session_id": _hex_id(raw["diagnostic_session_id"]),
        "created_revision": _integer(raw["created_revision"]),
        "steps": [step.to_dict() for step in _steps(steps)],
    }


def calculate_plan_digest(plan_without_ids: object) -> str:
    """Calculate a plan ID/digest over canonical plan fields excluding both IDs."""

    return hashlib.sha256(canonical_diagnostic_json_bytes(_plan_fields(plan_without_ids))).hexdigest()


@dataclass(frozen=True)
class ObservationPlan:
    plan_id: str
    diagnostic_session_id: str
    created_revision: int
    steps: tuple[ObservationStep, ...]
    digest: str

    def __post_init__(self) -> None:
        plan_id = _hash(self.plan_id)
        session_id = _hex_id(self.diagnostic_session_id)
        revision = _integer(self.created_revision)
        steps = _steps(self.steps)
        digest = _hash(self.digest)
        calculated = calculate_plan_digest(
            {"diagnostic_session_id": session_id, "created_revision": revision, "steps": list(steps)}
        )
        if plan_id != calculated or digest != calculated:
            _fail(DIAGNOSTIC_PLAN_INVALID)
        object.__setattr__(self, "plan_id", plan_id)
        object.__setattr__(self, "diagnostic_session_id", session_id)
        object.__setattr__(self, "created_revision", revision)
        object.__setattr__(self, "steps", steps)
        object.__setattr__(self, "digest", digest)

    @classmethod
    def from_value(cls, value: object) -> "ObservationPlan":
        _reject_tuples(value)
        data = _keys(value, {"plan_id", "diagnostic_session_id", "created_revision", "steps", "digest"})
        steps = data["steps"]
        if not isinstance(steps, list):
            _fail(DIAGNOSTIC_INVALID_EVENT)
        return cls(
            data["plan_id"],
            data["diagnostic_session_id"],
            data["created_revision"],
            tuple(ObservationStep.from_value(item) for item in steps),
            data["digest"],
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "plan_id": self.plan_id,
            "diagnostic_session_id": self.diagnostic_session_id,
            "created_revision": self.created_revision,
            "steps": [step.to_dict() for step in self.steps],
            "digest": self.digest,
        }


@dataclass(frozen=True)
class ObservationResult:
    plan_id: str
    step_id: str
    evidence_id: str
    selector: Mapping[str, object]
    observed_value: str | int
    expected_value: str | int
    matched: bool

    def __post_init__(self) -> None:
        plan_id = _hash(self.plan_id)
        step_id = _safe_id(self.step_id)
        evidence_id = _hash(self.evidence_id)
        selector = _selector(self.selector)
        observed = _value_for_selector(selector, self.observed_value)
        expected = _value_for_selector(selector, self.expected_value)
        if type(self.matched) is not bool or self.matched != (observed == expected):
            _fail(DIAGNOSTIC_PLAN_INVALID)
        object.__setattr__(self, "plan_id", plan_id)
        object.__setattr__(self, "step_id", step_id)
        object.__setattr__(self, "evidence_id", evidence_id)
        object.__setattr__(self, "selector", selector)
        object.__setattr__(self, "observed_value", observed)
        object.__setattr__(self, "expected_value", expected)

    @classmethod
    def from_value(cls, value: object) -> "ObservationResult":
        _reject_tuples(value)
        data = _keys(
            value,
            {"plan_id", "step_id", "evidence_id", "selector", "observed_value", "expected_value", "matched"},
        )
        return cls(
            data["plan_id"],
            data["step_id"],
            data["evidence_id"],
            data["selector"],
            data["observed_value"],
            data["expected_value"],
            data["matched"],
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "plan_id": self.plan_id,
            "step_id": self.step_id,
            "evidence_id": self.evidence_id,
            "selector": cast(dict[str, object], _thaw(self.selector)),
            "observed_value": self.observed_value,
            "expected_value": self.expected_value,
            "matched": self.matched,
        }


def _assessment_fields(value: object) -> dict[str, object]:
    if isinstance(value, EvidenceAssessment):
        raw = value.to_dict()
    elif isinstance(value, Mapping):
        raw = dict(value)
    else:
        _fail(DIAGNOSTIC_INVALID_EVENT)
    raw.pop("assessment_id", None)
    expected = {
        "hypothesis_id", "plan_id", "step_id", "evidence_id", "selector", "observed_value", "polarity", "rationale"
    }
    if set(raw) != expected:
        _fail(DIAGNOSTIC_INVALID_EVENT)
    selector = _selector(raw["selector"])
    observed = _value_for_selector(selector, raw["observed_value"])
    if raw["polarity"] not in {"supports", "refutes"}:
        _fail(DIAGNOSTIC_PLAN_INVALID)
    return {
        "hypothesis_id": _hex_id(raw["hypothesis_id"]),
        "plan_id": _hash(raw["plan_id"]),
        "step_id": _safe_id(raw["step_id"]),
        "evidence_id": _hash(raw["evidence_id"]),
        "selector": cast(dict[str, object], _thaw(selector)),
        "observed_value": observed,
        "polarity": raw["polarity"],
        "rationale": _string(raw["rationale"]),
    }


def calculate_assessment_id(assessment_without_id: object) -> str:
    return hashlib.sha256(canonical_diagnostic_json_bytes(_assessment_fields(assessment_without_id))).hexdigest()


@dataclass(frozen=True)
class EvidenceAssessment:
    assessment_id: str
    hypothesis_id: str
    plan_id: str
    step_id: str
    evidence_id: str
    selector: Mapping[str, object]
    observed_value: str | int
    polarity: Literal["supports", "refutes"]
    rationale: str

    def __post_init__(self) -> None:
        assessment_id = _hash(self.assessment_id)
        fields = _assessment_fields(
            {
                "hypothesis_id": self.hypothesis_id,
                "plan_id": self.plan_id,
                "step_id": self.step_id,
                "evidence_id": self.evidence_id,
                "selector": self.selector,
                "observed_value": self.observed_value,
                "polarity": self.polarity,
                "rationale": self.rationale,
            }
        )
        if assessment_id != calculate_assessment_id(fields):
            _fail(DIAGNOSTIC_PLAN_INVALID)
        object.__setattr__(self, "assessment_id", assessment_id)
        object.__setattr__(self, "hypothesis_id", fields["hypothesis_id"])
        object.__setattr__(self, "plan_id", fields["plan_id"])
        object.__setattr__(self, "step_id", fields["step_id"])
        object.__setattr__(self, "evidence_id", fields["evidence_id"])
        object.__setattr__(self, "selector", _selector(fields["selector"]))
        object.__setattr__(self, "observed_value", fields["observed_value"])
        object.__setattr__(self, "polarity", fields["polarity"])
        object.__setattr__(self, "rationale", fields["rationale"])

    @classmethod
    def new(
        cls,
        *,
        hypothesis_id: str,
        plan_id: str,
        step_id: str,
        evidence_id: str,
        selector: Mapping[str, object],
        observed_value: str | int,
        polarity: Literal["supports", "refutes"],
        rationale: str,
    ) -> "EvidenceAssessment":
        fields = {
            "hypothesis_id": hypothesis_id,
            "plan_id": plan_id,
            "step_id": step_id,
            "evidence_id": evidence_id,
            "selector": dict(selector),
            "observed_value": observed_value,
            "polarity": polarity,
            "rationale": rationale,
        }
        return cls(calculate_assessment_id(fields), **fields)

    @classmethod
    def from_value(cls, value: object) -> "EvidenceAssessment":
        _reject_tuples(value)
        data = _keys(
            value,
            {
                "assessment_id", "hypothesis_id", "plan_id", "step_id", "evidence_id", "selector",
                "observed_value", "polarity", "rationale",
            },
        )
        return cls(
            data["assessment_id"],
            data["hypothesis_id"],
            data["plan_id"],
            data["step_id"],
            data["evidence_id"],
            data["selector"],
            data["observed_value"],
            data["polarity"],
            data["rationale"],
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "assessment_id": self.assessment_id,
            "hypothesis_id": self.hypothesis_id,
            "plan_id": self.plan_id,
            "step_id": self.step_id,
            "evidence_id": self.evidence_id,
            "selector": cast(dict[str, object], _thaw(self.selector)),
            "observed_value": self.observed_value,
            "polarity": self.polarity,
            "rationale": self.rationale,
        }


@dataclass(frozen=True)
class Hypothesis:
    hypothesis_id: str
    statement: str
    status: Literal["open"]
    confidence_basis: Literal["unrated"]
    supporting: tuple[EvidenceAssessment, ...]
    refuting: tuple[EvidenceAssessment, ...]

    def __post_init__(self) -> None:
        hypothesis_id = _hex_id(self.hypothesis_id)
        statement = _string(self.statement)
        if self.status != "open" or self.confidence_basis != "unrated":
            _fail(DIAGNOSTIC_INVALID_EVENT)
        if not isinstance(self.supporting, tuple) or not isinstance(self.refuting, tuple):
            _fail(DIAGNOSTIC_INVALID_EVENT)
        if len(self.supporting) + len(self.refuting) > MAX_ASSESSMENTS:
            _fail(DIAGNOSTIC_LIMIT_EXCEEDED)
        assessments = self.supporting + self.refuting
        if not all(isinstance(item, EvidenceAssessment) for item in assessments):
            _fail(DIAGNOSTIC_INVALID_EVENT)
        if any(item.hypothesis_id != hypothesis_id for item in assessments):
            _fail(DIAGNOSTIC_PLAN_INVALID)
        if len({item.assessment_id for item in assessments}) != len(assessments):
            _fail(DIAGNOSTIC_PLAN_INVALID)
        supporting_keys = {(item.evidence_id, canonical_diagnostic_json_bytes(item.selector)) for item in self.supporting}
        refuting_keys = {(item.evidence_id, canonical_diagnostic_json_bytes(item.selector)) for item in self.refuting}
        if supporting_keys & refuting_keys:
            _fail(DIAGNOSTIC_PLAN_INVALID)
        object.__setattr__(self, "hypothesis_id", hypothesis_id)
        object.__setattr__(self, "statement", statement)
        object.__setattr__(self, "supporting", tuple(self.supporting))
        object.__setattr__(self, "refuting", tuple(self.refuting))

    @classmethod
    def from_value(cls, value: object) -> "Hypothesis":
        _reject_tuples(value)
        data = _keys(
            value,
            {"hypothesis_id", "statement", "status", "confidence_basis", "supporting", "refuting"},
        )
        supporting = data["supporting"]
        refuting = data["refuting"]
        if not isinstance(supporting, list) or not isinstance(refuting, list):
            _fail(DIAGNOSTIC_INVALID_EVENT)
        return cls(
            data["hypothesis_id"],
            data["statement"],
            data["status"],
            data["confidence_basis"],
            tuple(EvidenceAssessment.from_value(item) for item in supporting),
            tuple(EvidenceAssessment.from_value(item) for item in refuting),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "hypothesis_id": self.hypothesis_id,
            "statement": self.statement,
            "status": self.status,
            "confidence_basis": self.confidence_basis,
            "supporting": [item.to_dict() for item in self.supporting],
            "refuting": [item.to_dict() for item in self.refuting],
        }


@dataclass(frozen=True)
class DiagnosticSession:
    diagnostic_session_id: str
    revision: int
    state: Literal["OPEN", "INVESTIGATING", "FIX_PROPOSED", "VERIFYING", "RESOLVED", "ABANDONED"]
    identity: EvidenceIdentity
    failed_test_run_id: str
    failed_evidence_id: str
    event_head: str
    hypotheses: tuple[Hypothesis, ...]
    observation_plans: tuple[ObservationPlan, ...]
    observation_results: tuple[ObservationResult, ...]
    source_change_declarations: tuple[SourceChangeDeclaration, ...] = ()
    verification_plans: tuple[VerificationPlan, ...] = ()
    diagnostic_marker_refs: tuple[DiagnosticMarkerRef, ...] = ()
    fix_verifications: tuple[FixVerification, ...] = ()
    active_verification_plan_id: str | None = None

    def __post_init__(self) -> None:
        session_id = _hex_id(self.diagnostic_session_id)
        revision = _integer(self.revision)
        if self.state not in STATES:
            _fail(DIAGNOSTIC_INVALID_EVENT)
        if not isinstance(self.identity, EvidenceIdentity):
            _fail(DIAGNOSTIC_INVALID_EVENT)
        run_id = _run_id(self.failed_test_run_id)
        evidence_id = _hash(self.failed_evidence_id)
        event_head = _hash(self.event_head)
        if type(self.hypotheses) is not tuple or type(self.observation_plans) is not tuple or type(self.observation_results) is not tuple:
            _fail(DIAGNOSTIC_INVALID_EVENT)
        if len(self.hypotheses) > MAX_HYPOTHESES or len(self.observation_plans) > MAX_PLANS:
            _fail(DIAGNOSTIC_LIMIT_EXCEEDED)
        if len(self.observation_results) > MAX_RESULTS:
            _fail(DIAGNOSTIC_LIMIT_EXCEEDED)
        if not all(type(item) is Hypothesis for item in self.hypotheses):
            _fail(DIAGNOSTIC_INVALID_EVENT)
        if not all(type(item) is ObservationPlan for item in self.observation_plans):
            _fail(DIAGNOSTIC_INVALID_EVENT)
        if not all(type(item) is ObservationResult for item in self.observation_results):
            _fail(DIAGNOSTIC_INVALID_EVENT)
        if len({item.hypothesis_id for item in self.hypotheses}) != len(self.hypotheses):
            _fail(DIAGNOSTIC_PLAN_INVALID)
        if len({item.plan_id for item in self.observation_plans}) != len(self.observation_plans):
            _fail(DIAGNOSTIC_PLAN_INVALID)
        plans = {item.plan_id: item for item in self.observation_plans}
        if any(plan.diagnostic_session_id != session_id for plan in self.observation_plans):
            _fail(DIAGNOSTIC_PLAN_INVALID)
        results: dict[tuple[str, str], ObservationResult] = {}
        for item in self.observation_results:
            if item.evidence_id != evidence_id:
                _fail(DIAGNOSTIC_PLAN_INVALID)
            plan = plans.get(item.plan_id)
            if plan is None or item.step_id not in {step.step_id for step in plan.steps}:
                _fail(DIAGNOSTIC_PLAN_INVALID)
            if (item.plan_id, item.step_id) in results:
                _fail(DIAGNOSTIC_PLAN_INVALID)
            results[(item.plan_id, item.step_id)] = item
            step = next(step for step in plan.steps if step.step_id == item.step_id)
            if item.selector != step.selector or item.expected_value != step.expected_value:
                _fail(DIAGNOSTIC_PLAN_INVALID)
        for hypothesis in self.hypotheses:
            for assessment in hypothesis.supporting + hypothesis.refuting:
                if assessment.hypothesis_id != hypothesis.hypothesis_id:
                    _fail(DIAGNOSTIC_PLAN_INVALID)
                result = results.get((assessment.plan_id, assessment.step_id))
                if result is None or assessment.evidence_id != result.evidence_id or assessment.selector != result.selector or assessment.observed_value != result.observed_value:
                    _fail(DIAGNOSTIC_PLAN_INVALID)

        if (
            type(self.source_change_declarations) is not tuple
            or type(self.verification_plans) is not tuple
            or type(self.diagnostic_marker_refs) is not tuple
            or type(self.fix_verifications) is not tuple
        ):
            _fail(DIAGNOSTIC_INVALID_EVENT)
        if (
            len(self.source_change_declarations) > MAX_PLANS
            or len(self.verification_plans) > MAX_PLANS
            or len(self.diagnostic_marker_refs) > MAX_RESULTS
            or len(self.fix_verifications) > MAX_RESULTS
        ):
            _fail(DIAGNOSTIC_LIMIT_EXCEEDED)
        if not all(type(item) is SourceChangeDeclaration for item in self.source_change_declarations):
            _fail(DIAGNOSTIC_INVALID_EVENT)
        if not all(type(item) is VerificationPlan for item in self.verification_plans):
            _fail(DIAGNOSTIC_INVALID_EVENT)
        if not all(type(item) is DiagnosticMarkerRef for item in self.diagnostic_marker_refs):
            _fail(DIAGNOSTIC_INVALID_EVENT)
        if not all(type(item) is FixVerification for item in self.fix_verifications):
            _fail(DIAGNOSTIC_INVALID_EVENT)
        if self.active_verification_plan_id is not None:
            active_plan_id = _hash(self.active_verification_plan_id)
        else:
            active_plan_id = None

        declarations = {item.declaration_id: item for item in self.source_change_declarations}
        plans = {item.verification_plan_id: item for item in self.verification_plans}
        markers = {item.marker_id: item for item in self.diagnostic_marker_refs}
        fixes = {item.fix_verification_id: item for item in self.fix_verifications}
        if (
            len(declarations) != len(self.source_change_declarations)
            or len(plans) != len(self.verification_plans)
            or len(markers) != len(self.diagnostic_marker_refs)
            or len(fixes) != len(self.fix_verifications)
        ):
            _fail(DIAGNOSTIC_PLAN_INVALID)
        hypothesis_ids = {item.hypothesis_id for item in self.hypotheses}
        if any(
            hypothesis_id not in hypothesis_ids
            for declaration in self.source_change_declarations
            for hypothesis_id in declaration.claimed_hypothesis_ids
        ):
            _fail(DIAGNOSTIC_PLAN_INVALID)
        for plan in self.verification_plans:
            declaration = declarations.get(plan.source_change_declaration_id)
            if declaration is None or plan.diagnostic_session_id != session_id:
                _fail(DIAGNOSTIC_PLAN_INVALID)
            if plan.verification_plan_id != declaration.validation_plan_id:
                _fail(DIAGNOSTIC_PLAN_INVALID)
        for marker in self.diagnostic_marker_refs:
            if marker.diagnostic_session_id != session_id or marker.hypothesis_id not in hypothesis_ids:
                _fail(DIAGNOSTIC_PLAN_INVALID)
            if not any(
                marker.analysis_id == analysis_id and marker.analysis_evidence_id == evidence_id
                for plan in self.verification_plans
                for analysis_id, evidence_id in zip(
                    plan.required_analysis_ids,
                    plan.required_analysis_evidence_ids,
                )
            ):
                _fail(DIAGNOSTIC_PLAN_INVALID)
            if active_plan_id is not None:
                active_plan = plans.get(active_plan_id)
                if active_plan is None or not any(
                    marker.analysis_id == analysis_id and marker.analysis_evidence_id == evidence_id
                    for analysis_id, evidence_id in zip(
                        active_plan.required_analysis_ids,
                        active_plan.required_analysis_evidence_ids,
                    )
                ):
                    _fail(DIAGNOSTIC_PLAN_INVALID)
        for verification in self.fix_verifications:
            plan = plans.get(verification.verification_plan_id)
            declaration = declarations.get(verification.source_change_declaration_id)
            if (
                plan is None
                or declaration is None
                or verification.diagnostic_session_id != session_id
                or verification.source_change_declaration_id != plan.source_change_declaration_id
                or verification.verification_plan_digest != plan.plan_digest
                or verification.failed_before_run_id != run_id
                or verification.failed_before_evidence_id != evidence_id
                or verification.failed_before_run_id != plan.failed_before_run_id
                or verification.failed_before_evidence_id != plan.failed_before_evidence_id
                or verification.fixed_after_run_id != plan.fixed_after_run_id
                or verification.fixed_after_evidence_id != plan.fixed_after_evidence_id
                or verification.analysis_ids != plan.required_analysis_ids
                or verification.analysis_evidence_ids != plan.required_analysis_evidence_ids
            ):
                _fail(DIAGNOSTIC_PLAN_INVALID)
        if active_plan_id is not None and active_plan_id not in plans:
            _fail(DIAGNOSTIC_PLAN_INVALID)
        if self.state == "VERIFYING" and active_plan_id is None:
            _fail(DIAGNOSTIC_PLAN_INVALID)
        if self.state != "VERIFYING" and active_plan_id is not None:
            _fail(DIAGNOSTIC_PLAN_INVALID)
        has_new_lifecycle_data = bool(
            self.source_change_declarations
            or self.verification_plans
            or self.diagnostic_marker_refs
            or self.fix_verifications
        )
        if self.state == "OPEN" and has_new_lifecycle_data:
            _fail(DIAGNOSTIC_INVALID_EVENT)
        if self.state == "FIX_PROPOSED" and not self.source_change_declarations:
            _fail(DIAGNOSTIC_INVALID_EVENT)
        if self.state == "RESOLVED" and not any(
            item.status == "PASSED" for item in self.fix_verifications
        ):
            _fail(DIAGNOSTIC_INVALID_EVENT)
        object.__setattr__(self, "diagnostic_session_id", session_id)
        object.__setattr__(self, "revision", revision)
        object.__setattr__(self, "failed_test_run_id", run_id)
        object.__setattr__(self, "failed_evidence_id", evidence_id)
        object.__setattr__(self, "event_head", event_head)
        object.__setattr__(self, "hypotheses", tuple(self.hypotheses))
        object.__setattr__(self, "observation_plans", tuple(self.observation_plans))
        object.__setattr__(self, "observation_results", tuple(self.observation_results))
        object.__setattr__(self, "source_change_declarations", tuple(self.source_change_declarations))
        object.__setattr__(self, "verification_plans", tuple(self.verification_plans))
        object.__setattr__(self, "diagnostic_marker_refs", tuple(self.diagnostic_marker_refs))
        object.__setattr__(self, "fix_verifications", tuple(self.fix_verifications))
        object.__setattr__(self, "active_verification_plan_id", active_plan_id)

    @classmethod
    def from_value(cls, value: object) -> "DiagnosticSession":
        _reject_tuples(value)
        if not isinstance(value, Mapping):
            _fail(DIAGNOSTIC_INVALID_EVENT)
        legacy_keys = {
            "diagnostic_session_id", "revision", "state", "identity", "failed_test_run_id", "failed_evidence_id",
            "event_head", "hypotheses", "observation_plans", "observation_results",
        }
        extended_keys = legacy_keys | {
            "source_change_declarations", "verification_plans", "diagnostic_marker_refs", "fix_verifications",
            "active_verification_plan_id",
        }
        keys = set(value)
        if keys != legacy_keys and keys != extended_keys:
            _fail(DIAGNOSTIC_INVALID_EVENT)
        data = cast(Mapping[str, object], value)
        hypotheses = data["hypotheses"]
        plans = data["observation_plans"]
        results = data["observation_results"]
        if not isinstance(hypotheses, list) or not isinstance(plans, list) or not isinstance(results, list):
            _fail(DIAGNOSTIC_INVALID_EVENT)
        if keys == legacy_keys:
            return cls(
                data["diagnostic_session_id"],
                data["revision"],
                data["state"],
                _identity(data["identity"]),
                data["failed_test_run_id"],
                data["failed_evidence_id"],
                data["event_head"],
                tuple(Hypothesis.from_value(item) for item in hypotheses),
                tuple(ObservationPlan.from_value(item) for item in plans),
                tuple(ObservationResult.from_value(item) for item in results),
            )
        declarations = data["source_change_declarations"]
        verification_plans = data["verification_plans"]
        marker_refs = data["diagnostic_marker_refs"]
        fix_verifications = data["fix_verifications"]
        if (
            not isinstance(declarations, list)
            or not isinstance(verification_plans, list)
            or not isinstance(marker_refs, list)
            or not isinstance(fix_verifications, list)
        ):
            _fail(DIAGNOSTIC_INVALID_EVENT)
        if (
            data["state"] in {"OPEN", "INVESTIGATING"}
            and not declarations
            and not verification_plans
            and not marker_refs
            and not fix_verifications
            and data["active_verification_plan_id"] is None
        ):
            _fail(DIAGNOSTIC_INVALID_EVENT)
        return cls(
            data["diagnostic_session_id"],
            data["revision"],
            data["state"],
            _identity(data["identity"]),
            data["failed_test_run_id"],
            data["failed_evidence_id"],
            data["event_head"],
            tuple(Hypothesis.from_value(item) for item in hypotheses),
            tuple(ObservationPlan.from_value(item) for item in plans),
            tuple(ObservationResult.from_value(item) for item in results),
            tuple(SourceChangeDeclaration.from_value(item) for item in declarations),
            tuple(VerificationPlan.from_value(item) for item in verification_plans),
            tuple(DiagnosticMarkerRef.from_value(item) for item in marker_refs),
            tuple(FixVerification.from_value(item) for item in fix_verifications),
            data["active_verification_plan_id"],
        )

    def to_dict(self) -> dict[str, object]:
        legacy = (
            self.state in {"OPEN", "INVESTIGATING"}
            and not self.source_change_declarations
            and not self.verification_plans
            and not self.diagnostic_marker_refs
            and not self.fix_verifications
            and self.active_verification_plan_id is None
        )
        result = {
            "diagnostic_session_id": self.diagnostic_session_id,
            "revision": self.revision,
            "state": self.state,
            "identity": self.identity.to_dict(),
            "failed_test_run_id": self.failed_test_run_id,
            "failed_evidence_id": self.failed_evidence_id,
            "event_head": self.event_head,
            "hypotheses": [item.to_dict() for item in self.hypotheses],
            "observation_plans": [item.to_dict() for item in self.observation_plans],
            "observation_results": [item.to_dict() for item in self.observation_results],
        }
        if not legacy:
            result.update(
                {
                    "source_change_declarations": [item.to_dict() for item in self.source_change_declarations],
                    "verification_plans": [item.to_dict() for item in self.verification_plans],
                    "diagnostic_marker_refs": [item.to_dict() for item in self.diagnostic_marker_refs],
                    "fix_verifications": [item.to_dict() for item in self.fix_verifications],
                    "active_verification_plan_id": self.active_verification_plan_id,
                }
            )
        return result


def _payload(value: object) -> dict[str, object]:
    _reject_tuples(value)
    data = _keys(value, {"request", "result"})
    request = data["request"]
    result = data["result"]
    if not isinstance(request, Mapping) or not isinstance(result, Mapping):
        _fail(DIAGNOSTIC_INVALID_EVENT)
    return {"request": cast(dict[str, object], dict(request)), "result": cast(dict[str, object], dict(result))}


def _validate_event_payload(event_type: str, value: object) -> dict[str, object]:
    payload = _payload(value)
    request = payload["request"]
    result = payload["result"]
    assert isinstance(request, dict) and isinstance(result, dict)
    if event_type == "session.created":
        _keys(request, {"failed_test_run_id"})
        _run_id(request["failed_test_run_id"])
        result_data = _keys(result, {"failed_evidence_id", "identity"})
        _hash(result_data["failed_evidence_id"])
        _identity(result_data["identity"])
    elif event_type == "investigation.started":
        _keys(request, set())
        _keys(result, set())
    elif event_type == "hypothesis.added":
        _keys(request, {"statement"})
        _string(request["statement"])
        hypothesis_data = _keys(result, {"hypothesis"})
        hypothesis = Hypothesis.from_value(hypothesis_data["hypothesis"])
        if hypothesis.statement != request["statement"] or hypothesis.supporting or hypothesis.refuting:
            _fail(DIAGNOSTIC_INVALID_EVENT)
    elif event_type == "observation.plan_added":
        _keys(request, {"steps"})
        steps = request["steps"]
        if not isinstance(steps, list):
            _fail(DIAGNOSTIC_INVALID_EVENT)
        request_steps = tuple(ObservationStep.from_value(item) for item in steps)
        plan_data = _keys(result, {"observation_plan"})
        plan = ObservationPlan.from_value(plan_data["observation_plan"])
        if plan.steps != request_steps:
            _fail(DIAGNOSTIC_PLAN_INVALID)
    elif event_type == "observation.plan_executed":
        _keys(request, {"plan_id"})
        _hash(request["plan_id"])
        result_data = _keys(result, {"observation_results"})
        values = result_data["observation_results"]
        if not isinstance(values, list):
            _fail(DIAGNOSTIC_INVALID_EVENT)
        tuple(ObservationResult.from_value(item) for item in values)
    elif event_type == "hypothesis.assessed":
        _keys(request, {"hypothesis_id", "plan_id", "step_id", "polarity", "rationale"})
        _hex_id(request["hypothesis_id"])
        _hash(request["plan_id"])
        _safe_id(request["step_id"])
        if request["polarity"] not in {"supports", "refutes"}:
            _fail(DIAGNOSTIC_PLAN_INVALID)
        _string(request["rationale"])
        assessment_data = _keys(result, {"assessment"})
        assessment = EvidenceAssessment.from_value(assessment_data["assessment"])
        if {
            key: assessment.to_dict()[key]
            for key in ("hypothesis_id", "plan_id", "step_id", "polarity", "rationale")
        } != request:
            _fail(DIAGNOSTIC_INVALID_EVENT)
    elif event_type == "source_change.declared":
        declaration_data = _keys(request, {"source_change_declaration"})
        declaration = SourceChangeDeclaration.from_value(declaration_data["source_change_declaration"])
        result_data = _keys(result, {"declaration_id"})
        declaration_id = _hash(result_data["declaration_id"])
        if declaration_id != declaration.declaration_id:
            _fail(DIAGNOSTIC_INVALID_EVENT)
    elif event_type == "verification.plan_added":
        plan_data = _keys(request, {"verification_plan"})
        plan = VerificationPlan.from_value(plan_data["verification_plan"])
        result_data = _keys(result, {"verification_plan_id", "plan_digest"})
        plan_id = _hash(result_data["verification_plan_id"])
        plan_digest = _hash(result_data["plan_digest"])
        if plan_id != plan.verification_plan_id or plan_digest != plan.plan_digest:
            _fail(DIAGNOSTIC_INVALID_EVENT)
    elif event_type == "verification.started":
        _keys(request, {"verification_plan_id"})
        _keys(result, {"verification_plan_id"})
        plan_id = _hash(request["verification_plan_id"])
        result_plan_id = _hash(result["verification_plan_id"])
        if plan_id != result_plan_id:
            _fail(DIAGNOSTIC_INVALID_EVENT)
    elif event_type == "analysis.marker_attached":
        marker_data = _keys(request, {"diagnostic_marker_ref"})
        marker = DiagnosticMarkerRef.from_value(marker_data["diagnostic_marker_ref"])
        result_data = _keys(result, {"marker_id"})
        marker_id = _hash(result_data["marker_id"])
        if marker_id != marker.marker_id:
            _fail(DIAGNOSTIC_INVALID_EVENT)
    elif event_type == "verification.completed":
        verification_data = _keys(request, {"fix_verification"})
        verification = FixVerification.from_value(verification_data["fix_verification"])
        result_data = _keys(result, {"fix_verification_id", "status", "reason_code"})
        verification_id = _hash(result_data["fix_verification_id"])
        if (
            verification_id != verification.fix_verification_id
            or result_data["status"] != verification.status
            or result_data["reason_code"] != verification.reason_code
        ):
            _fail(DIAGNOSTIC_INVALID_EVENT)
    else:
        _fail(DIAGNOSTIC_INVALID_EVENT)
    return payload


def _event_fields_without_digest(value: object) -> dict[str, object]:
    if isinstance(value, DiagnosticEvent):
        raw = value.to_dict()
    elif isinstance(value, Mapping):
        raw = dict(value)
    else:
        _fail(DIAGNOSTIC_INVALID_EVENT)
    raw.pop("digest", None)
    expected = {
        "schema", "diagnostic_session_id", "operation_id", "sequence", "revision_before", "event_type",
        "occurred_at_utc", "actor", "previous_digest", "payload",
    }
    if set(raw) != expected:
        _fail(DIAGNOSTIC_INVALID_EVENT)
    if raw["schema"] != DIAGNOSTIC_SCHEMA:
        _fail(DIAGNOSTIC_INVALID_EVENT)
    _hex_id(raw["diagnostic_session_id"])
    _safe_id(raw["operation_id"])
    sequence = _sequence(raw["sequence"])
    revision = _integer(raw["revision_before"])
    if sequence != revision:
        _fail(DIAGNOSTIC_INVALID_EVENT)
    if raw["event_type"] not in EVENT_TYPES:
        _fail(DIAGNOSTIC_INVALID_EVENT)
    _utc(raw["occurred_at_utc"])
    if raw["actor"] not in ACTORS:
        _fail(DIAGNOSTIC_INVALID_EVENT)
    previous = raw["previous_digest"]
    if sequence == 0:
        if previous is not None:
            _fail(DIAGNOSTIC_INVALID_EVENT)
    else:
        _hash(previous)
    payload = _validate_event_payload(cast(str, raw["event_type"]), raw["payload"])
    raw["payload"] = payload
    canonical_diagnostic_json_bytes(raw)
    return raw


def calculate_event_digest(event_without_digest: object) -> str:
    """Calculate an event digest over canonical event fields excluding ``digest``."""

    return hashlib.sha256(canonical_diagnostic_json_bytes(_event_fields_without_digest(event_without_digest))).hexdigest()


@dataclass(frozen=True)
class DiagnosticEvent:
    schema: Literal["stm32-diagnostic-event/1"]
    diagnostic_session_id: str
    operation_id: str
    sequence: int
    revision_before: int
    event_type: str
    occurred_at_utc: str
    actor: Literal["user", "tool", "ai-client"]
    previous_digest: str | None
    payload: Mapping[str, object]
    digest: str

    def __post_init__(self) -> None:
        raw = {
            "schema": self.schema,
            "diagnostic_session_id": self.diagnostic_session_id,
            "operation_id": self.operation_id,
            "sequence": self.sequence,
            "revision_before": self.revision_before,
            "event_type": self.event_type,
            "occurred_at_utc": self.occurred_at_utc,
            "actor": self.actor,
            "previous_digest": self.previous_digest,
            "payload": self.payload,
        }
        normalized = _event_fields_without_digest(raw)
        digest = _hash(self.digest)
        if digest != hashlib.sha256(canonical_diagnostic_json_bytes(normalized)).hexdigest():
            _fail(DIAGNOSTIC_INVALID_EVENT)
        object.__setattr__(self, "schema", DIAGNOSTIC_SCHEMA)
        object.__setattr__(self, "diagnostic_session_id", normalized["diagnostic_session_id"])
        object.__setattr__(self, "operation_id", normalized["operation_id"])
        object.__setattr__(self, "sequence", normalized["sequence"])
        object.__setattr__(self, "revision_before", normalized["revision_before"])
        object.__setattr__(self, "event_type", normalized["event_type"])
        object.__setattr__(self, "occurred_at_utc", normalized["occurred_at_utc"])
        object.__setattr__(self, "actor", normalized["actor"])
        object.__setattr__(self, "previous_digest", normalized["previous_digest"])
        object.__setattr__(self, "payload", cast(Mapping[str, object], _freeze(normalized["payload"])))
        object.__setattr__(self, "digest", digest)

    @classmethod
    def from_value(cls, value: object) -> "DiagnosticEvent":
        _reject_tuples(value)
        data = _keys(
            value,
            {
                "schema", "diagnostic_session_id", "operation_id", "sequence", "revision_before", "event_type",
                "occurred_at_utc", "actor", "previous_digest", "payload", "digest",
            },
        )
        return cls(
            data["schema"],
            data["diagnostic_session_id"],
            data["operation_id"],
            data["sequence"],
            data["revision_before"],
            data["event_type"],
            data["occurred_at_utc"],
            data["actor"],
            data["previous_digest"],
            data["payload"],
            data["digest"],
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "diagnostic_session_id": self.diagnostic_session_id,
            "operation_id": self.operation_id,
            "sequence": self.sequence,
            "revision_before": self.revision_before,
            "event_type": self.event_type,
            "occurred_at_utc": self.occurred_at_utc,
            "actor": self.actor,
            "previous_digest": self.previous_digest,
            "payload": cast(dict[str, object], _thaw(self.payload)),
            "digest": self.digest,
        }


_SOURCE_CHANGE_FIELDS = {
    "schema", "declaration_id", "before_source_sha256", "after_source_sha256",
    "before_build_id", "before_elf_sha256", "after_build_id", "after_elf_sha256",
    "changed_paths", "diff_evidence_id", "diff_artifact", "claimed_hypothesis_ids",
    "validation_plan_id",
}
_VERIFICATION_PLAN_FIELDS = {
    "schema", "verification_plan_id", "diagnostic_session_id", "failed_before_run_id",
    "failed_before_evidence_id", "source_change_declaration_id", "fixed_after_run_id",
    "fixed_after_evidence_id", "required_analysis_ids", "required_analysis_evidence_ids",
    "required_monitor_quality", "expected_changed", "plan_digest",
}
_DIAGNOSTIC_MARKER_FIELDS = {
    "schema", "marker_id", "marker_evidence_id", "analysis_id", "analysis_evidence_id", "diagnostic_session_id",
    "hypothesis_id", "polarity", "label", "rationale",
}
_FIX_VERIFICATION_FIELDS = {
    "schema", "fix_verification_id", "diagnostic_session_id", "failed_before_run_id",
    "failed_before_evidence_id", "source_change_declaration_id", "fixed_after_run_id",
    "fixed_after_evidence_id", "verification_plan_id", "verification_plan_digest",
    "analysis_ids", "analysis_evidence_ids", "executed_operation_ids", "status", "reason_code",
    "completed_at_utc",
}
_MARKER_LABELS = {"change-observed", "no-change-observed", "analysis-inconclusive"}
_FIX_REASONS = {
    "PASSED": {"VERIFICATION_PASSED"},
    "FAILED": {"FIXED_TEST_FAILED", "ANALYSIS_CONTRADICTED"},
    "INCONCLUSIVE": {
        "MANDATORY_EVIDENCE_MISSING", "MANDATORY_EVIDENCE_CORRUPT", "ANALYSIS_NOT_VALID",
    },
    "CANCELLED": {"CALLER_CANCELLED"},
}


def _closed_mapping(value: object, expected: set[str]) -> dict[str, object]:
    if type(value) is not dict or set(value) != expected:
        _fail(DIAGNOSTIC_INVALID_EVENT)
    return cast(dict[str, object], value)


def _closed_text(value: object, *, limit: int = MAX_STRING_BYTES) -> str:
    if type(value) is not str:
        _fail(DIAGNOSTIC_INVALID_EVENT)
    return _string(value, limit=limit)


def _closed_schema(value: object, expected: str) -> str:
    schema = _closed_text(value, limit=128)
    if schema != expected:
        _fail(DIAGNOSTIC_INVALID_EVENT)
    return expected


def _closed_hash(value: object) -> str:
    if type(value) is not str:
        _fail(DIAGNOSTIC_INVALID_EVENT)
    return _hash(value)


def _closed_hex_id(value: object) -> str:
    if type(value) is not str:
        _fail(DIAGNOSTIC_INVALID_EVENT)
    return _hex_id(value)


def _closed_safe_id(value: object) -> str:
    if type(value) is not str:
        _fail(DIAGNOSTIC_INVALID_EVENT)
    return _safe_id(value)


def _closed_run_id(value: object) -> str:
    if type(value) is not str:
        _fail(DIAGNOSTIC_INVALID_EVENT)
    return _run_id(value)


def _closed_utc(value: object) -> str:
    if type(value) is not str:
        _fail(DIAGNOSTIC_INVALID_EVENT)
    return _utc(value)


def _closed_bool(value: object) -> bool:
    if type(value) is not bool:
        _fail(DIAGNOSTIC_INVALID_EVENT)
    return cast(bool, value)


def _closed_tuple(value: object, *, minimum: int, maximum: int) -> tuple[object, ...]:
    if type(value) is not tuple:
        _fail(DIAGNOSTIC_INVALID_EVENT)
    if len(value) > maximum:
        _fail(DIAGNOSTIC_LIMIT_EXCEEDED)
    if len(value) < minimum:
        _fail(DIAGNOSTIC_INVALID_EVENT)
    return cast(tuple[object, ...], value)


def _closed_wire_list(value: object, *, minimum: int, maximum: int) -> list[object]:
    if type(value) is not list:
        _fail(DIAGNOSTIC_INVALID_EVENT)
    if len(value) > maximum:
        _fail(DIAGNOSTIC_LIMIT_EXCEEDED)
    if len(value) < minimum:
        _fail(DIAGNOSTIC_INVALID_EVENT)
    return cast(list[object], value)


def _artifact_snapshot(value: object) -> ArtifactRef:
    if type(value) is ArtifactRef:
        raw = value.to_dict()
    elif type(value) is dict:
        raw = value
    elif isinstance(value, ArtifactRef):
        _fail(DIAGNOSTIC_INVALID_EVENT)
    else:
        _fail(DIAGNOSTIC_INVALID_EVENT)
    try:
        artifact = ArtifactRef.from_dict(raw)
    except EvidenceValidationError as error:
        if error.code == "EVIDENCE_LIMIT_EXCEEDED":
            _fail(DIAGNOSTIC_LIMIT_EXCEEDED)
        _fail(DIAGNOSTIC_INVALID_EVENT)
    except (TypeError, ValueError, OverflowError, UnicodeError, RecursionError):
        _fail(DIAGNOSTIC_INVALID_EVENT)
    except Exception:
        _fail(DIAGNOSTIC_INVALID_EVENT)
    if type(artifact) is not ArtifactRef:
        _fail(DIAGNOSTIC_INVALID_EVENT)
    return artifact


def _path_text(value: object) -> str:
    path = _closed_text(value, limit=4096)
    if path.startswith(("/", "\\")) or "\\" in path or ":" in path or path.endswith("/"):
        _fail(DIAGNOSTIC_INVALID_EVENT)
    parts = path.split("/")
    if any(not part or part in {".", ".."} for part in parts):
        _fail(DIAGNOSTIC_INVALID_EVENT)
    for part in parts:
        try:
            if len(part.encode("utf-8")) > 255:
                _fail(DIAGNOSTIC_LIMIT_EXCEEDED)
        except UnicodeEncodeError:
            _fail(DIAGNOSTIC_INVALID_EVENT)
    return path


def _path_tuple(value: object) -> tuple[str, ...]:
    paths = _closed_tuple(value, minimum=1, maximum=128)
    normalized = tuple(_path_text(path) for path in paths)
    total_bytes = sum(len(path.encode("utf-8")) for path in normalized)
    if total_bytes > 4096:
        _fail(DIAGNOSTIC_LIMIT_EXCEEDED)
    if len(set(normalized)) != len(normalized):
        _fail(DIAGNOSTIC_INVALID_EVENT)
    if normalized != tuple(sorted(normalized, key=lambda path: path.encode("utf-8"))):
        _fail(DIAGNOSTIC_INVALID_EVENT)
    return normalized


def _wire_path_tuple(value: object) -> tuple[str, ...]:
    paths = _closed_wire_list(value, minimum=1, maximum=128)
    return _path_tuple(tuple(paths))


def _hash_tuple(value: object, *, maximum: int, minimum: int = 1) -> tuple[str, ...]:
    values = _closed_tuple(value, minimum=minimum, maximum=maximum)
    normalized = tuple(_closed_hash(item) for item in values)
    if len(set(normalized)) != len(normalized):
        _fail(DIAGNOSTIC_INVALID_EVENT)
    if normalized != tuple(sorted(normalized)):
        _fail(DIAGNOSTIC_INVALID_EVENT)
    return normalized


def _wire_hash_tuple(value: object, *, maximum: int, minimum: int = 1) -> tuple[str, ...]:
    items = _closed_wire_list(value, minimum=minimum, maximum=maximum)
    return _hash_tuple(tuple(items), maximum=maximum, minimum=minimum)


def _parallel_hash_tuples(
    values: object,
    evidence_values: object,
    *,
    maximum: int = 16,
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    ids = _hash_tuple(values, maximum=maximum)
    evidence_ids = _hash_tuple_preserve_order(evidence_values, maximum=maximum)
    if len(ids) != len(evidence_ids):
        _fail(DIAGNOSTIC_INVALID_EVENT)
    return ids, evidence_ids


def _wire_parallel_hash_tuples(
    values: object,
    evidence_values: object,
    *,
    maximum: int = 16,
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    ids = _wire_hash_tuple(values, maximum=maximum)
    evidence_ids = _wire_hash_tuple_preserve_order(evidence_values, maximum=maximum)
    if len(ids) != len(evidence_ids):
        _fail(DIAGNOSTIC_INVALID_EVENT)
    return ids, evidence_ids


def _hash_tuple_preserve_order(
    value: object,
    *,
    maximum: int,
    minimum: int = 1,
) -> tuple[str, ...]:
    values = _closed_tuple(value, minimum=minimum, maximum=maximum)
    normalized = tuple(_closed_hash(item) for item in values)
    if len(set(normalized)) != len(normalized):
        _fail(DIAGNOSTIC_INVALID_EVENT)
    return normalized


def _wire_hash_tuple_preserve_order(
    value: object,
    *,
    maximum: int,
    minimum: int = 1,
) -> tuple[str, ...]:
    items = _closed_wire_list(value, minimum=minimum, maximum=maximum)
    return _hash_tuple_preserve_order(tuple(items), maximum=maximum, minimum=minimum)


def _hypothesis_tuple(value: object) -> tuple[str, ...]:
    values = _closed_tuple(value, minimum=1, maximum=16)
    normalized = tuple(_closed_hex_id(item) for item in values)
    if len(set(normalized)) != len(normalized):
        _fail(DIAGNOSTIC_INVALID_EVENT)
    if normalized != tuple(sorted(normalized)):
        _fail(DIAGNOSTIC_INVALID_EVENT)
    return normalized


def _wire_hypothesis_tuple(value: object) -> tuple[str, ...]:
    items = _closed_wire_list(value, minimum=1, maximum=16)
    return _hypothesis_tuple(tuple(items))


def _operation_tuple(value: object) -> tuple[str, ...]:
    operations = _closed_tuple(value, minimum=1, maximum=64)
    normalized = tuple(_closed_safe_id(item) for item in operations)
    if len(set(normalized)) != len(normalized):
        _fail(DIAGNOSTIC_INVALID_EVENT)
    return normalized


def _wire_operation_tuple(value: object) -> tuple[str, ...]:
    operations = _closed_wire_list(value, minimum=1, maximum=64)
    return _operation_tuple(tuple(operations))


def _digest_payload(value: dict[str, object]) -> str:
    return hashlib.sha256(canonical_diagnostic_json_bytes(value)).hexdigest()


def _source_change_payload(
    *,
    schema: object,
    before_source_sha256: object,
    after_source_sha256: object,
    before_build_id: object,
    before_elf_sha256: object,
    after_build_id: object,
    after_elf_sha256: object,
    changed_paths: object,
    diff_evidence_id: object,
    diff_artifact: object,
    claimed_hypothesis_ids: object,
    validation_plan_id: object,
) -> dict[str, object]:
    normalized_schema = _closed_schema(schema, SOURCE_CHANGE_DECLARATION_SCHEMA)
    before_source = _closed_hash(before_source_sha256)
    after_source = _closed_hash(after_source_sha256)
    if before_source == after_source:
        _fail(DIAGNOSTIC_INVALID_EVENT)
    paths = _path_tuple(changed_paths)
    hypotheses = _hypothesis_tuple(claimed_hypothesis_ids)
    artifact = _artifact_snapshot(diff_artifact)
    return {
        "schema": normalized_schema,
        "before_source_sha256": before_source,
        "after_source_sha256": after_source,
        "before_build_id": _closed_hash(before_build_id),
        "before_elf_sha256": _closed_hash(before_elf_sha256),
        "after_build_id": _closed_hash(after_build_id),
        "after_elf_sha256": _closed_hash(after_elf_sha256),
        "changed_paths": list(paths),
        "diff_evidence_id": _closed_hash(diff_evidence_id),
        "diff_artifact": artifact.to_dict(),
        "claimed_hypothesis_ids": list(hypotheses),
        "validation_plan_id": _closed_hash(validation_plan_id),
    }


def _source_change_payload_from_value(value: object) -> dict[str, object]:
    if type(value) is SourceChangeDeclaration:
        return _source_change_payload(
            schema=value.schema,
            before_source_sha256=value.before_source_sha256,
            after_source_sha256=value.after_source_sha256,
            before_build_id=value.before_build_id,
            before_elf_sha256=value.before_elf_sha256,
            after_build_id=value.after_build_id,
            after_elf_sha256=value.after_elf_sha256,
            changed_paths=value.changed_paths,
            diff_evidence_id=value.diff_evidence_id,
            diff_artifact=value.diff_artifact,
            claimed_hypothesis_ids=value.claimed_hypothesis_ids,
            validation_plan_id=value.validation_plan_id,
        )
    if isinstance(value, SourceChangeDeclaration):
        _fail(DIAGNOSTIC_INVALID_EVENT)
    _reject_tuples(value)
    data = _closed_mapping(value, _SOURCE_CHANGE_FIELDS)
    paths = _wire_path_tuple(data["changed_paths"])
    hypotheses = _wire_hypothesis_tuple(data["claimed_hypothesis_ids"])
    return _source_change_payload(
        schema=data["schema"],
        before_source_sha256=data["before_source_sha256"],
        after_source_sha256=data["after_source_sha256"],
        before_build_id=data["before_build_id"],
        before_elf_sha256=data["before_elf_sha256"],
        after_build_id=data["after_build_id"],
        after_elf_sha256=data["after_elf_sha256"],
        changed_paths=paths,
        diff_evidence_id=data["diff_evidence_id"],
        diff_artifact=data["diff_artifact"],
        claimed_hypothesis_ids=hypotheses,
        validation_plan_id=data["validation_plan_id"],
    )


def calculate_source_change_declaration_id(value: object) -> str:
    return _digest_payload(_source_change_payload_from_value(value))


@dataclass(frozen=True)
class SourceChangeDeclaration:
    schema: str
    declaration_id: str
    before_source_sha256: str
    after_source_sha256: str
    before_build_id: str
    before_elf_sha256: str
    after_build_id: str
    after_elf_sha256: str
    changed_paths: tuple[str, ...]
    diff_evidence_id: str
    diff_artifact: ArtifactRef
    claimed_hypothesis_ids: tuple[str, ...]
    validation_plan_id: str

    def __post_init__(self) -> None:
        payload = _source_change_payload(
            schema=self.schema,
            before_source_sha256=self.before_source_sha256,
            after_source_sha256=self.after_source_sha256,
            before_build_id=self.before_build_id,
            before_elf_sha256=self.before_elf_sha256,
            after_build_id=self.after_build_id,
            after_elf_sha256=self.after_elf_sha256,
            changed_paths=self.changed_paths,
            diff_evidence_id=self.diff_evidence_id,
            diff_artifact=self.diff_artifact,
            claimed_hypothesis_ids=self.claimed_hypothesis_ids,
            validation_plan_id=self.validation_plan_id,
        )
        declaration_id = _closed_hash(self.declaration_id)
        if declaration_id != _digest_payload(payload):
            _fail(DIAGNOSTIC_INVALID_EVENT)
        object.__setattr__(self, "schema", payload["schema"])
        for field_name in (
            "before_source_sha256", "after_source_sha256", "before_build_id", "before_elf_sha256",
            "after_build_id", "after_elf_sha256", "diff_evidence_id", "validation_plan_id",
        ):
            object.__setattr__(self, field_name, payload[field_name])
        object.__setattr__(self, "changed_paths", tuple(cast(list[str], payload["changed_paths"])))
        object.__setattr__(self, "diff_artifact", _artifact_snapshot(payload["diff_artifact"]))
        object.__setattr__(
            self,
            "claimed_hypothesis_ids",
            tuple(cast(list[str], payload["claimed_hypothesis_ids"])),
        )
        object.__setattr__(self, "declaration_id", declaration_id)

    @classmethod
    def new(
        cls,
        *,
        before_source_sha256: str,
        after_source_sha256: str,
        before_build_id: str,
        before_elf_sha256: str,
        after_build_id: str,
        after_elf_sha256: str,
        changed_paths: tuple[str, ...],
        diff_evidence_id: str,
        diff_artifact: ArtifactRef,
        claimed_hypothesis_ids: tuple[str, ...],
        validation_plan_id: str,
    ) -> "SourceChangeDeclaration":
        payload = _source_change_payload(
            schema=SOURCE_CHANGE_DECLARATION_SCHEMA,
            before_source_sha256=before_source_sha256,
            after_source_sha256=after_source_sha256,
            before_build_id=before_build_id,
            before_elf_sha256=before_elf_sha256,
            after_build_id=after_build_id,
            after_elf_sha256=after_elf_sha256,
            changed_paths=changed_paths,
            diff_evidence_id=diff_evidence_id,
            diff_artifact=diff_artifact,
            claimed_hypothesis_ids=claimed_hypothesis_ids,
            validation_plan_id=validation_plan_id,
        )
        return cls(
            payload["schema"],
            _digest_payload(payload),
            payload["before_source_sha256"],
            payload["after_source_sha256"],
            payload["before_build_id"],
            payload["before_elf_sha256"],
            payload["after_build_id"],
            payload["after_elf_sha256"],
            tuple(cast(list[str], payload["changed_paths"])),
            payload["diff_evidence_id"],
            _artifact_snapshot(payload["diff_artifact"]),
            tuple(cast(list[str], payload["claimed_hypothesis_ids"])),
            payload["validation_plan_id"],
        )

    @classmethod
    def from_value(cls, value: object) -> "SourceChangeDeclaration":
        if type(value) is cls:
            return value
        if isinstance(value, cls):
            _fail(DIAGNOSTIC_INVALID_EVENT)
        payload = _source_change_payload_from_value(value)
        data = _closed_mapping(value, _SOURCE_CHANGE_FIELDS)
        return cls(
            data["schema"],
            data["declaration_id"],
            payload["before_source_sha256"],
            payload["after_source_sha256"],
            payload["before_build_id"],
            payload["before_elf_sha256"],
            payload["after_build_id"],
            payload["after_elf_sha256"],
            tuple(cast(list[str], payload["changed_paths"])),
            payload["diff_evidence_id"],
            _artifact_snapshot(payload["diff_artifact"]),
            tuple(cast(list[str], payload["claimed_hypothesis_ids"])),
            payload["validation_plan_id"],
        )

    def to_dict(self) -> dict[str, object]:
        payload = _source_change_payload_from_value(self)
        payload["declaration_id"] = self.declaration_id
        return {"schema": payload["schema"], "declaration_id": payload["declaration_id"],
                "before_source_sha256": payload["before_source_sha256"],
                "after_source_sha256": payload["after_source_sha256"],
                "before_build_id": payload["before_build_id"], "before_elf_sha256": payload["before_elf_sha256"],
                "after_build_id": payload["after_build_id"], "after_elf_sha256": payload["after_elf_sha256"],
                "changed_paths": list(cast(list[str], payload["changed_paths"])),
                "diff_evidence_id": payload["diff_evidence_id"],
                "diff_artifact": dict(cast(dict[str, object], payload["diff_artifact"])),
                "claimed_hypothesis_ids": list(cast(list[str], payload["claimed_hypothesis_ids"])),
                "validation_plan_id": payload["validation_plan_id"]}


def _verification_plan_payload(
    *,
    schema: object,
    verification_plan_id: object,
    diagnostic_session_id: object,
    failed_before_run_id: object,
    failed_before_evidence_id: object,
    source_change_declaration_id: object,
    fixed_after_run_id: object,
    fixed_after_evidence_id: object,
    required_analysis_ids: object,
    required_analysis_evidence_ids: object,
    required_monitor_quality: object,
    expected_changed: object,
) -> dict[str, object]:
    normalized_schema = _closed_schema(schema, VERIFICATION_PLAN_SCHEMA)
    normalized_plan_id = _closed_hash(verification_plan_id)
    failed_run = _closed_run_id(failed_before_run_id)
    fixed_run = _closed_run_id(fixed_after_run_id)
    failed_evidence = _closed_hash(failed_before_evidence_id)
    fixed_evidence = _closed_hash(fixed_after_evidence_id)
    if failed_run == fixed_run or failed_evidence == fixed_evidence:
        _fail(DIAGNOSTIC_INVALID_EVENT)
    analysis_ids, analysis_evidence_ids = _parallel_hash_tuples(
        required_analysis_ids,
        required_analysis_evidence_ids,
    )
    if required_monitor_quality != "VALID" or type(required_monitor_quality) is not str:
        _fail(DIAGNOSTIC_INVALID_EVENT)
    if type(expected_changed) is not bool or expected_changed is not True:
        _fail(DIAGNOSTIC_INVALID_EVENT)
    return {
        "schema": normalized_schema,
        "verification_plan_id": normalized_plan_id,
        "diagnostic_session_id": _closed_hex_id(diagnostic_session_id),
        "failed_before_run_id": failed_run,
        "failed_before_evidence_id": failed_evidence,
        "source_change_declaration_id": _closed_hash(source_change_declaration_id),
        "fixed_after_run_id": fixed_run,
        "fixed_after_evidence_id": fixed_evidence,
        "required_analysis_ids": list(analysis_ids),
        "required_analysis_evidence_ids": list(analysis_evidence_ids),
        "required_monitor_quality": "VALID",
        "expected_changed": True,
    }


def _verification_plan_payload_from_value(value: object) -> dict[str, object]:
    if type(value) is VerificationPlan:
        return _verification_plan_payload(
            schema=value.schema,
            verification_plan_id=value.verification_plan_id,
            diagnostic_session_id=value.diagnostic_session_id,
            failed_before_run_id=value.failed_before_run_id,
            failed_before_evidence_id=value.failed_before_evidence_id,
            source_change_declaration_id=value.source_change_declaration_id,
            fixed_after_run_id=value.fixed_after_run_id,
            fixed_after_evidence_id=value.fixed_after_evidence_id,
            required_analysis_ids=value.required_analysis_ids,
            required_analysis_evidence_ids=value.required_analysis_evidence_ids,
            required_monitor_quality=value.required_monitor_quality,
            expected_changed=value.expected_changed,
        )
    if isinstance(value, VerificationPlan):
        _fail(DIAGNOSTIC_INVALID_EVENT)
    _reject_tuples(value)
    data = _closed_mapping(value, _VERIFICATION_PLAN_FIELDS)
    analysis_ids, evidence_ids = _wire_parallel_hash_tuples(
        data["required_analysis_ids"],
        data["required_analysis_evidence_ids"],
    )
    return _verification_plan_payload(
        schema=data["schema"],
        verification_plan_id=data["verification_plan_id"],
        diagnostic_session_id=data["diagnostic_session_id"],
        failed_before_run_id=data["failed_before_run_id"],
        failed_before_evidence_id=data["failed_before_evidence_id"],
        source_change_declaration_id=data["source_change_declaration_id"],
        fixed_after_run_id=data["fixed_after_run_id"],
        fixed_after_evidence_id=data["fixed_after_evidence_id"],
        required_analysis_ids=analysis_ids,
        required_analysis_evidence_ids=evidence_ids,
        required_monitor_quality=data["required_monitor_quality"],
        expected_changed=data["expected_changed"],
    )


def calculate_verification_plan_digest(value: object) -> str:
    return _digest_payload(_verification_plan_payload_from_value(value))


@dataclass(frozen=True)
class VerificationPlan:
    schema: str
    verification_plan_id: str
    diagnostic_session_id: str
    failed_before_run_id: str
    failed_before_evidence_id: str
    source_change_declaration_id: str
    fixed_after_run_id: str
    fixed_after_evidence_id: str
    required_analysis_ids: tuple[str, ...]
    required_analysis_evidence_ids: tuple[str, ...]
    required_monitor_quality: str
    expected_changed: bool
    plan_digest: str

    def __post_init__(self) -> None:
        payload = _verification_plan_payload(
            schema=self.schema,
            verification_plan_id=self.verification_plan_id,
            diagnostic_session_id=self.diagnostic_session_id,
            failed_before_run_id=self.failed_before_run_id,
            failed_before_evidence_id=self.failed_before_evidence_id,
            source_change_declaration_id=self.source_change_declaration_id,
            fixed_after_run_id=self.fixed_after_run_id,
            fixed_after_evidence_id=self.fixed_after_evidence_id,
            required_analysis_ids=self.required_analysis_ids,
            required_analysis_evidence_ids=self.required_analysis_evidence_ids,
            required_monitor_quality=self.required_monitor_quality,
            expected_changed=self.expected_changed,
        )
        digest = _closed_hash(self.plan_digest)
        calculated = _digest_payload(payload)
        if digest != calculated:
            _fail(DIAGNOSTIC_INVALID_EVENT)
        object.__setattr__(self, "schema", payload["schema"])
        object.__setattr__(self, "verification_plan_id", payload["verification_plan_id"])
        for field_name in (
            "diagnostic_session_id", "failed_before_run_id", "failed_before_evidence_id",
            "source_change_declaration_id", "fixed_after_run_id", "fixed_after_evidence_id",
            "required_monitor_quality", "expected_changed",
        ):
            object.__setattr__(self, field_name, payload[field_name])
        object.__setattr__(self, "required_analysis_ids", tuple(cast(list[str], payload["required_analysis_ids"])))
        object.__setattr__(
            self,
            "required_analysis_evidence_ids",
            tuple(cast(list[str], payload["required_analysis_evidence_ids"])),
        )
        object.__setattr__(self, "plan_digest", digest)

    @classmethod
    def new(
        cls,
        *,
        verification_plan_id: str,
        diagnostic_session_id: str,
        failed_before_run_id: str,
        failed_before_evidence_id: str,
        source_change_declaration_id: str,
        fixed_after_run_id: str,
        fixed_after_evidence_id: str,
        required_analysis_ids: tuple[str, ...],
        required_analysis_evidence_ids: tuple[str, ...],
        required_monitor_quality: str,
        expected_changed: bool,
    ) -> "VerificationPlan":
        payload = _verification_plan_payload(
            schema=VERIFICATION_PLAN_SCHEMA,
            verification_plan_id=verification_plan_id,
            diagnostic_session_id=diagnostic_session_id,
            failed_before_run_id=failed_before_run_id,
            failed_before_evidence_id=failed_before_evidence_id,
            source_change_declaration_id=source_change_declaration_id,
            fixed_after_run_id=fixed_after_run_id,
            fixed_after_evidence_id=fixed_after_evidence_id,
            required_analysis_ids=required_analysis_ids,
            required_analysis_evidence_ids=required_analysis_evidence_ids,
            required_monitor_quality=required_monitor_quality,
            expected_changed=expected_changed,
        )
        digest = _digest_payload(payload)
        return cls(
            payload["schema"],
            payload["verification_plan_id"],
            payload["diagnostic_session_id"],
            payload["failed_before_run_id"],
            payload["failed_before_evidence_id"],
            payload["source_change_declaration_id"],
            payload["fixed_after_run_id"],
            payload["fixed_after_evidence_id"],
            tuple(cast(list[str], payload["required_analysis_ids"])),
            tuple(cast(list[str], payload["required_analysis_evidence_ids"])),
            payload["required_monitor_quality"],
            payload["expected_changed"],
            digest,
        )

    @classmethod
    def from_value(cls, value: object) -> "VerificationPlan":
        if type(value) is cls:
            return value
        if isinstance(value, cls):
            _fail(DIAGNOSTIC_INVALID_EVENT)
        payload = _verification_plan_payload_from_value(value)
        data = _closed_mapping(value, _VERIFICATION_PLAN_FIELDS)
        return cls(
            data["schema"],
            data["verification_plan_id"],
            payload["diagnostic_session_id"],
            payload["failed_before_run_id"],
            payload["failed_before_evidence_id"],
            payload["source_change_declaration_id"],
            payload["fixed_after_run_id"],
            payload["fixed_after_evidence_id"],
            tuple(cast(list[str], payload["required_analysis_ids"])),
            tuple(cast(list[str], payload["required_analysis_evidence_ids"])),
            payload["required_monitor_quality"],
            payload["expected_changed"],
            data["plan_digest"],
        )

    def to_dict(self) -> dict[str, object]:
        payload = _verification_plan_payload_from_value(self)
        payload["plan_digest"] = self.plan_digest
        return {
            "schema": payload["schema"],
            "verification_plan_id": payload["verification_plan_id"],
            "diagnostic_session_id": payload["diagnostic_session_id"],
            "failed_before_run_id": payload["failed_before_run_id"],
            "failed_before_evidence_id": payload["failed_before_evidence_id"],
            "source_change_declaration_id": payload["source_change_declaration_id"],
            "fixed_after_run_id": payload["fixed_after_run_id"],
            "fixed_after_evidence_id": payload["fixed_after_evidence_id"],
            "required_analysis_ids": list(cast(list[str], payload["required_analysis_ids"])),
            "required_analysis_evidence_ids": list(cast(list[str], payload["required_analysis_evidence_ids"])),
            "required_monitor_quality": payload["required_monitor_quality"],
            "expected_changed": payload["expected_changed"],
            "plan_digest": payload["plan_digest"],
        }


def _marker_payload(
    *,
    schema: object,
    marker_evidence_id: object,
    analysis_id: object,
    analysis_evidence_id: object,
    diagnostic_session_id: object,
    hypothesis_id: object,
    polarity: object,
    label: object,
    rationale: object,
) -> dict[str, object]:
    normalized_schema = _closed_schema(schema, DIAGNOSTIC_MARKER_SCHEMA)
    polarity_value = _closed_text(polarity, limit=32)
    if polarity_value not in {"supports", "refutes"}:
        _fail(DIAGNOSTIC_INVALID_EVENT)
    label_value = _closed_text(label, limit=64)
    if label_value not in _MARKER_LABELS:
        _fail(DIAGNOSTIC_INVALID_EVENT)
    return {
        "schema": normalized_schema,
        "marker_evidence_id": _closed_hash(marker_evidence_id),
        "analysis_id": _closed_hash(analysis_id),
        "analysis_evidence_id": _closed_hash(analysis_evidence_id),
        "diagnostic_session_id": _closed_hex_id(diagnostic_session_id),
        "hypothesis_id": _closed_hex_id(hypothesis_id),
        "polarity": polarity_value,
        "label": label_value,
        "rationale": _closed_text(rationale, limit=4096),
    }


def _marker_payload_from_value(value: object) -> dict[str, object]:
    if type(value) is DiagnosticMarkerRef:
        return _marker_payload(
            schema=value.schema,
            marker_evidence_id=value.marker_evidence_id,
            analysis_id=value.analysis_id,
            analysis_evidence_id=value.analysis_evidence_id,
            diagnostic_session_id=value.diagnostic_session_id,
            hypothesis_id=value.hypothesis_id,
            polarity=value.polarity,
            label=value.label,
            rationale=value.rationale,
        )
    if isinstance(value, DiagnosticMarkerRef):
        _fail(DIAGNOSTIC_INVALID_EVENT)
    _reject_tuples(value)
    data = _closed_mapping(value, _DIAGNOSTIC_MARKER_FIELDS)
    return _marker_payload(
        schema=data["schema"],
        marker_evidence_id=data["marker_evidence_id"],
        analysis_id=data["analysis_id"],
        analysis_evidence_id=data["analysis_evidence_id"],
        diagnostic_session_id=data["diagnostic_session_id"],
        hypothesis_id=data["hypothesis_id"],
        polarity=data["polarity"],
        label=data["label"],
        rationale=data["rationale"],
    )


@dataclass(frozen=True)
class DiagnosticMarkerRef:
    schema: str
    marker_id: str
    marker_evidence_id: str
    analysis_id: str
    analysis_evidence_id: str
    diagnostic_session_id: str
    hypothesis_id: str
    polarity: str
    label: str
    rationale: str

    def __post_init__(self) -> None:
        payload = _marker_payload(
            schema=self.schema,
            marker_evidence_id=self.marker_evidence_id,
            analysis_id=self.analysis_id,
            analysis_evidence_id=self.analysis_evidence_id,
            diagnostic_session_id=self.diagnostic_session_id,
            hypothesis_id=self.hypothesis_id,
            polarity=self.polarity,
            label=self.label,
            rationale=self.rationale,
        )
        marker_id = _closed_hash(self.marker_id)
        object.__setattr__(self, "schema", payload["schema"])
        object.__setattr__(self, "marker_id", marker_id)
        for field_name in (
            "marker_evidence_id", "analysis_id", "analysis_evidence_id", "diagnostic_session_id",
            "hypothesis_id", "polarity", "label", "rationale",
        ):
            object.__setattr__(self, field_name, payload[field_name])

    @classmethod
    def new(
        cls,
        *,
        marker_id: str,
        marker_evidence_id: str,
        analysis_id: str,
        analysis_evidence_id: str,
        diagnostic_session_id: str,
        hypothesis_id: str,
        polarity: str,
        label: str,
        rationale: str,
    ) -> "DiagnosticMarkerRef":
        return cls(
            DIAGNOSTIC_MARKER_SCHEMA,
            marker_id,
            marker_evidence_id,
            analysis_id,
            analysis_evidence_id,
            diagnostic_session_id,
            hypothesis_id,
            polarity,
            label,
            rationale,
        )

    @classmethod
    def from_value(cls, value: object) -> "DiagnosticMarkerRef":
        if type(value) is cls:
            return value
        if isinstance(value, cls):
            _fail(DIAGNOSTIC_INVALID_EVENT)
        _reject_tuples(value)
        data = _closed_mapping(value, _DIAGNOSTIC_MARKER_FIELDS)
        payload = _marker_payload_from_value(value)
        return cls(
            data["schema"],
            data["marker_id"],
            payload["marker_evidence_id"],
            payload["analysis_id"],
            payload["analysis_evidence_id"],
            payload["diagnostic_session_id"],
            payload["hypothesis_id"],
            payload["polarity"],
            payload["label"],
            payload["rationale"],
        )

    def to_dict(self) -> dict[str, object]:
        payload = _marker_payload_from_value(self)
        return {
            "schema": payload["schema"],
            "marker_id": self.marker_id,
            "marker_evidence_id": payload["marker_evidence_id"],
            "analysis_id": payload["analysis_id"],
            "analysis_evidence_id": payload["analysis_evidence_id"],
            "diagnostic_session_id": payload["diagnostic_session_id"],
            "hypothesis_id": payload["hypothesis_id"],
            "polarity": payload["polarity"],
            "label": payload["label"],
            "rationale": payload["rationale"],
        }


def _fix_verification_payload(
    *,
    schema: object,
    diagnostic_session_id: object,
    failed_before_run_id: object,
    failed_before_evidence_id: object,
    source_change_declaration_id: object,
    fixed_after_run_id: object,
    fixed_after_evidence_id: object,
    verification_plan_id: object,
    verification_plan_digest: object,
    analysis_ids: object,
    analysis_evidence_ids: object,
    executed_operation_ids: object,
    status: object,
    reason_code: object,
    completed_at_utc: object,
) -> dict[str, object]:
    normalized_schema = _closed_schema(schema, FIX_VERIFICATION_SCHEMA)
    failed_run = _closed_run_id(failed_before_run_id)
    fixed_run = _closed_run_id(fixed_after_run_id)
    failed_evidence = _closed_hash(failed_before_evidence_id)
    fixed_evidence = _closed_hash(fixed_after_evidence_id)
    if failed_run == fixed_run or failed_evidence == fixed_evidence:
        _fail(DIAGNOSTIC_INVALID_EVENT)
    normalized_plan_id = _closed_hash(verification_plan_id)
    normalized_plan_digest = _closed_hash(verification_plan_digest)
    normalized_status = _closed_text(status, limit=32)
    allowed_reasons = _FIX_REASONS.get(normalized_status)
    if allowed_reasons is None:
        _fail(DIAGNOSTIC_INVALID_EVENT)
    normalized_reason = _closed_text(reason_code, limit=64)
    if normalized_reason not in allowed_reasons:
        _fail(DIAGNOSTIC_INVALID_EVENT)
    analysis, analysis_evidence = _parallel_hash_tuples(analysis_ids, analysis_evidence_ids)
    operations = _operation_tuple(executed_operation_ids)
    return {
        "schema": normalized_schema,
        "diagnostic_session_id": _closed_hex_id(diagnostic_session_id),
        "failed_before_run_id": failed_run,
        "failed_before_evidence_id": failed_evidence,
        "source_change_declaration_id": _closed_hash(source_change_declaration_id),
        "fixed_after_run_id": fixed_run,
        "fixed_after_evidence_id": fixed_evidence,
        "verification_plan_id": normalized_plan_id,
        "verification_plan_digest": normalized_plan_digest,
        "analysis_ids": list(analysis),
        "analysis_evidence_ids": list(analysis_evidence),
        "executed_operation_ids": list(operations),
        "status": normalized_status,
        "reason_code": normalized_reason,
        "completed_at_utc": _closed_utc(completed_at_utc),
    }


def _fix_verification_payload_from_value(value: object) -> dict[str, object]:
    if type(value) is FixVerification:
        return _fix_verification_payload(
            schema=value.schema,
            diagnostic_session_id=value.diagnostic_session_id,
            failed_before_run_id=value.failed_before_run_id,
            failed_before_evidence_id=value.failed_before_evidence_id,
            source_change_declaration_id=value.source_change_declaration_id,
            fixed_after_run_id=value.fixed_after_run_id,
            fixed_after_evidence_id=value.fixed_after_evidence_id,
            verification_plan_id=value.verification_plan_id,
            verification_plan_digest=value.verification_plan_digest,
            analysis_ids=value.analysis_ids,
            analysis_evidence_ids=value.analysis_evidence_ids,
            executed_operation_ids=value.executed_operation_ids,
            status=value.status,
            reason_code=value.reason_code,
            completed_at_utc=value.completed_at_utc,
        )
    if isinstance(value, FixVerification):
        _fail(DIAGNOSTIC_INVALID_EVENT)
    _reject_tuples(value)
    data = _closed_mapping(value, _FIX_VERIFICATION_FIELDS)
    analysis_ids, analysis_evidence_ids = _wire_parallel_hash_tuples(
        data["analysis_ids"],
        data["analysis_evidence_ids"],
    )
    executed_operations = _wire_operation_tuple(data["executed_operation_ids"])
    return _fix_verification_payload(
        schema=data["schema"],
        diagnostic_session_id=data["diagnostic_session_id"],
        failed_before_run_id=data["failed_before_run_id"],
        failed_before_evidence_id=data["failed_before_evidence_id"],
        source_change_declaration_id=data["source_change_declaration_id"],
        fixed_after_run_id=data["fixed_after_run_id"],
        fixed_after_evidence_id=data["fixed_after_evidence_id"],
        verification_plan_id=data["verification_plan_id"],
        verification_plan_digest=data["verification_plan_digest"],
        analysis_ids=analysis_ids,
        analysis_evidence_ids=analysis_evidence_ids,
        executed_operation_ids=executed_operations,
        status=data["status"],
        reason_code=data["reason_code"],
        completed_at_utc=data["completed_at_utc"],
    )


def calculate_fix_verification_id(value: object) -> str:
    return _digest_payload(_fix_verification_payload_from_value(value))


@dataclass(frozen=True)
class FixVerification:
    schema: str
    fix_verification_id: str
    diagnostic_session_id: str
    failed_before_run_id: str
    failed_before_evidence_id: str
    source_change_declaration_id: str
    fixed_after_run_id: str
    fixed_after_evidence_id: str
    verification_plan_id: str
    verification_plan_digest: str
    analysis_ids: tuple[str, ...]
    analysis_evidence_ids: tuple[str, ...]
    executed_operation_ids: tuple[str, ...]
    status: str
    reason_code: str
    completed_at_utc: str

    def __post_init__(self) -> None:
        payload = _fix_verification_payload(
            schema=self.schema,
            diagnostic_session_id=self.diagnostic_session_id,
            failed_before_run_id=self.failed_before_run_id,
            failed_before_evidence_id=self.failed_before_evidence_id,
            source_change_declaration_id=self.source_change_declaration_id,
            fixed_after_run_id=self.fixed_after_run_id,
            fixed_after_evidence_id=self.fixed_after_evidence_id,
            verification_plan_id=self.verification_plan_id,
            verification_plan_digest=self.verification_plan_digest,
            analysis_ids=self.analysis_ids,
            analysis_evidence_ids=self.analysis_evidence_ids,
            executed_operation_ids=self.executed_operation_ids,
            status=self.status,
            reason_code=self.reason_code,
            completed_at_utc=self.completed_at_utc,
        )
        fix_id = _closed_hash(self.fix_verification_id)
        calculated = _digest_payload(payload)
        if fix_id != calculated:
            _fail(DIAGNOSTIC_INVALID_EVENT)
        object.__setattr__(self, "schema", payload["schema"])
        for field_name in (
            "diagnostic_session_id", "failed_before_run_id", "failed_before_evidence_id",
            "source_change_declaration_id", "fixed_after_run_id", "fixed_after_evidence_id",
            "verification_plan_id", "verification_plan_digest", "status", "reason_code",
            "completed_at_utc",
        ):
            object.__setattr__(self, field_name, payload[field_name])
        object.__setattr__(self, "analysis_ids", tuple(cast(list[str], payload["analysis_ids"])))
        object.__setattr__(
            self,
            "analysis_evidence_ids",
            tuple(cast(list[str], payload["analysis_evidence_ids"])),
        )
        object.__setattr__(
            self,
            "executed_operation_ids",
            tuple(cast(list[str], payload["executed_operation_ids"])),
        )
        object.__setattr__(self, "fix_verification_id", fix_id)

    @classmethod
    def new(
        cls,
        *,
        diagnostic_session_id: str,
        failed_before_run_id: str,
        failed_before_evidence_id: str,
        source_change_declaration_id: str,
        fixed_after_run_id: str,
        fixed_after_evidence_id: str,
        verification_plan_id: str,
        verification_plan_digest: str,
        analysis_ids: tuple[str, ...],
        analysis_evidence_ids: tuple[str, ...],
        executed_operation_ids: tuple[str, ...],
        status: str,
        reason_code: str,
        completed_at_utc: str,
    ) -> "FixVerification":
        payload = _fix_verification_payload(
            schema=FIX_VERIFICATION_SCHEMA,
            diagnostic_session_id=diagnostic_session_id,
            failed_before_run_id=failed_before_run_id,
            failed_before_evidence_id=failed_before_evidence_id,
            source_change_declaration_id=source_change_declaration_id,
            fixed_after_run_id=fixed_after_run_id,
            fixed_after_evidence_id=fixed_after_evidence_id,
            verification_plan_id=verification_plan_id,
            verification_plan_digest=verification_plan_digest,
            analysis_ids=analysis_ids,
            analysis_evidence_ids=analysis_evidence_ids,
            executed_operation_ids=executed_operation_ids,
            status=status,
            reason_code=reason_code,
            completed_at_utc=completed_at_utc,
        )
        fix_id = _digest_payload(payload)
        return cls(
            payload["schema"],
            fix_id,
            payload["diagnostic_session_id"],
            payload["failed_before_run_id"],
            payload["failed_before_evidence_id"],
            payload["source_change_declaration_id"],
            payload["fixed_after_run_id"],
            payload["fixed_after_evidence_id"],
            payload["verification_plan_id"],
            payload["verification_plan_digest"],
            tuple(cast(list[str], payload["analysis_ids"])),
            tuple(cast(list[str], payload["analysis_evidence_ids"])),
            tuple(cast(list[str], payload["executed_operation_ids"])),
            payload["status"],
            payload["reason_code"],
            payload["completed_at_utc"],
        )

    @classmethod
    def from_value(cls, value: object) -> "FixVerification":
        if type(value) is cls:
            return value
        if isinstance(value, cls):
            _fail(DIAGNOSTIC_INVALID_EVENT)
        payload = _fix_verification_payload_from_value(value)
        data = _closed_mapping(value, _FIX_VERIFICATION_FIELDS)
        return cls(
            data["schema"],
            data["fix_verification_id"],
            payload["diagnostic_session_id"],
            payload["failed_before_run_id"],
            payload["failed_before_evidence_id"],
            payload["source_change_declaration_id"],
            payload["fixed_after_run_id"],
            payload["fixed_after_evidence_id"],
            payload["verification_plan_id"],
            payload["verification_plan_digest"],
            tuple(cast(list[str], payload["analysis_ids"])),
            tuple(cast(list[str], payload["analysis_evidence_ids"])),
            tuple(cast(list[str], payload["executed_operation_ids"])),
            payload["status"],
            payload["reason_code"],
            payload["completed_at_utc"],
        )

    def to_dict(self) -> dict[str, object]:
        payload = _fix_verification_payload_from_value(self)
        return {
            "schema": payload["schema"],
            "fix_verification_id": self.fix_verification_id,
            "diagnostic_session_id": payload["diagnostic_session_id"],
            "failed_before_run_id": payload["failed_before_run_id"],
            "failed_before_evidence_id": payload["failed_before_evidence_id"],
            "source_change_declaration_id": payload["source_change_declaration_id"],
            "fixed_after_run_id": payload["fixed_after_run_id"],
            "fixed_after_evidence_id": payload["fixed_after_evidence_id"],
            "verification_plan_id": payload["verification_plan_id"],
            "verification_plan_digest": payload["verification_plan_digest"],
            "analysis_ids": list(cast(list[str], payload["analysis_ids"])),
            "analysis_evidence_ids": list(cast(list[str], payload["analysis_evidence_ids"])),
            "executed_operation_ids": list(cast(list[str], payload["executed_operation_ids"])),
            "status": payload["status"],
            "reason_code": payload["reason_code"],
            "completed_at_utc": payload["completed_at_utc"],
        }


__all__ = [
    "ACTORS", "CASE_STATES", "DIAGNOSTIC_CODES", "DIAGNOSTIC_EVIDENCE_MISSING", "DIAGNOSTIC_CHAIN_CORRUPT",
    "DIAGNOSTIC_IDENTITY_MISMATCH", "DIAGNOSTIC_INVALID_EVENT", "DIAGNOSTIC_INVALID_TRANSITION",
    "DIAGNOSTIC_LIMIT_EXCEEDED", "DIAGNOSTIC_NOT_FOUND", "DIAGNOSTIC_OPERATION_CONFLICT", "DIAGNOSTIC_PLAN_INVALID",
    "DIAGNOSTIC_REVISION_CONFLICT", "DIAGNOSTIC_SCHEMA", "DIAGNOSTIC_MARKER_SCHEMA",
    "SOURCE_CHANGE_DECLARATION_SCHEMA", "VERIFICATION_PLAN_SCHEMA", "FIX_VERIFICATION_SCHEMA",
    "DiagnosticEvent", "DiagnosticSession", "DiagnosticMarkerRef", "FixVerification",
    "SourceChangeDeclaration", "VerificationPlan",
    "DiagnosticValidationError", "EvidenceAssessment", "EvidenceIdentity", "EVENT_TYPES", "Hypothesis",
    "ObservationPlan", "ObservationResult", "ObservationStep", "RUN_STATES", "STATES",
    "calculate_assessment_id", "calculate_event_digest", "calculate_plan_digest",
    "calculate_fix_verification_id", "calculate_source_change_declaration_id",
    "calculate_verification_plan_digest", "canonical_diagnostic_json_bytes",
]
