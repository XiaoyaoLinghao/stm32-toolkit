import shutil
from pathlib import Path

import pytest


FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def copy_fixture():
    def copy(name: str, destination: Path) -> None:
        shutil.copyfile(FIXTURES / name, destination)

    return copy


@pytest.fixture
def configured_project(tmp_path: Path, copy_fixture) -> Path:
    copy_fixture("valid-project.json", tmp_path / ".stm32-project.json")
    (tmp_path / "App").mkdir()
    (tmp_path / "App/main.c").write_text("int main(void) { return 0; }\n", encoding="utf-8")
    (tmp_path / "build-fw").mkdir()
    (tmp_path / "build-fw/firmware.elf").write_bytes(b"ELF fixture")
    (tmp_path / "CMakeLists.txt").write_text(
        "cmake_minimum_required(VERSION 3.24)\n", encoding="utf-8"
    )
    return tmp_path
