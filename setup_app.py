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

SPEC_FILE = os.path.join(os.path.dirname(__file__), "TAK.spec")

cmd = [
    sys.executable, "-m", "PyInstaller",
    "--noconfirm",
    SPEC_FILE,
]

print("Building TAK.app with PyInstaller (TAK.spec)...")
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
    print("To create a signed DMG for distribution: python ship_dmg.py")
else:
    print(f"\nBuild failed with exit code {result.returncode}", file=sys.stderr)

sys.exit(result.returncode)
