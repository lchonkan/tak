"""PyInstaller build script for TAK.app.

Build:
    conda activate tak
    pip install pyinstaller
    python setup_app.py

Output:
    dist/TAK.app
"""

import os
import subprocess
import sys

# Locate mlx native libraries
SITE_PACKAGES = os.path.join(
    os.path.dirname(sys.executable), "..", "lib",
    f"python{sys.version_info.major}.{sys.version_info.minor}", "site-packages",
)
SITE_PACKAGES = os.path.normpath(SITE_PACKAGES)

MLX_LIB = os.path.join(SITE_PACKAGES, "mlx", "lib")
SOUNDDEVICE_DATA = os.path.join(SITE_PACKAGES, "_sounddevice_data")

cmd = [
    sys.executable, "-m", "PyInstaller",
    "--name", "TAK",
    "--windowed",                     # .app bundle, no console
    "--icon", "resources/tak.icns",
    "--osx-bundle-identifier", "com.tak.app",

    # ── Collect packages ─────────────────────────────────────────
    "--collect-all", "mlx",
    "--collect-all", "mlx_whisper",
    "--collect-all", "pynput",

    # ── Hidden imports ───────────────────────────────────────────
    "--hidden-import", "AppKit",
    "--hidden-import", "Foundation",
    "--hidden-import", "objc",
    "--hidden-import", "sounddevice",
    "--hidden-import", "numpy",

    # ── Native libraries ─────────────────────────────────────────
    "--add-binary", f"{MLX_LIB}/libmlx.dylib:mlx/lib",
    "--add-data", f"{MLX_LIB}/mlx.metallib:mlx/lib",

    # ── Excludes (save ~500MB) ───────────────────────────────────
    "--exclude-module", "torch",
    "--exclude-module", "torchaudio",
    "--exclude-module", "torchvision",
    "--exclude-module", "faster_whisper",
    "--exclude-module", "ctranslate2",
    "--exclude-module", "onnxruntime",
    "--exclude-module", "PIL",
    "--exclude-module", "tkinter",

    # ── Entry point ──────────────────────────────────────────────
    "tak/gui_main.py",
]

# Add sounddevice portaudio if present
if os.path.isdir(SOUNDDEVICE_DATA):
    cmd.insert(-1, "--add-data")
    cmd.insert(-1, f"{SOUNDDEVICE_DATA}:_sounddevice_data")

# Add Info.plist overrides via environment
os.environ["PYINSTALLER_PLIST_EXTRA"] = ""  # handled post-build

print("Building TAK.app with PyInstaller...")
print(f"  Site-packages: {SITE_PACKAGES}")
print(f"  MLX lib: {MLX_LIB}")
result = subprocess.run(cmd)

if result.returncode == 0:
    # Post-build: patch Info.plist with required macOS keys
    import plistlib

    plist_path = os.path.join("dist", "TAK.app", "Contents", "Info.plist")
    if os.path.exists(plist_path):
        with open(plist_path, "rb") as f:
            plist = plistlib.load(f)

        plist.update({
            "CFBundleDisplayName": "TAK \u2014 Talk to Keyboard",
            "LSMinimumSystemVersion": "13.0",
            "LSUIElement": True,
            "NSMicrophoneUsageDescription": (
                "TAK needs microphone access to record speech for transcription."
            ),
            "NSAppleEventsUsageDescription": (
                "TAK uses System Events to type transcribed text "
                "into the active window."
            ),
        })

        with open(plist_path, "wb") as f:
            plistlib.dump(plist, f)

        print("\nInfo.plist patched with macOS permission keys.")

    # Ad-hoc code sign so macOS shows permission prompts (microphone, etc.)
    app_path = os.path.join("dist", "TAK.app")
    subprocess.run(
        ["codesign", "--force", "--deep", "--sign", "-", app_path],
        check=True,
    )
    print("Ad-hoc code signed.")

    print(f"\nDone! App bundle at: dist/TAK.app")
else:
    print(f"\nBuild failed with exit code {result.returncode}", file=sys.stderr)

sys.exit(result.returncode)
