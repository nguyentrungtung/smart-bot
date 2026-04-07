#!/bin/bash
# Test Voice Chat Async Fix
# Usage: bash scripts/test_voice_async_fix.sh

set -e

echo "═══════════════════════════════════════════════════════════════"
echo "  VOICE CHAT ASYNC FIX — REBUILD & TESTING"
echo "═══════════════════════════════════════════════════════════════"
echo ""

echo "Step 1: Stopping backend container..."
docker compose stop core_backend
sleep 2

echo "Step 2: Rebuilding backend with fixes..."
docker compose up -d --build core_backend
sleep 8

echo "Step 3: Checking backend health..."
docker compose logs core_backend --tail 20 | grep -E "SOCKET|STT|faster-whisper" || echo "Backend starting..."

echo ""
echo "═══════════════════════════════════════════════════════════════"
echo "  READY TO TEST!"
echo "═══════════════════════════════════════════════════════════════"
echo ""
echo "Next steps:"
echo "1. Open browser with Smart-Bot widget"
echo "2. Press F12 to open DevTools → Console tab"
echo "3. Click Microphone button and record 3-5 seconds"
echo "4. Click Send"
echo ""
echo "Expected in Frontend Console:"
echo "  ✅ 'FE Debug: Audio converted, base64 size: X.XX MB'"
echo "  ✅ '[CRITICAL] message_complete RECEIVED'"
echo ""
echo "Monitor Backend Logs:"
echo "  $ docker compose logs -f core_backend 2>&1 | grep -E 'STEP|SOCKET|message_complete|✓|✗'"
echo ""
echo "Full Test Procedure:"
echo "  $ cat docs/VOICE_FIX_TESTING_GUIDE.md"
echo ""
echo "Analysis Documents:"
echo "  - docs/SOCKET_ASYNC_DIAGNOSIS.md (technical deep-dive)"
echo "  - docs/VOICE_FIX_TESTING_GUIDE.md (user testing guide)"
echo "  - docs/VOICE_ASYNC_FIX_SESSION_SUMMARY.md (this session summary)"
echo ""
