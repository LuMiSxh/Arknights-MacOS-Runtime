# SPDX-License-Identifier: MPL-2.0

from scripts.arm64 import llvm_mingw


def _run_main(monkeypatch, lock: dict, capsys) -> str:
    monkeypatch.setattr(llvm_mingw, "load_lock", lambda **kwargs: lock)
    assert llvm_mingw.main() == 0
    return capsys.readouterr().out


def test_prints_two_empty_lines_when_the_lock_has_no_pin(monkeypatch, capsys) -> None:
    assert _run_main(monkeypatch, {"toolchain": {}}, capsys) == "\n\n"


def test_prints_the_pinned_url_and_sha256(monkeypatch, capsys) -> None:
    lock = {
        "toolchain": {
            "llvmMingw": {
                "url": "https://toolchains.example/llvm-mingw.tar.xz",
                "sha256": "a" * 64,
            }
        }
    }

    assert _run_main(monkeypatch, lock, capsys) == (
        "https://toolchains.example/llvm-mingw.tar.xz\n" + "a" * 64 + "\n"
    )
