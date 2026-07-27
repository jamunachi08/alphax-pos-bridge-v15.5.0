# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec for AlphaX POS Bridge.

Produces a single windowed executable that runs the tray app on
launch. Works on Windows, macOS, and Linux with the same spec.

Usage:
    pyinstaller packaging/pyinstaller/alphax-bridge.spec --clean --noconfirm

Outputs:
    dist/alphax-bridge/                 (Windows / Linux: a folder)
    dist/AlphaX POS Bridge.app/         (macOS: a .app bundle)

Build prereqs (per-OS):
    pip install pyinstaller pystray Pillow pyyaml pyserial pyusb
    Windows:   nothing else
    macOS:     no extra; Tk shipped with python.org Python builds
    Linux:     apt install python3-tk libusb-1.0-0
"""
import os
import sys
from pathlib import Path

# Resolve project root (the alphax-pos-bridge directory)
HERE = os.path.abspath(os.path.dirname(SPEC))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
PROFILES_DIR = os.path.join(ROOT, "profiles")

block_cipher = None

a = Analysis(
    [os.path.join(ROOT, "alphax_bridge", "tray.py")],
    pathex=[ROOT],
    binaries=[],
    datas=[
        # Bundle the device profile JSONs so they're available at runtime.
        (PROFILES_DIR, "profiles"),
        # Bundle docs so users can read them from the install dir.
        (os.path.join(ROOT, "README.md"), "."),
        (os.path.join(ROOT, "docs"), "docs"),
    ],
    hiddenimports=[
        # Pull in everything the tray + bridge actually use.
        # PyInstaller's static analysis misses dynamic imports we
        # do via the registry's profile loader.
        "alphax_bridge",
        "alphax_bridge.devices",
        "alphax_bridge.protocols",
        "alphax_bridge.registry",
        "alphax_bridge.renderer",
        "alphax_bridge.server",
        "alphax_bridge.terminals",
        "alphax_bridge.terminals_helpers",
        "alphax_bridge.transports",
        "alphax_bridge.tray",
        "alphax_bridge.wizard",
        # GUI deps for tray + wizard
        "pystray",
        "PIL",
        "PIL.Image",
        "PIL.ImageDraw",
        "tkinter",
        "tkinter.font",
        "tkinter.messagebox",
        "tkinter.scrolledtext",
        # Optional hardware libs — included so the .exe works without
        # the user having to pip-install anything.
        "yaml",
        "serial",
        "serial.tools.list_ports",
        "usb",
        "usb.core",
        "usb.util",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Skip heavy stdlib modules we don't need.
        "test", "unittest",
        "distutils", "setuptools", "pip",
        "_pytest", "pytest",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)


# Resolve icon per platform.
ICON = None
if sys.platform == "win32":
    ico = os.path.join(HERE, "..", "assets", "alphax-bridge.ico")
    if os.path.exists(ico): ICON = ico
elif sys.platform == "darwin":
    icns = os.path.join(HERE, "..", "assets", "alphax-bridge.icns")
    if os.path.exists(icns): ICON = icns
else:
    png = os.path.join(HERE, "..", "assets", "alphax-bridge.png")
    if os.path.exists(png): ICON = png


exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="alphax-bridge",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,           # windowed app, no console
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=ICON,
)


coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="alphax-bridge",
)


# macOS .app bundle
if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name="AlphaX POS Bridge.app",
        icon=ICON,
        bundle_identifier="com.alphax.pos.bridge",
        info_plist={
            "CFBundleShortVersionString": "15.5.1",
            "CFBundleVersion": "15.5.1",
            "NSHighResolutionCapable": "True",
            "LSUIElement": "True",                # background-only app (tray)
            "LSMinimumSystemVersion": "10.15",
        },
    )
