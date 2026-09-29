from pathlib import Path



def test_icon_assets_are_bundled_as_package_data():
    root = Path(__file__).resolve().parents[1]
    assets = root / "src" / "maxiv_exact" / "assets"
    for name in [
        "exact_icon.ico",
        "exact_icon.icns",
        "exact_icon_64.png",
        "exact_icon_128.png",
        "exact_icon_256.png",
        "exact_icon_512.png",
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
    text = (root / "src" / "maxiv_exact" / "icon.py").read_text(encoding="utf-8")
    assert "def windows_icon_path()" in text
    assert "def macos_icon_path()" in text
    assert "def linux_icon_png_path(" in text



def test_about_dialog_uses_large_application_logo():
    root = Path(__file__).resolve().parents[1]
    core = (root / "src" / "maxiv_exact" / "plotting" / "mixin_core.py").read_text(encoding="utf-8")
    assert "application_icon().pixmap(96, 96)" in core
    assert "box.setIconPixmap(pixmap)" in core


def test_windows_app_user_model_id_is_set_before_qapplication():
    root = Path(__file__).resolve().parents[1]
    text = (root / "src" / "maxiv_exact" / "app.py").read_text(encoding="utf-8")
    assert 'SetCurrentProcessExplicitAppUserModelID' in text
    assert '"MAXIV.EXACT"' in text
    assert text.index("_set_windows_app_user_model_id()") < text.index("QApplication.instance()")


def test_windows_native_taskbar_icon_is_applied():
    root = Path(__file__).resolve().parents[1]
    app = (root / "src" / "maxiv_exact" / "app.py").read_text(encoding="utf-8")
    icon = (root / "src" / "maxiv_exact" / "icon.py").read_text(encoding="utf-8")
    assert "apply_windows_native_window_icon(win)" in app
    assert "QtCore.QTimer.singleShot(0" in app
    assert "WM_SETICON = 0x0080" in icon
    assert "ICON_BIG = 1" in icon
    assert "ICON_SMALL = 0" in icon
    assert "SendMessageW" in icon


def test_about_dialog_text_order_matches_panda_style():
    root = Path(__file__).resolve().parents[1]
    core = (root / "src" / "maxiv_exact" / "plotting" / "mixin_core.py").read_text(encoding="utf-8")
    title = "EXACT: Exploration of X-ray Absorption: Characterization and Treatment"
    version = "Software Version:"
    date = "Date:"
    created = "Created by: Alexei Preobrajenski (MAX IV Laboratory)"
    license_line = "License: MIT"
    assert title in core
    assert version in core
    assert date in core
    assert created in core
    assert license_line in core
    assert core.index(title) < core.index(version) < core.index(date) < core.index(created) < core.index(license_line)



def test_png_icon_uses_transparent_outer_canvas():
    from PIL import Image
    root = Path(__file__).resolve().parents[1]
    img = Image.open(root / "src" / "maxiv_exact" / "assets" / "exact_icon_512.png").convert("RGBA")
    # Outside rounded frame is transparent.
    assert img.getpixel((0, 0))[3] == 0
    # White interior above spectrum remains opaque.
    cx = img.width // 2
    cy = img.height // 5
    r, g, b, a = img.getpixel((cx, cy))
    assert a == 255
    assert min(r, g, b) > 240
