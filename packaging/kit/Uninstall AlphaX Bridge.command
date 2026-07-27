#!/bin/bash
PLIST="$HOME/Library/LaunchAgents/ai.neotec.alphax-bridge.plist"
launchctl unload "$PLIST" 2>/dev/null || true
rm -f "$PLIST"
rm -rf "$HOME/Library/Application Support/AlphaXBridge"
echo "AlphaX POS Bridge removed."
