"""Offline integrity boundaries for the Monitor source catalog.

The first case exercises the real project-model/input-snapshot/fresh-firmware
fallback (``_offline_facts`` is not substituted) while a synthetic local
adapter/index deliberately mutates an owned project during indexing.  The
later provider fixtures substitute ``_offline_facts``, a synthetic local
adapter plan/index and a synthetic ELF/DWARF provider value; those inputs feed
the real ``_load_base`` admission plus real attribution, materialization and
cursor validation.  No firmware, probe or backend is opened.
"""

from __future__ import annotations

import asyncio
import base64
import json
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest

import stm32_monitor.source_catalog as module
from stm32_monitor.source_catalog import SourceCatalogFailure, SourceCatalogProvider
from stm32_toolkit import __version__ as toolkit_version
from stm32_toolkit.debug.dwarf import DwarfSourceSymbol
from stm32_toolkit.debug.source import SourceDeclaration, SourceIndex, SourcePlan
from stm32_toolkit.debug.types import DwarfError, DwarfSelection, DwarfType


FIXTURES = (
    Path(__file__).resolve().parents[2]
    / "stm32-toolkit"
    / "tests"
    / "fixtures"
)
_SCALAR = DwarfType("integer", "int", 4)


def _write_synthetic_project(root: Path) -> Path:
    """A minimal owned project whose real offline facts need no firmware."""
    payload = json.loads(
        (FIXTURES / "valid-project.json").read_text(encoding="utf-8")
    )
    payload["schemaVersion"] = 3
    payload["generatedBy"] = {"tool": "stm32-toolkit", "version": toolkit_version}
    payload["build"]["presets"] = []
    payload["memory"] = {"source": "manual", "regions": []}
    payload["generation"] = {
        "cubeMxIoc": None,
        "managedManifest": ".stm32-toolkit/generated-files.json",
        "generatedDirectories": [],
        "userDirectories": [],
    }
    (root / "App").mkdir(parents=True)
    (root / "App" / "main.c").write_text("int counter = 1;\n", encoding="utf-8")
    (root / "App" / "extra.h").write_text("#define EXTRA 1\n", encoding="utf-8")
    (root / ".stm32-toolkit").mkdir()
    (root / ".stm32-toolkit" / "generated-files.json").write_text(
        json.dumps(
            {
                "schemaVersion": 1,
                "tool": "stm32-toolkit",
                "toolVersion": toolkit_version,
                "templateVersion": 1,
                "projectManifestSha256": "0" * 64,
                "files": [],
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    (root / ".stm32-project.json").write_text(
        json.dumps(payload, sort_keys=True), encoding="utf-8"
    )
    return root


class _Adapter:
    def __init__(self, index: SourceIndex) -> None:
        self.index_result = index
        self.index_calls = 0
        self.close_calls = 0

    def plan(self, _model: object) -> SourcePlan:
        return SourcePlan((), "manifest", "version", "f" * 64)

    def index(self, _model: object, _plan: SourcePlan) -> SourceIndex:
        self.index_calls += 1
        return self.index_result

    def close(self) -> None:
        self.close_calls += 1


class _Catalog:
    """Synthetic DWARF provider value returned by ``DwarfCatalog.from_elf``."""

    elf_sha256 = "e" * 64
    source_metadata_truncated = False
    readable_regions = ((0x20000000, 0x20001000),)

    def __init__(self, declarations: tuple[SourceDeclaration, ...]) -> None:
        self.symbols = tuple(
            DwarfSourceSymbol(
                declaration.name,
                declaration.file,
                declaration.line,
                None,
                declaration.function,
                declaration.translation_units[0],
                _SCALAR,
                0x20000000 + 4 * ordinal,
                None,
                None,
                cu_offset=0,
                die_offset=ordinal + 1,
                storage=declaration.storage,
                scope_kind=declaration.scope_kind,
            )
            for ordinal, declaration in enumerate(declarations)
        )

    def source_declarations(self) -> tuple[DwarfSourceSymbol, ...]:
        return self.symbols

    def source_functions(self) -> tuple[()]:
        return ()

    def lookup(self, selector: str) -> DwarfSelection:
        symbol = next(item for item in self.symbols if item.name == selector)
        assert symbol.address is not None and symbol.dwarf_type is not None
        return DwarfSelection(selector, symbol.address, symbol.dwarf_type)


def _declarations(names: tuple[str, ...]) -> tuple[SourceDeclaration, ...]:
    return tuple(
        SourceDeclaration(
            f"{ordinal + 1:064x}",
            f"{ordinal + 1:064x}",
            name,
            "int",
            "Src/main.c",
            ordinal + 1,
            1,
            "none",
            "global",
            None,
            (),
            ("Src/main.c",),
        )
        for ordinal, name in enumerate(names)
    )


def _provider(
    monkeypatch: pytest.MonkeyPatch,
    root: Path,
    names: tuple[str, ...] = ("alpha", "alps", "beta"),
) -> SourceCatalogProvider:
    declarations = _declarations(names)
    index = SourceIndex(
        "engine", "version", "manifest", 1, 1, (), True, declarations, "f" * 64
    )
    region = SimpleNamespace(
        name="RAM", origin=0x20000000, length=0x1000, attributes="rw"
    )
    model = SimpleNamespace(
        project_root=root,
        logical_project_id="project",
        target=SimpleNamespace(device="STM32F407VG"),
        memory=SimpleNamespace(regions=(region,)),
    )
    # This fixture substitutes _offline_facts, a synthetic local adapter
    # plan/index and a synthetic ELF/DWARF provider value.  Those inputs feed
    # the real _load_base admission, attribution, materialization and cursor
    # validation.
    facts = module._Facts(
        model, "b" * 64, "build", "e" * 64, "firmware.elf", 4096,
        ("Src/main.c",), ("Src/main.c",),
    )
    monkeypatch.setattr(module, "_offline_facts", lambda _root: facts)
    monkeypatch.setattr(
        module.DwarfCatalog,
        "from_elf",
        staticmethod(lambda *_args, **_kwargs: _Catalog(declarations)),
    )
    return SourceCatalogProvider(root, "workspace", "session", _Adapter(index))


def _envelope(cursor: str) -> bytes:
    encoded = cursor.encode("ascii")
    return base64.urlsafe_b64decode(encoded + b"=" * (-len(encoded) % 4))


def _canonical(envelope: bytes) -> bytes:
    return base64.urlsafe_b64encode(envelope).rstrip(b"=")


def _mac_flipped(cursor: str) -> str:
    envelope = _envelope(cursor)
    raw, mac = envelope[:-32], bytearray(envelope[-32:])
    mac[0] ^= 0x01
    return _canonical(raw + bytes(mac)).decode("ascii")


def _noncanonical_padding(cursor: str) -> str | None:
    """Re-encode with non-zero unused bits, which Python decoders tolerate."""
    envelope = _envelope(cursor)
    remainder = len(envelope) % 3
    if remainder == 0:
        return None
    alphabet = b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"
    encoded = _canonical(envelope)
    unused_bits = 4 if remainder == 1 else 2
    last = alphabet.index(encoded[-1:])
    mutated = encoded[:-1] + bytes([alphabet[last ^ 1]])
    assert (last ^ 1) >> unused_bits == last >> unused_bits
    encoded_input = mutated + b"=" * (-len(mutated) % 4)
    assert base64.urlsafe_b64decode(encoded_input) == envelope
    assert _canonical(envelope) != mutated
    return mutated.decode("ascii")


def test_real_offline_facts_snapshot_and_mid_index_change_invalidate_request(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = _write_synthetic_project(tmp_path / "project")

    facts = module._offline_facts(root)
    assert facts.policy == module.SOURCE_LOCAL_HEADERS_POLICY
    assert facts.build_id is None and facts.elf_sha is None
    assert facts.elf_path is None and facts.elf_size is None
    assert "App/main.c" in facts.source_files
    assert "App/extra.h" in facts.source_files
    assert "App/extra.h" in facts.snapshot_paths

    declaration = SourceDeclaration(
        "1" * 64, "1" * 64, "counter", "int", "App/main.c", 1, 5,
        "none", "global", None, (), ("App/main.c",),
    )
    index = SourceIndex(
        "engine", "version", "manifest", 1, 1, (), True, (declaration,), "f" * 64
    )

    class _MutatingAdapter(_Adapter):
        def index(self, model: object, plan: SourcePlan) -> SourceIndex:
            result = super().index(model, plan)
            if self.index_calls == 2:
                (root / "App" / "main.c").write_text(
                    "int counter = 2;\n", encoding="utf-8"
                )
            return result

    adapter = _MutatingAdapter(index)
    provider = SourceCatalogProvider(root, "workspace", "session", adapter)

    async def scenario() -> None:
        tree = await provider.tree(
            query="", cursor=None, limit=100, parent_id=None, catalog_id=None,
            binding=None, binding_epoch=0,
        )
        assert tree["coverage"]["complete"] is True
        assert tree["items"] == [] and tree["total"] == 0
        page = await provider.page(
            query="", cursor=None, limit=100, parent_id=None,
            catalog_id=tree["catalogId"], binding=None, binding_epoch=0,
        )
        assert page["items"] == [] and page["total"] == 0
        view = provider._views[tree["catalogId"]]
        assert [entry.name for entry in view.index.declarations] == ["counter"]

        with pytest.raises(SourceCatalogFailure) as changed:
            await provider.page(
                query="", cursor=None, limit=100, parent_id=None,
                catalog_id=None, binding=None, binding_epoch=0, refresh=True,
            )
        assert changed.value.code == "MONITOR_SOURCE_CONTEXT_CHANGED"
        assert changed.value.message == "Source or firmware changed while indexing"
        assert provider._bases == {}
        assert adapter.index_calls == 2

        with pytest.raises(SourceCatalogFailure) as stale:
            await provider.page(
                query="", cursor=None, limit=100, parent_id=None,
                catalog_id=tree["catalogId"], binding=None, binding_epoch=0,
            )
        assert stale.value.code == "MONITOR_SOURCE_CONTEXT_CHANGED"
        assert stale.value.message == "Source catalog identity changed"

        (root / "App" / "main.c").write_text("int counter = 1;\n", encoding="utf-8")
        recovered = await provider.page(
            query="", cursor=None, limit=100, parent_id=None,
            catalog_id=None, binding=None, binding_epoch=0, refresh=True,
        )
        assert recovered["catalogId"] == tree["catalogId"]
        assert recovered["coverage"]["complete"] is True
        assert adapter.index_calls == 4

    try:
        asyncio.run(scenario())
    finally:
        provider.close()


def test_in_memory_source_file_limit_refuses_before_any_view_or_write(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    model = SimpleNamespace(
        project_root=tmp_path,
        logical_project_id="project",
        target=SimpleNamespace(device="STM32F407VG"),
    )
    paths = tuple(f"Src/f{index}.c" for index in range(10_001))
    facts = module._Facts(
        model, "b" * 64, None, None, None, None, paths, paths
    )
    monkeypatch.setattr(module, "_offline_facts", lambda _root: facts)
    index = SourceIndex(
        "engine", "version", "manifest", 1, 1, (), True, (), "f" * 64
    )
    provider = SourceCatalogProvider(
        tmp_path, "workspace", "session", _Adapter(index)
    )
    before = tuple(sorted(tmp_path.iterdir()))

    async def scenario() -> None:
        with pytest.raises(SourceCatalogFailure) as limited:
            await provider.page(
                query="", cursor=None, limit=1, parent_id=None,
                catalog_id=None, binding=None, binding_epoch=0,
            )
        assert limited.value.code == "MONITOR_SOURCE_INDEX_FAILED"
        assert limited.value.message == "Source file limit was reached"
        assert provider._bases == {} and provider._views == {}

    try:
        asyncio.run(scenario())
    finally:
        provider.close()
    assert tuple(sorted(tmp_path.iterdir())) == before


def test_compiled_debug_directory_limit_is_classified_before_any_base(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    model = SimpleNamespace(
        project_root=tmp_path,
        logical_project_id="project",
        target=SimpleNamespace(device="STM32F407VG"),
        memory=SimpleNamespace(regions=()),
    )
    facts = module._Facts(
        model, "b" * 64, "build", "e" * 64, "firmware.elf", 1
    )
    monkeypatch.setattr(module, "_offline_facts", lambda _root: facts)

    def limited(*_args: object, **_kwargs: object) -> object:
        raise DwarfError("DWARF_CATALOG_LIMIT_EXCEEDED", "debug directory limit")

    monkeypatch.setattr(module.DwarfCatalog, "from_elf", staticmethod(limited))
    index = SourceIndex(
        "engine", "version", "manifest", 1, 1, (), True, (), "f" * 64
    )
    provider = SourceCatalogProvider(
        tmp_path, "workspace", "session", _Adapter(index)
    )

    async def scenario() -> None:
        with pytest.raises(SourceCatalogFailure) as limited_failure:
            await provider.tree(
                query="", cursor=None, limit=1, parent_id=None,
                catalog_id=None, binding=None, binding_epoch=0,
            )
        assert limited_failure.value.code == "MONITOR_SOURCE_INDEX_FAILED"
        assert (
            limited_failure.value.message
            == "Compiled debug directory limit was reached"
        )
        assert provider._bases == {} and provider._views == {}

    try:
        asyncio.run(scenario())
    finally:
        provider.close()


def test_genuine_catalog_cursors_reject_length_canonical_and_mac_mutations(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    provider = _provider(monkeypatch, tmp_path)

    async def scenario() -> None:
        first = await provider.page(
            query="", cursor=None, limit=1, parent_id=None, catalog_id=None,
            binding=None, binding_epoch=0,
        )
        assert first["nextCursor"] is not None
        catalog = first["catalogId"]
        genuine: dict[str, str] = {}
        for query in ("", "a", "al"):
            page = await provider.page(
                query=query, cursor=None, limit=1, parent_id=None,
                catalog_id=catalog, binding=None, binding_epoch=0,
            )
            assert page["nextCursor"] is not None
            genuine[query] = page["nextCursor"]
        views_before = tuple(provider._views)

        overlong = genuine[""] + "A" * (module._MAX_CURSOR_LENGTH + 1 - len(genuine[""]))
        assert len(overlong) > module._MAX_CURSOR_LENGTH
        noncanonical = next(
            (
                candidate
                for cursor in genuine.values()
                for candidate in (_noncanonical_padding(cursor),)
                if candidate is not None
            ),
            None,
        )
        assert noncanonical is not None
        mac_flipped = _mac_flipped(genuine[""])

        for cursor in (overlong, noncanonical, mac_flipped):
            with pytest.raises(SourceCatalogFailure) as invalid:
                await provider.page(
                    query="", cursor=cursor, limit=1, parent_id=None,
                    catalog_id=catalog, binding=None, binding_epoch=0,
                )
            assert invalid.value.code == "MONITOR_SOURCE_CONTEXT_CHANGED"
            assert invalid.value.message == "Source catalog cursor is invalid"

        with pytest.raises(SourceCatalogFailure) as tree_invalid:
            await provider.tree(
                query="", cursor=mac_flipped, limit=1, parent_id=None,
                catalog_id=catalog, binding=None, binding_epoch=0,
            )
        assert tree_invalid.value.code == "MONITOR_SOURCE_CONTEXT_CHANGED"
        assert tree_invalid.value.message == "Source catalog cursor is invalid"

        assert tuple(provider._views) == views_before
        resumed = await provider.page(
            query="", cursor=genuine[""], limit=1, parent_id=None,
            catalog_id=catalog, binding=None, binding_epoch=0,
        )
        assert [item["name"] for item in resumed["items"]] == ["alps"]

    try:
        asyncio.run(scenario())
    finally:
        provider.close()


def test_valid_format_stale_handles_and_closed_provider_are_refused(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    provider = _provider(monkeypatch, tmp_path)
    foreign = "a" * 64

    async def expect(message: str, operation) -> None:
        with pytest.raises(SourceCatalogFailure) as refused:
            await operation()
        assert refused.value.code == "MONITOR_SOURCE_CONTEXT_CHANGED"
        assert refused.value.message == message

    async def scenario() -> None:
        tree = await provider.tree(
            query="", cursor=None, limit=100, parent_id=None, catalog_id=None,
            binding=None, binding_epoch=0,
        )
        file_id = tree["items"][0]["id"]
        catalog = tree["catalogId"]
        scopes = await provider.tree(
            query="", cursor=None, limit=100, parent_id=file_id,
            catalog_id=catalog, binding=None, binding_epoch=0,
        )
        scope_id = scopes["items"][0]["id"]

        await expect(
            "Source scope changed",
            lambda: provider.page(
                query="", cursor=None, limit=1, parent_id=None,
                scope_id=foreign, catalog_id=catalog, binding=None,
                binding_epoch=0,
            ),
        )
        await expect(
            "Source scope changed",
            lambda: provider.page(
                query="absent", cursor=None, limit=1, parent_id=None,
                scope_id=scope_id, catalog_id=catalog, binding=None,
                binding_epoch=0,
            ),
        )
        await expect(
            "Source catalog parent changed",
            lambda: provider.page(
                query="", cursor=None, limit=1, parent_id=foreign,
                catalog_id=catalog, binding=None, binding_epoch=0,
            ),
        )
        await expect(
            "Source tree parent changed",
            lambda: provider.tree(
                query="", cursor=None, limit=1, parent_id=foreign,
                catalog_id=catalog, binding=None, binding_epoch=0,
            ),
        )
        await expect(
            "Source catalog identity changed",
            lambda: provider.tree(
                query="", cursor=None, limit=1, parent_id=None,
                catalog_id="b" * 64, binding=None, binding_epoch=0,
            ),
        )

        provider.close()
        provider.close()
        assert provider.adapter.close_calls == 2
        assert provider._closed is True
        await expect(
            "Source catalog was closed",
            lambda: provider.page(
                query="", cursor=None, limit=1, parent_id=None,
                catalog_id=None, binding=None, binding_epoch=0,
            ),
        )
        await expect(
            "Source catalog was closed",
            lambda: provider.tree(
                query="", cursor=None, limit=1, parent_id=None,
                catalog_id=None, binding=None, binding_epoch=0,
            ),
        )
        await expect(
            "Source catalog was closed",
            lambda: provider.select(
                catalog_id=catalog, item_id=file_id, selector="alpha",
                binding=None, binding_epoch=0,
            ),
        )

    try:
        asyncio.run(scenario())
    finally:
        provider.close()


def test_close_cancels_a_coalesced_in_flight_base_task(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    class _BlockingAdapter(_Adapter):
        def __init__(self, index: SourceIndex) -> None:
            super().__init__(index)
            self.entered = threading.Event()
            self.release = threading.Event()

        def index(self, model: object, plan: SourcePlan) -> SourceIndex:
            self.entered.set()
            assert self.release.wait(timeout=5)
            return super().index(model, plan)

    declarations = _declarations(("alpha", "alps"))
    index = SourceIndex(
        "engine", "version", "manifest", 1, 1, (), True, declarations, "f" * 64
    )
    model = SimpleNamespace(
        project_root=tmp_path,
        logical_project_id="project",
        target=SimpleNamespace(device="STM32F407VG"),
    )
    facts = module._Facts(
        model, "b" * 64, None, None, None, None,
        ("Src/main.c",), ("Src/main.c",),
    )
    monkeypatch.setattr(module, "_offline_facts", lambda _root: facts)
    adapter = _BlockingAdapter(index)
    provider = SourceCatalogProvider(tmp_path, "workspace", "session", adapter)

    async def scenario() -> None:
        waiter = asyncio.create_task(
            provider.page(
                query="", cursor=None, limit=1, parent_id=None,
                catalog_id=None, binding=None, binding_epoch=0,
            )
        )
        try:
            assert await asyncio.to_thread(adapter.entered.wait, 5)
            task = next(iter(provider._inflight.values()))
            provider.close()
            assert task.cancelling() > 0 or task.cancelled()
        finally:
            adapter.release.set()
        with pytest.raises(asyncio.CancelledError):
            await waiter
        for _ in range(100):
            if not provider._inflight:
                break
            await asyncio.sleep(0.01)
        assert provider._inflight == {}
        assert provider._bases == {} and provider._views == {}

    try:
        asyncio.run(scenario())
    finally:
        adapter.release.set()
        provider.close()
