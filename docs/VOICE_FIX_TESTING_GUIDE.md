# Voice Chat Fix Testing Guide

**Date**: 2026-04-07  
**Status**: 6 critical fixes applied  
**Goal**: Verify socket async flow is working correctly

---

## Quick Start: Rebuild & Test

### Step 1: Apply Code Changes
All changes have been made to:
- `frontend/widget/src/app.jsx` - Added blob-to-base64 timeout + error handling + socket state tracking
- `core_backend/app/api/socket_handler.py` - Increased buffer size + detailed logging

### Step 2: Rebuild Backend
```bash
docker compose stop core_backend
docker compose up -d --build core_backend
sleep 5
```

### Step 3: Open Browser DevTools
```
1. Open any page with the Smart-Bot widget
2. Press F12 to open DevTools
3. Click "Console" tab
4. Keep this visible while testing
```

### Step 4: Record & Send Voice Message
```
1. Click Microphone button (red "Stop" appears)
2. Speak clearly for 3-5 seconds
3. Click Stop button
4. ✅ Should see: "FE Debug: Audio converted, base64 size: X.XX MB"
5. Wait for response
6. ✅ Should see: "[CRITICAL] message_complete RECEIVED"
```

---

## What to Expect in Console Logs

### ✅ SUCCESS SCENARIO

**Frontend Console**:
```
FE Debug: Requesting microphone access...
FE Debug: Recording started
FE Debug: Recording complete, blob size: 45678
FE Debug: Recording stopped
FE Debug: Audio converted, base64 size: 0.61 MB (raw was 0.46 MB)
FE Debug: Attaching audio to payload
```

**Backend Logs** (docker compose logs -f core_backend):
```
[sid] STEP 1/6 VALIDATE ✓ session_id=...
[sid] STEP 2/6 EXTRACT: text=0, image=False, audio=True
[sid] STEP 3/6 SANITIZE ✓
[sid] STEP 4/6 PREPARE: building multimodal content...
[sid] ├─ [1/4] DECODE: webm format, 45678 bytes
[sid] ├─ [2/4] CONVERT: 3.45s of 16kHz mono PCM
[sid] ├─ [3/4] PARSE: numpy (55040,) dtype=float32
[sid] └─ [4/4] TRANSCRIBE: 'Xin chào em'
[sid] STEP 4/6 PREPARE ✓ text content ready
[sid] STEP 5/6 LOCK ✓ acquired
[sid] STEP 6/6 STREAM: starting LangGraph astream...
[LANGGRAPH] Node 'agent' finished execution
[sid] About to emit message_complete...
[sid] ✓ message_complete emitted successfully
[SOCKET CLOSE] sid (user_id: user_123)  ← Normal cleanup
```

**Frontend Console** (continued):
```
FE Debug: Received message_stream chunk: Dạ, xin chào...
FE Debug: Received message_stream chunk: Em có thể...
FE Debug: Stream complete. Finalizing message: Dạ, xin chào em...
[CRITICAL] message_complete RECEIVED
```

---

## Troubleshooting: What If Something Goes Wrong?

### ❌ ISSUE 1: "Audio converted" log doesn't appear

**Symptom**:
```
FE Debug: Recording stopped
[MISSING: Audio converted log]
```

**Root Cause**: blobToBase64() timed out or failed
**Fix**: Check console for error message:
```
FE Error: Audio processing failed: Base64 conversion timeout after 60000ms
```

**Solution**:
1. Try shorter audio clip (< 30 seconds)
2. Check if browser is slow (large audio blob on slow machine)
3. Increase timeout in app.jsx L179: `timeout = 90000` (for very large files)

---

### ❌ ISSUE 2: Socket disconnects before message_complete

**Symptoms**:
```
FE Debug: Audio converted, base64 size: 5.5 MB
FE Debug: Attaching audio to payload
[MISSING: message_complete]
[CRITICAL] Socket DISCONNECTED, reason: client namespace disconnect
```

**Backend shows**:
```
[sid] STEP 1/6 VALIDATE ✓
[sid] STEP 4/6 PREPARE ✓
[SOCKET CLOSE] sid (user_id: user_123)
[MISSING: ✓ message_complete emitted]
```

**Root Cause**: Backend crashed or hung before emitting message_complete
**Investigation**:
```bash
# Check for errors in backend logs
docker compose logs -f core_backend 2>&1 | grep -E 'ERROR|FAILED|Exception'
```

**Common errors**:
- `FAILED to emit message_complete` → Socket.io library issue, check buffer size
- `Graph execution error` → LangGraph node crashed (check which node)
- `CONVERT TIMEOUT` → FFmpeg took > 60s (audio too large or system slow)
- `TRANSCRIBE FAILED` → Whisper crashed or ran out of memory

---

### ❌ ISSUE 3: Backend receives audio but STT returns empty

**Symptoms**:
```
[sid] STEP 4/6 PREPARE ✓
[sid] └─ [4/4] TRANSCRIBE: empty result
[sid] STEP 4/6 PREPARE ✗
Guard: Error handler...
```

**Root Cause**: 
- Audio duration too short (< 300ms VAD threshold)
- Audio is silence or just noise
- Language confidence < 0.5 (non-Vietnamese detected)

**Expected for synthetic audio**:
- Test scripts generate synthetic 440Hz sine wave
- Whisper cannot transcribe pure tones
- This is OK for test; use real human speech for validation

**Solution**:
1. For testing: Use test script with pre-recorded Vietnamese audio
2. For real usage: Whisper handles normal speech fine

---

### ❌ ISSUE 4: Audio size warning appears

**Symptoms**:
```
FE Error: Audio processing failed: Audio quá lớn: 52.3MB (max 50MB)
```

**Root Cause**: Audio blob exceeded 50MB raw size (66MB base64)
**Solution**:
1. Use shorter recording (< 2 minutes)
2. If longer needed, increase max in app.jsx L230: `50 * 1024 * 1024` → `100 * 1024 * 1024`
3. Also increase backend buffer in socket_handler.py L28 to match

---

## Advanced Testing: Stress Test Voice Messages

### Test Case A: Quick Fire 3 Messages
```
1. Send voice message 1
2. Wait for message_complete
3. Send voice message 2 (immediately after)
4. Wait for message_complete
5. Send voice message 3

Expected: All 3 succeed without 429 "busy" errors
```

### Test Case B: Long Audio (60 seconds)
```
1. Hold record button for full 60 seconds
2. Speak continuously
3. Send

Expected:
- "CONVERT" step takes ~10-15s (FFmpeg is CPU-bound)
- "TRANSCRIBE" step takes ~5-10s (Whisper processing)
- Total STEP 4: ~20-30s
- Still under 120s lock timeout → Success
```

### Test Case C: Very Large Image Upload
```
1. Upload 5MB image (max allowed)
2. Send with text "Cái ảnh này là gì?"

Expected:
- Should work fine with new 50MB buffer
- Image base64 will be ~6.7MB (33% larger)
- Still under 50MB limit
```

### Test Case D: Mixed Message (Voice + Text)
```
1. Record 5 seconds of audio
2. Also type "Thêm chi tiết về điều này"
3. Send both together

Expected:
- Backend merges both into LangGraph input
- AI responds to both voice + text context
```

---

## Monitoring Backend in Real-Time

### Terminal 1: Tail All Logs
```bash
docker compose logs -f core_backend 2>&1 | grep -v "DEBUG"
```

### Terminal 2: Filter Only Audio Processing
```bash
docker compose logs -f core_backend 2>&1 | grep -E 'STEP|AUDIO|SOCKET|message_complete'
```

### Terminal 3: Filter Only Errors
```bash
docker compose logs -f core_backend 2>&1 | grep -E 'ERROR|FAILED|Exception|✗'
```

---

## Expected Log Markers

These markers indicate successful voice message processing:

| Marker | Meaning | Expected Time |
|--------|---------|------------------|
| `[SOCKET OPEN]` | Client connected | T+0s |
| `STEP 1/6 VALIDATE ✓` | Input validated | T+0s |
| `STEP 4/6 PREPARE ✓` | STT complete | T+10-30s (depends on audio length) |
| `STEP 5/6 LOCK ✓` | Session locked | T+10-30s |
| `✓ message_complete emitted` | Response sent | T+15-40s |
| `[SOCKET CLOSE]` | Cleanup done | T+20-45s |

---

## Success Criteria: Voice Chat is "Fixed"

✅ **PASS** if you can:
1. Record audio voice message in browser
2. See "Audio converted" log in console
3. See backend process audio through all 6 steps
4. Receive message_complete event within 60 seconds
5. See AI response rendered in chat
6. Send multiple voice messages without 429 errors
7. No "connection closed" errors during normal message flow

---

## When "Connection Closed" is Normal

After every message, you may see:
```
[SOCKET CLOSE] sid (user_id: user_123)
```

This is **EXPECTED** and means:
- LangGraph finished processing
- message_complete was emitted
- Backend released session lock
- Background tasks (summarizer, profile_analyzer) are draining
- Socket.io cleaned up that message's resources

This is **NOT** an error — it's normal socket lifecycle cleanup.

---

## When "Connection Closed" is a Problem

**Only report as bug if**:
1. "Connection closed" appears DURING message processing (before message_complete)
2. AND frontend never receives message_complete event
3. AND you see error logs on backend (ERROR, FAILED, Exception)

Example of **BAD** sequence:
```
[sid] STEP 4/6 PREPARE...
[SOCKET CLOSE] sid           ← WRONG: Too early, before PREPARE completes
[ERROR] Graph execution error: ...
```

Example of **GOOD** sequence:
```
[sid] STEP 6/6 STREAM...
[sid] ✓ message_complete emitted
[SOCKET CLOSE] sid           ← CORRECT: After message_complete
```

---

**Next Steps**: 
1. Rebuild with: `docker compose up -d --build core_backend`
2. Test voice message from browser (Console open)
3. Verify you see all expected log markers
4. If any issue, check which marker is missing and refer to Troubleshooting section
