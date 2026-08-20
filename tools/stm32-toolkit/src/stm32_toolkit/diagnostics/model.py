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

from stm32_toolkit.evidence import EvidenceIdentity, EvidenceValidationError
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
)
ACTORS = ("user", "tool", "ai-client")
STATES = ("OPEN", "INVESTIGATING")

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
    state: Literal["OPEN", "INVESTIGATING"]
    identity: EvidenceIdentity
    failed_test_run_id: str
    failed_evidence_id: str
    event_head: str
    hypotheses: tuple[Hypothesis, ...]
    observation_plans: tuple[ObservationPlan, ...]
    observation_results: tuple[ObservationResult, ...]

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
        if not isinstance(self.hypotheses, tuple) or not isinstance(self.observation_plans, tuple) or not isinstance(self.observation_results, tuple):
            _fail(DIAGNOSTIC_INVALID_EVENT)
        if len(self.hypotheses) > MAX_HYPOTHESES or len(self.observation_plans) > MAX_PLANS:
            _fail(DIAGNOSTIC_LIMIT_EXCEEDED)
        if len(self.observation_results) > MAX_RESULTS:
            _fail(DIAGNOSTIC_LIMIT_EXCEEDED)
        if not all(isinstance(item, Hypothesis) for item in self.hypotheses):
            _fail(DIAGNOSTIC_INVALID_EVENT)
        if not all(isinstance(item, ObservationPlan) for item in self.observation_plans):
            _fail(DIAGNOSTIC_INVALID_EVENT)
        if not all(isinstance(item, ObservationResult) for item in self.observation_results):
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
        object.__setattr__(self, "diagnostic_session_id", session_id)
        object.__setattr__(self, "revision", revision)
        object.__setattr__(self, "failed_test_run_id", run_id)
        object.__setattr__(self, "failed_evidence_id", evidence_id)
        object.__setattr__(self, "event_head", event_head)
        object.__setattr__(self, "hypotheses", tuple(self.hypotheses))
        object.__setattr__(self, "observation_plans", tuple(self.observation_plans))
        object.__setattr__(self, "observation_results", tuple(self.observation_results))

    @classmethod
    def from_value(cls, value: object) -> "DiagnosticSession":
        _reject_tuples(value)
        data = _keys(
            value,
            {
                "diagnostic_session_id", "revision", "state", "identity", "failed_test_run_id", "failed_evidence_id",
                "event_head", "hypotheses", "observation_plans", "observation_results",
            },
        )
        hypotheses = data["hypotheses"]
        plans = data["observation_plans"]
        results = data["observation_results"]
        if not isinstance(hypotheses, list) or not isinstance(plans, list) or not isinstance(results, list):
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
        )

    def to_dict(self) -> dict[str, object]:
        return {
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


__all__ = [
    "ACTORS", "CASE_STATES", "DIAGNOSTIC_CODES", "DIAGNOSTIC_EVIDENCE_MISSING", "DIAGNOSTIC_CHAIN_CORRUPT",
    "DIAGNOSTIC_IDENTITY_MISMATCH", "DIAGNOSTIC_INVALID_EVENT", "DIAGNOSTIC_INVALID_TRANSITION",
    "DIAGNOSTIC_LIMIT_EXCEEDED", "DIAGNOSTIC_NOT_FOUND", "DIAGNOSTIC_OPERATION_CONFLICT", "DIAGNOSTIC_PLAN_INVALID",
    "DIAGNOSTIC_REVISION_CONFLICT", "DIAGNOSTIC_SCHEMA", "DiagnosticEvent", "DiagnosticSession",
    "DiagnosticValidationError", "EvidenceAssessment", "EvidenceIdentity", "EVENT_TYPES", "Hypothesis",
    "ObservationPlan", "ObservationResult", "ObservationStep", "RUN_STATES", "STATES",
    "calculate_assessment_id", "calculate_event_digest", "calculate_plan_digest", "canonical_diagnostic_json_bytes",
]
