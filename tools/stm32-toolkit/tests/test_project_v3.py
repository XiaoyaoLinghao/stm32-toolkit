from __future__ import annotations

import json
import stat
from dataclasses import asdict
from importlib import resources
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from stm32_toolkit import __version__
import stm32_toolkit.project_model as model_mod
from stm32_toolkit.project_model import (
    HostTestConfig,
    MemoryMailboxTransportOptions,
    ProjectManifestError,
    RttTransportOptions,
    SemihostingTransportOptions,
    TargetTestConfig,
    TestingConfig as ProjectTestingConfig,
    UartTransportOptions,
    load_project_model,
)


MANIFEST_NAME = ".stm32-project.json"


def _v2_payload() -> dict:
    return {
        "schemaVersion": 2,
        "logicalProjectId": "12345678-1234-5678-1234-567812345678",
        "generatedBy": {"tool": "stm32-toolkit", "version": __version__},
        "project": {"name": "firmware", "origin": "manual"},
        "target": {"device": "STM32F429ZGTx", "core": "cortex-m4"},
        "framework": {"type": "spl", "version": None},
        "build": {
            "sources": ["App/main.c"],
            "includePaths": [],
            "defines": [],
            "compileOptions": [],
            "assemblySources": [],
            "presets": [],
            "elf": "build-fw/firmware.elf",
        },
        "memory": {"source": "manual", "regions": []},
        "debug": {"backend": "pyocd", "target": "stm32f429zgtx", "svd": None},
        "generation": {
            "cubeMxIoc": None,
            "managedManifest": ".stm32-toolkit/generated-files.json",
            "generatedDirectories": [],
            "userDirectories": [],
        },
    }


def _v3_payload(kind: str = "memory-mailbox") -> dict:
    payload = _v2_payload()
    payload["schemaVersion"] = 3
    options = {
        "memory-mailbox": {"address": 0x20010000, "size": 4096},
        "rtt": {"channel": 0, "controlBlockAddress": 0x20000000},
        "uart": {"port": "COM7", "baud": 115200},
        "semihosting": {},
    }[kind]
    payload["testing"] = {
        "host": {
            "buildPreset": "host-build",
            "ctestPreset": "host-tests",
            "labels": ["unit"],
            "timeout_seconds": 120,
            "environment": {
                "allow": ["STM32TK_TEST_SEED"],
                "values": {"STM32TK_TEST_SEED": "1"},
            },
        },
        "target": {
            "executable": "build/test/firmware-tests.elf",
            "timeout_seconds": 120,
            "transport": {"kind": kind, "options": options},
        },
    }
    return payload


def _write(root: Path, payload: dict) -> None:
    (root / MANIFEST_NAME).write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _schema_error(root: Path, payload: dict) -> ProjectManifestError:
    _write(root, payload)
    with pytest.raises(ProjectManifestError) as caught:
        load_project_model(root)
    assert caught.value.code == "PROJECT_SCHEMA_INVALID"
    return caught.value


def test_v3_model_exposes_distinct_host_presets_without_inference(tmp_path: Path):
    _write(tmp_path, _v3_payload())

    model = load_project_model(tmp_path)

    assert model.schema_version == 3
    assert isinstance(model.testing, ProjectTestingConfig)
    assert isinstance(model.testing.host, HostTestConfig)
    assert model.testing.host.build_preset == "host-build"
    assert model.testing.host.ctest_preset == "host-tests"
    assert model.testing.host.build_preset != model.testing.host.ctest_preset
    assert dict(model.testing.host.environment_values) == {"STM32TK_TEST_SEED": "1"}
    with pytest.raises(TypeError):
        model.testing.host.environment_values["STM32TK_TEST_SEED"] = "2"


def test_v3_target_protocol_defaults_to_v1_without_rewriting_manifest(tmp_path: Path):
    payload = _v3_payload()
    _write(tmp_path, payload)
    before = (tmp_path / MANIFEST_NAME).read_bytes()

    model = load_project_model(tmp_path)

    assert model.testing.target.protocol == "stm32-target-frame/1"
    assert (tmp_path / MANIFEST_NAME).read_bytes() == before
    assert "protocol" not in json.loads(before)["testing"]["target"]


@pytest.mark.parametrize(
    "protocol",
    ["stm32-target-frame/1", "stm32-target-frame/2"],
)
def test_v3_target_protocol_loads_explicit_version(tmp_path: Path, protocol: str):
    payload = _v3_payload()
    payload["testing"]["target"]["protocol"] = protocol
    _write(tmp_path, payload)

    model = load_project_model(tmp_path)

    assert model.testing.target.protocol == protocol


@pytest.mark.parametrize(
    "protocol",
    ["stm32-target-frame/3", "STM32-TARGET-FRAME/2", "stm32-target-frame/2 ", {"version": 2}],
)
def test_v3_target_protocol_rejects_unknown_case_changed_and_non_string_values(
    tmp_path: Path, protocol: object
):
    payload = _v3_payload()
    payload["testing"]["target"]["protocol"] = protocol

    error = _schema_error(tmp_path, payload)

    assert error.details == {"field": "testing.target.protocol", "rule": "enum"}


def test_v3_target_protocol_rejects_unknown_target_fields(tmp_path: Path):
    payload = _v3_payload()
    payload["testing"]["target"]["protocolExtra"] = "stm32-target-frame/2"

    error = _schema_error(tmp_path, payload)

    assert error.details == {
        "field": "testing.target.protocolExtra",
        "rule": "additionalProperties",
    }


def test_v3_target_protocol_survives_public_dataclass_serialization(tmp_path: Path):
    payload = _v3_payload()
    payload["testing"]["target"]["protocol"] = "stm32-target-frame/2"
    _write(tmp_path, payload)

    model = load_project_model(tmp_path)

    assert asdict(model.testing.target)["protocol"] == "stm32-target-frame/2"


@pytest.mark.parametrize("missing", ["buildPreset", "ctestPreset"])
def test_host_requires_each_preset_independently(tmp_path: Path, missing: str):
    payload = _v3_payload()
    del payload["testing"]["host"][missing]

    error = _schema_error(tmp_path, payload)

    assert error.details == {"field": f"testing.host.{missing}", "rule": "required"}


def test_v2_reader_has_no_testing_config(tmp_path: Path):
    _write(tmp_path, _v2_payload())

    model = load_project_model(tmp_path)

    assert model.schema_version == 2
    assert model.testing is None


def test_v1_uses_explicit_compatibility_route(tmp_path: Path):
    fixture = Path(__file__).parent / "fixtures" / "valid-project.json"
    (tmp_path / MANIFEST_NAME).write_bytes(fixture.read_bytes())

    with pytest.raises(ProjectManifestError) as caught:
        load_project_model(tmp_path)

    assert caught.value.code == "PROJECT_SCHEMA_VERSION_UNSUPPORTED"
    assert caught.value.details == {"schemaVersion": 1, "supported": [2, 3]}


@pytest.mark.parametrize(
    ("kind", "option_type"),
    [
        ("memory-mailbox", MemoryMailboxTransportOptions),
        ("rtt", RttTransportOptions),
        ("uart", UartTransportOptions),
        ("semihosting", SemihostingTransportOptions),
    ],
)
def test_all_closed_target_transport_options_are_typed(
    tmp_path: Path, kind: str, option_type: type
):
    _write(tmp_path, _v3_payload(kind))

    model = load_project_model(tmp_path)

    assert isinstance(model.testing.target, TargetTestConfig)
    assert model.testing.target.transport.kind == kind
    assert isinstance(model.testing.target.transport.options, option_type)


@pytest.mark.parametrize(
    ("kind", "field", "bad", "rule"),
    [
        ("memory-mailbox", "address", True, "type"),
        ("memory-mailbox", "address", 1.0, "type"),
        ("memory-mailbox", "address", -1, "minimum"),
        ("memory-mailbox", "address", 0x1_0000_0000, "maximum"),
        ("memory-mailbox", "size", 0, "minimum"),
        ("memory-mailbox", "size", 65537, "maximum"),
        ("rtt", "channel", -1, "minimum"),
        ("rtt", "channel", 16, "maximum"),
        ("rtt", "controlBlockAddress", "0x20000000", "type"),
        ("uart", "baud", 9600.0, "type"),
        ("uart", "baud", 14400, "enum"),
    ],
)
def test_transport_numeric_contract_is_strict(
    tmp_path: Path, kind: str, field: str, bad: object, rule: str
):
    payload = _v3_payload(kind)
    payload["testing"]["target"]["transport"]["options"][field] = bad

    error = _schema_error(tmp_path, payload)

    assert error.details == {
        "field": f"testing.target.transport.options.{field}",
        "rule": rule,
    }


@pytest.mark.parametrize(
    ("section", "bad", "rule"),
    [
        ("host", True, "type"),
        ("host", 0, "minimum"),
        ("host", 3601, "maximum"),
        ("target", 1.0, "type"),
        ("target", 0, "minimum"),
        ("target", 3601, "maximum"),
    ],
)
def test_host_and_target_timeout_bounds_are_strict(
    tmp_path: Path, section: str, bad: object, rule: str
):
    payload = _v3_payload()
    payload["testing"][section]["timeout_seconds"] = bad

    error = _schema_error(tmp_path, payload)

    assert error.details == {
        "field": f"testing.{section}.timeout_seconds",
        "rule": rule,
    }


@pytest.mark.parametrize(
    ("mutation", "field", "rule"),
    [
        (lambda host: host["labels"].append("unit"), "testing.host.labels", "uniqueItems"),
        (
            lambda host: host["labels"].extend(f"label-{index}" for index in range(32)),
            "testing.host.labels",
            "maxItems",
        ),
        (
            lambda host: host["environment"]["allow"].extend(
                f"STM32TK_{index}" for index in range(32)
            ),
            "testing.host.environment.allow",
            "maxItems",
        ),
        (
            lambda host: host["environment"]["allow"].append("BAD=NAME"),
            "testing.host.environment.allow[1]",
            "pattern",
        ),
        (
            lambda host: host["environment"]["values"].__setitem__("NOT_ALLOWED", "x"),
            "testing.host.environment.values.NOT_ALLOWED",
            "allowlisted",
        ),
        (
            lambda host: host["environment"]["values"].__setitem__(
                "STM32TK_TEST_SEED", "x" * 4097
            ),
            "testing.host.environment.values.STM32TK_TEST_SEED",
            "maxLength",
        ),
    ],
)
def test_labels_and_environment_are_closed_and_bounded(
    tmp_path: Path, mutation, field: str, rule: str
):
    payload = _v3_payload()
    mutation(payload["testing"]["host"])

    error = _schema_error(tmp_path, payload)

    assert error.details == {"field": field, "rule": rule}


@pytest.mark.parametrize(
    ("mutation", "field", "rule"),
    [
        (
            lambda host: host.__setitem__("buildPreset", "x" * 129),
            "testing.host.buildPreset",
            "maxLength",
        ),
        (
            lambda host: host.__setitem__("ctestPreset", "e\u0301"),
            "testing.host.ctestPreset",
            "normalized",
        ),
        (
            lambda host: host["labels"].__setitem__(0, "x" * 129),
            "testing.host.labels[0]",
            "maxLength",
        ),
        (
            lambda host: host["labels"].__setitem__(0, "e\u0301"),
            "testing.host.labels[0]",
            "normalized",
        ),
        (
            lambda host: (
                host["environment"].__setitem__("allow", ["X" * 129]),
                host["environment"].__setitem__("values", {}),
            ),
            "testing.host.environment.allow[0]",
            "maxLength",
        ),
    ],
)
def test_host_strings_use_canonical_nfc_and_utf8_bounds(
    tmp_path: Path, mutation, field: str, rule: str
):
    payload = _v3_payload()
    mutation(payload["testing"]["host"])
    error = _schema_error(tmp_path, payload)
    assert error.details == {"field": field, "rule": rule}


@pytest.mark.parametrize(
    ("kind", "extra_field"),
    [
        ("memory-mailbox", "channel"),
        ("rtt", "address"),
        ("uart", "flowControl"),
        ("semihosting", "hostFiles"),
    ],
)
def test_transport_options_reject_unknown_fields(
    tmp_path: Path, kind: str, extra_field: str
):
    payload = _v3_payload(kind)
    payload["testing"]["target"]["transport"]["options"][extra_field] = 1

    error = _schema_error(tmp_path, payload)

    assert error.details == {
        "field": f"testing.target.transport.options.{extra_field}",
        "rule": "additionalProperties",
    }


@pytest.mark.parametrize(
    ("value", "rule"),
    [
        ("", "minLength"),
        ("COM\x00BAD", "pattern"),
        ("C" * 257, "maxLength"),
        ("e\u0301", "normalized"),
    ],
)
def test_uart_port_has_closed_utf8_string_contract(tmp_path: Path, value: str, rule: str):
    payload = _v3_payload("uart")
    payload["testing"]["target"]["transport"]["options"]["port"] = value

    error = _schema_error(tmp_path, payload)

    assert error.details == {
        "field": "testing.target.transport.options.port",
        "rule": rule,
    }


@pytest.mark.parametrize("value", ["../firmware.elf", "/tmp/firmware.elf", "C:/fw.elf", "C:fw.elf"])
def test_target_executable_must_be_workspace_relative(tmp_path: Path, value: str):
    payload = _v3_payload()
    payload["testing"]["target"]["executable"] = value

    error = _schema_error(tmp_path, payload)

    assert error.details == {
        "field": "testing.target.executable",
        "rule": "pattern",
    }


def test_standalone_schema_and_model_layer_acceptance_matrix(tmp_path: Path):
    schema = json.loads(resources.files("stm32_toolkit").joinpath("schemas/stm32-project.schema.json").read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema)
    ascii_too_long = _v3_payload()
    ascii_too_long["testing"]["host"]["buildPreset"] = "x" * 129
    assert any(error.validator == "maxLength" for error in validator.iter_errors(ascii_too_long))
    byte_too_long = _v3_payload()
    byte_too_long["testing"]["host"]["buildPreset"] = "é" * 65
    assert not list(validator.iter_errors(byte_too_long))
    error = _schema_error(tmp_path, byte_too_long)
    assert error.details == {"field": "testing.host.buildPreset", "rule": "maxUtf8Bytes"}
    lexical_escape = _v3_payload()
    lexical_escape["testing"]["target"]["executable"] = "../outside.elf"
    assert any(error.validator == "pattern" for error in validator.iter_errors(lexical_escape))
    executable_nfc = _v3_payload()
    executable_nfc["testing"]["target"]["executable"] = "build/e\u0301.elf"
    assert not list(validator.iter_errors(executable_nfc))
    assert _schema_error(tmp_path, executable_nfc).details == {
        "field": "testing.target.executable", "rule": "normalized"
    }
    executable_bytes = _v3_payload()
    executable_bytes["testing"]["target"]["executable"] = "界" * 1366
    assert not list(validator.iter_errors(executable_bytes))
    assert _schema_error(tmp_path, executable_bytes).details == {
        "field": "testing.target.executable", "rule": "maxUtf8Bytes"
    }
    environment_schema = schema["properties"]["testing"]["properties"]["host"]["properties"]["environment"]
    assert "allowlist relationship" in environment_schema["description"]


@pytest.mark.parametrize(
    ("path", "field"),
    [
        (("testing",), "extra"),
        (("testing", "host"), "command"),
        (("testing", "target"), "probe"),
        (("testing", "target", "transport"), "fallback"),
    ],
)
def test_v3_objects_reject_unknown_fields(tmp_path: Path, path: tuple[str, ...], field: str):
    payload = _v3_payload()
    target = payload
    for component in path:
        target = target[component]
    target[field] = "forbidden"

    error = _schema_error(tmp_path, payload)

    assert error.details == {
        "field": ".".join((*path, field)),
        "rule": "additionalProperties",
    }


def test_testing_object_requires_host_or_target(tmp_path: Path):
    payload = _v3_payload()
    payload["testing"] = {}

    error = _schema_error(tmp_path, payload)

    assert error.details == {"field": "testing", "rule": "anyOf"}


def test_schema_mirror_is_byte_identical():
    package_schema = resources.files("stm32_toolkit").joinpath(
        "schemas/stm32-project.schema.json"
    )
    root_schema = Path(__file__).resolve().parents[3] / "schemas/stm32-project.schema.json"

    assert package_schema.read_bytes() == root_schema.read_bytes()


def test_host_only_and_target_only_testing_configs_are_supported(tmp_path: Path):
    host_only = _v3_payload()
    del host_only["testing"]["target"]
    _write(tmp_path, host_only)
    host_model = load_project_model(tmp_path)
    assert host_model.testing.host is not None
    assert host_model.testing.target is None

    target_only = _v3_payload()
    del target_only["testing"]["host"]
    _write(tmp_path, target_only)
    target_model = load_project_model(tmp_path)
    assert target_model.testing.host is None
    assert target_model.testing.target is not None


def test_rtt_control_block_address_is_optional(tmp_path: Path):
    payload = _v3_payload("rtt")
    del payload["testing"]["target"]["transport"]["options"]["controlBlockAddress"]
    _write(tmp_path, payload)
    model = load_project_model(tmp_path)
    assert model.testing.target.transport.options.control_block_address is None


@pytest.mark.parametrize(
    ("payload", "details"),
    [
        ([], {"field": "$", "rule": "type"}),
        ({}, {"field": "schemaVersion", "rule": "required"}),
        (
            {"schemaVersion": 99},
            {"schemaVersion": 99, "supported": [2, 3]},
        ),
    ],
)
def test_model_reader_rejects_malformed_dispatch_inputs(
    tmp_path: Path, payload: object, details: dict
):
    (tmp_path / MANIFEST_NAME).write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ProjectManifestError) as caught:
        load_project_model(tmp_path)
    assert caught.value.details == details


def test_v3_rejects_duplicate_memory_region_names(tmp_path: Path):
    payload = _v3_payload()
    payload["memory"]["regions"] = [
        {"name": "RAM", "origin": 0, "length": 1, "attributes": "rw-"},
        {"name": "RAM", "origin": 1, "length": 1, "attributes": "rw-"},
    ]
    error = _schema_error(tmp_path, payload)
    assert error.details == {"field": "memory.regions", "rule": "uniqueRegionName"}


def test_model_validation_defenses_cover_non_path_and_non_region_inputs(tmp_path: Path):
    model_mod._validate_path_value(tmp_path, 17, "field", {})
    model_mod._validate_unique_region_names("not-a-list")


def test_containment_resolves_when_an_existing_component_is_a_link(
    tmp_path: Path, monkeypatch
):
    monkeypatch.setattr(model_mod, "_has_existing_link_component", lambda *args: True)
    monkeypatch.setattr(model_mod, "_resolved_within", lambda *args: True)
    assert model_mod._contained_in_root(tmp_path, "linked/file.elf", {}) is True


def test_link_detector_accepts_a_real_symlink_mode_record():
    class FakeStat:
        st_mode = stat.S_IFLNK
        st_file_attributes = 0

    assert model_mod._is_link_or_reparse(FakeStat()) is True


def test_explicit_schema_helpers_cover_valid_schema_success():
    payload = {"value": 1}
    schema = {"type": "object", "required": ["value"]}
    assert model_mod.first_schema_error(payload, schema) is None
    model_mod._validate_schema(payload, schema, 3)
