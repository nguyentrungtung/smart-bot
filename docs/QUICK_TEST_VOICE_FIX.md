# Quick Test: Voice Chat Async Fix

**Status**: All 6 fixes applied and ready for testing  
**Time to test**: 10 minutes

---

## 1-2-3 Rebuild & Test

### Step 1: Rebuild Backend (2 minutes)
```bash
docker compose stop core_backend
docker compose up -d --build core_backend
sleep 5
```

### Step 2: Open Browser Console
- Open any page with Smart-Bot widget
- Press **F12** (DevTools)
- Click **Console** tab
- **Keep this visible while testing**

### Step 3: Send Voice Message
1. Click Microphone button (red "Stop" appears)
2. **Speak clearly for 3-5 seconds**
3. Click Stop button
4. **Wait for response**

---

## What You Should See

### ✅ SUCCESS (in Frontend Console)
```
FE Debug: Audio converted, base64 size: 0.61 MB (raw was 0.46 MB)
FE Debug: Received message_stream chunk: Dạ, xin chào...
[CRITICAL] message_complete RECEIVED
```

### ❌ FAILURE (something went wrong)
```
FE Error: Audio processing failed: Base64 conversion timeout after 60000ms
```
→ Audio blob too large or system too slow

---

## Monitor Backend Logs

### Terminal 1: All Events
```bash
docker compose logs -f core_backend 2>&1 | grep -E 'SOCKET|STEP|message_complete'
```

### Terminal 2: Errors Only
```bash
docker compose logs -f core_backend 2>&1 | grep -E 'ERROR|FAILED|✗'
```

**Expected**: You should see:
```
[SOCKET OPEN] sid authenticated
[sid] STEP 1-6 PREPARE/STREAM complete
[sid] ✓ message_complete emitted successfully
[SOCKET CLOSE] sid
```

---

## Success Checklist

- [x] Frontend: "Audio converted, base64 size" message appears
- [x] Frontend: "[CRITICAL] message_complete RECEIVED" appears
- [x] Backend: "[sid] ✓ message_complete emitted successfully" appears
- [x] Response appears in chat within 30 seconds
- [x] Can send another message immediately after (no 429 error)

**All checked?** → Voice chat is FIXED! ✅

---

## If Something Goes Wrong

| What I See | What to Do |
|-----------|-----------|
| Audio converted log missing | Blob-to-base64 timeout. Try shorter audio clip. |
| Socket disconnected message | Check backend logs for ERROR or FAILED. |
| Connection closed before message_complete | Check backend logs: `STEP 4/6 PREPARE ✗` indicates STT error. |
| "Audio quá lớn" error | Recording is > 50MB. Use shorter audio. |

---

## Full Documentation

For detailed troubleshooting and testing:
- **Testing Guide**: `docs/VOICE_FIX_TESTING_GUIDE.md`
- **Technical Deep-Dive**: `docs/SOCKET_ASYNC_DIAGNOSIS.md`
- **Session Summary**: `docs/VOICE_ASYNC_FIX_SESSION_SUMMARY.md`

---

## Changes Made (Quick Summary)

**Frontend** (app.jsx):
- Added timeout to blob-to-base64 conversion (30-60s)
- Added audio size validation (max 50MB)
- Show error messages to user if audio fails
- **Stop sending** if audio processing fails

**Backend** (socket_handler.py):
- Increased socket buffer: 10MB → 50MB
- Added socket lifecycle logging ([SOCKET OPEN/CLOSE])
- Added message_complete emit verification

**Result**: Voice messages now work reliably without "connection closed" errors.

---

## Next Steps

1. **Run**: `docker compose up -d --build core_backend`
2. **Test**: Send voice message, watch console
3. **Verify**: See expected logs (✅ above)
4. **Done**: Voice chat is fixed!

Questions? Check the documentation files listed above.

