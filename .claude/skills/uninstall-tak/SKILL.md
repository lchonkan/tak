# Uninstall TAK Skill

Use this skill when the user asks to completely uninstall TAK, remove TAK, or clear all TAK data from their system.

## How to Uninstall TAK

Run the provided bash script to completely uninstall TAK and all associated data from the system:

```bash
./uninstall.sh
```

This script mirrors the macOS native uninstaller logic found in the app. It will:
1. Quit the TAK application if it's currently running.
2. Clear the macOS User Defaults (preferences) for `com.tak.app`.
3. Delete the log directory (`~/Library/Logs/TAK`).
4. Reset the macOS permissions (Microphone and Accessibility) for the app bundle ID.
5. Delete the `.app` bundle from `/Applications`, `~/Applications`, and `dist/TAK.app`.

Note: cached MLX Whisper models in `~/.cache/huggingface/hub/` are intentionally preserved so they don't have to be re-downloaded on reinstall.

After running the script, confirm to the user that TAK and all its artifacts have been successfully removed.
