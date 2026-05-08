---
name: run-tak
description: Build (if needed), launch, and monitor TAK.app. Use when the user asks to run, launch, start, or test TAK. Tails ~/Library/Logs/TAK/tak.log until the app is stable ("TAK ready"), the app crashes, or the user returns.
---

# Run TAK Skill

Use this skill when the user asks to run, launch, start, or test the TAK macOS app.

## Procedure

1. **Build if missing.** If `dist/TAK.app` does not exist, build it first:
   ```bash
   source /opt/anaconda3/etc/profile.d/conda.sh && conda activate tak && python setup_app.py
   ```
   Use a long timeout (~10 min). If the build fails, stop and report the error — do not attempt to launch.

2. **Reset the log and launch.** Truncate the log so previous runs don't confuse diagnosis, then open the app:
   ```bash
   rm -f ~/Library/Logs/TAK/tak.log
   open dist/TAK.app
   ```

3. **Monitor until terminal state.** Tail `~/Library/Logs/TAK/tak.log` and watch the process. Stop when one of these happens:
   - **Stable**: log contains `TAK ready` (and the process is still alive). Report success and any non-fatal warnings.
   - **Crashed**: log contains `TAK crashed:` or the process exited before `TAK ready`. Report the full traceback and propose a fix.
   - **User returns**: if the user sends a new message, stop monitoring.

   Poll with short sleeps (e.g. `sleep 5 && tail -n 80 ~/Library/Logs/TAK/tak.log; pgrep -lf TAK.app`). Don't busy-loop — give the app time to download models on first run (the turbo model is ~1.5 GB).

4. **Report.** Summarize the outcome in 1–3 sentences. If the app crashed, quote the traceback's last frame and the exception line. If stable, mention the trigger key and model from the `TAK ready` line.

## Notes

- The log path is `~/Library/Logs/TAK/tak.log`. The `.app` bundle redirects stdout/stderr there.
- Accessibility-permission warnings are expected after a fresh install or uninstall — they are not crashes. The app continues running and polls for the permission.
- Common crash causes (check `TAK.spec` if these reappear): missing hidden imports under `mlx.*`, missing `mlx_whisper/assets/` data files.
