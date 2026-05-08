#!/usr/bin/env bash

# TAK Uninstaller Script
# This script completely uninstalls TAK and its associated data, mimicking the native macOS uninstaller.

echo "Uninstalling TAK..."

BUNDLE_ID="com.tak.app"

# 1. Quit the app if running
echo "Stopping TAK..."
pkill -f "TAK.app/Contents/MacOS/TAK" 2>/dev/null || true

# 2. Clear NSUserDefaults
echo "Clearing preferences..."
defaults delete "$BUNDLE_ID" 2>/dev/null || true

# 3. Remove log directory
echo "Removing logs..."
rm -rf "$HOME/Library/Logs/TAK"

# 4. Reset macOS permissions
echo "Resetting permissions..."
tccutil reset Microphone "$BUNDLE_ID" 2>/dev/null || true
tccutil reset Accessibility "$BUNDLE_ID" 2>/dev/null || true

# 5. Remove the application bundle
echo "Removing TAK.app..."
rm -rf "/Applications/TAK.app"
rm -rf "$HOME/Applications/TAK.app"
if [ -d "dist/TAK.app" ]; then
    rm -rf "dist/TAK.app"
fi

echo "TAK has been completely uninstalled."
