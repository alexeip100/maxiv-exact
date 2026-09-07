from pathlib import Path



def test_icon_assets_are_bundled_as_package_data():
    root = Path(__file__).resolve().parents[1]
    assets = root / "src" / "flexpes_nexafs" / "assets"
    for name in [
        "flexpes_xas_icon.ico",
        "flexpes_xas_icon.icns",
        "flexpes_xas_icon_64.png",
        "flexpes_xas_icon_128.png",
        "flexpes_xas_icon_256.png",
        "flexpes_xas_icon_512.png",
    ]:
        path = assets / name
        assert path.is_file()
        assert path.stat().st_size > 0



def test_pyproject_includes_icon_package_data():
    root = Path(__file__).resolve().parents[1]
    text = (root / "pyproject.toml").read_text(encoding="utf-8")
    assert '"assets/*.ico"' in text
    assert '"assets/*.icns"' in text
    assert '"assets/*.png"' in text



def test_icon_helpers_expose_cross_platform_asset_paths():
    root = Path(__file__).resolve().parents[1]
    text = (root / "src" / "flexpes_nexafs" / "icon.py").read_text(encoding="utf-8")
    assert "def windows_icon_path()" in text
    assert "def macos_icon_path()" in text
    assert "def linux_icon_png_path(" in text



def test_about_dialog_uses_large_application_logo():
    root = Path(__file__).resolve().parents[1]
    core = (root / "src" / "flexpes_nexafs" / "plotting" / "mixin_core.py").read_text(encoding="utf-8")
    assert "application_icon().pixmap(96, 96)" in core
    assert "box.setIconPixmap(pixmap)" in core


def test_windows_app_user_model_id_is_set_before_qapplication():
    root = Path(__file__).resolve().parents[1]
    text = (root / "src" / "flexpes_nexafs" / "app.py").read_text(encoding="utf-8")
    assert 'SetCurrentProcessExplicitAppUserModelID' in text
    assert '"MAXIV.FlexPES.NEXAFS"' in text
    assert text.index("_set_windows_app_user_model_id()") < text.index("QApplication.instance()")


def test_windows_native_taskbar_icon_is_applied():
    root = Path(__file__).resolve().parents[1]
    app = (root / "src" / "flexpes_nexafs" / "app.py").read_text(encoding="utf-8")
    icon = (root / "src" / "flexpes_nexafs" / "icon.py").read_text(encoding="utf-8")
    assert "apply_windows_native_window_icon(win)" in app
    assert "QtCore.QTimer.singleShot(0" in app
    assert "WM_SETICON = 0x0080" in icon
    assert "ICON_BIG = 1" in icon
    assert "ICON_SMALL = 0" in icon
    assert "SendMessageW" in icon
