from pathlib import Path


def test_windows_native_install_path_docs_match_installer() -> None:
    doc = Path("website/docs/user-guide/windows-native.md").read_text()
    install = Path("scripts/install.ps1").read_text()

    # The launchers live in the managed binary dir OUTSIDE the git checkout
    # (HAISHUI_HOME\bin, next to the managed uv) — NOT the whole venv\Scripts
    # (which would shadow the user's python, #83797) and NOT a dir inside
    # the checkout (which `haishui update`'s autostash swept off disk).
    assert "%LOCALAPPDATA%\\haishui\\bin" in doc
    assert (
        "Get-Command haishui        # should print "
        "C:\\Users\\<you>\\AppData\\Local\\haishui\\bin\\haishui.exe"
    ) in doc
    # Installer exposes $HaishuiHome\bin, and must copy the launchers into it.
    assert '$haishuiBin = "$HaishuiHome\\bin"' in install
    assert "haishui.exe" in install and "haishui-acp.exe" in install
    # Guard against regressions to either legacy layout.
    assert '$haishuiBin = "$InstallDir\\venv\\Scripts"' not in install
    assert '$haishuiBin = "$InstallDir\\bin"' not in install
