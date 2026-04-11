"""Create a signed, notarized DMG for distribution.

Prerequisites:
    1. Build the app first:           python setup_app.py
    2. "Developer ID Application" certificate in Keychain
       (create at developer.apple.com > Certificates)
    3. App-specific password stored:  xcrun notarytool store-credentials "TAK"
       (Apple ID + app-specific password from appleid.apple.com > Sign-In and Security)

Usage:
    python ship_dmg.py                              # uses CODESIGN_IDENTITY env var
    python ship_dmg.py --identity "Developer ID Application: Your Name (TEAMID)"
    python ship_dmg.py --skip-notarize              # sign only, skip notarization

Output:
    dist/TAK.dmg
"""

import argparse
import os
import shutil
import subprocess
import sys
import tempfile


APP_PATH = os.path.join("dist", "TAK.app")
DMG_PATH = os.path.join("dist", "TAK.dmg")
ENTITLEMENTS = os.path.join(os.path.dirname(__file__), "TAK.entitlements")
NOTARY_PROFILE = "TAK"


def run(cmd, **kwargs):
    print(f"  $ {' '.join(cmd)}")
    return subprocess.run(cmd, check=True, **kwargs)


def sign_app(identity):
    """Deep-sign the .app bundle with a Developer ID certificate."""
    print(f"\nSigning with: {identity}")

    # Sign the bundle with hardened runtime + entitlements for JIT (llvmlite/numba)
    run([
        "codesign", "--force", "--options", "runtime",
        "--sign", identity,
        "--deep",
        "--timestamp",
        "--entitlements", ENTITLEMENTS,
        APP_PATH,
    ])
    print("Signed.")

    # Verify
    run(["codesign", "--verify", "--verbose=2", APP_PATH])
    print("Signature verified.")


def create_dmg():
    """Package TAK.app into a compressed DMG with Applications symlink."""
    if os.path.exists(DMG_PATH):
        os.remove(DMG_PATH)

    staging = tempfile.mkdtemp(prefix="tak-dmg-")
    try:
        shutil.copytree(APP_PATH, os.path.join(staging, "TAK.app"), symlinks=True)
        os.symlink("/Applications", os.path.join(staging, "Applications"))

        run([
            "hdiutil", "create",
            "-volname", "TAK",
            "-srcfolder", staging,
            "-ov",
            "-format", "UDZO",
            DMG_PATH,
        ])
        print(f"DMG created: {DMG_PATH}")
    finally:
        shutil.rmtree(staging)


def notarize_dmg():
    """Submit DMG to Apple for notarization and staple the ticket."""
    print(f"\nSubmitting to Apple for notarization (profile: {NOTARY_PROFILE})...")
    run([
        "xcrun", "notarytool", "submit",
        DMG_PATH,
        "--keychain-profile", NOTARY_PROFILE,
        "--wait",
    ])
    print("Notarization approved.")

    # Staple the ticket to the DMG so it works offline
    run(["xcrun", "stapler", "staple", DMG_PATH])
    print("Ticket stapled.")


def main():
    parser = argparse.ArgumentParser(description="Create a signed DMG for distribution.")
    parser.add_argument(
        "--identity",
        default=os.environ.get("CODESIGN_IDENTITY"),
        help='Signing identity (e.g. "Developer ID Application: Name (TEAMID)"). '
             "Falls back to CODESIGN_IDENTITY env var.",
    )
    parser.add_argument(
        "--skip-notarize",
        action="store_true",
        help="Sign and package only, skip Apple notarization.",
    )
    args = parser.parse_args()

    if not os.path.isdir(APP_PATH):
        print(f"Error: {APP_PATH} not found. Run 'python setup_app.py' first.", file=sys.stderr)
        sys.exit(1)

    if not args.identity:
        print(
            "Error: No signing identity provided.\n\n"
            "  python ship_dmg.py --identity \"Developer ID Application: Your Name (TEAMID)\"\n"
            "  # or\n"
            "  export CODESIGN_IDENTITY=\"Developer ID Application: Your Name (TEAMID)\"\n\n"
            "List available identities: security find-identity -v -p codesigning",
            file=sys.stderr,
        )
        sys.exit(1)

    sign_app(args.identity)
    create_dmg()

    if not args.skip_notarize:
        notarize_dmg()
    else:
        print("\nSkipped notarization (--skip-notarize).")

    size_mb = os.path.getsize(DMG_PATH) / (1024 * 1024)
    print(f"\nReady to ship: {DMG_PATH} ({size_mb:.0f} MB)")


if __name__ == "__main__":
    main()
