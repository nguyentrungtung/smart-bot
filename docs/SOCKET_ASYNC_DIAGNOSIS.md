# Socket.IO Asynchronous Flow Diagnosis
**Date**: 2026-04-07  
**Concern**: Voice stream appearing asynchronous, connection closing before response received

---

## 1. Voice Message Flow Timeline

### Frontend (browser):
```
User clicks Mic button
  ↓ (L56 InputArea.jsx)
navigator.mediaDevices.getUserMedia({audio: true})
  ↓ (L60)
new MediaRecorder(stream)
  ↓ (L75)
recorder.start()
  ↓ [User speaks for N seconds]
  ↓
User clicks Stop or auto-stop timeout
  ↓ (L87-90)
recorder.onstop() triggers
  ├─ Collect chunks into array (L61-63)
  ├─ Create Blob from chunks (L65): Blob({chunks}, 'audio/webm')
  ├─ Call onSendMessage('', {audio: blob}) (L70)
  └─ Stop all audio tracks (L72)

[app.jsx handleSendMessage starts]:
  ↓ (L211-218)
Check if attachments.audio instanceof Blob → YES
  ├─ Call blobToBase64(blob) (L213)
  │   └─ Return new Promise with FileReader.readAsDataURL()
  │       └─ **CRITICAL**: This is ASYNC, FileReader may take 100-500ms+ for large blobs
  ├─ payload.audio = audioBase64 (L214)
  └─ Log: "Converted audio Blob to base64, length: XXXXX" (L215)

  ↓ (L263)
socketService.emit("message", payload)
  └─ Send via socket.io
```

**KEY TIMING ISSUE**: `blobToBase64()` is async but there's NO error handling if FileReader fails or times out.

---

### Backend (socket_handler.py):

```
Client emits "message" event
  ↓ (Line 71: handle_message)

STEP 1: VALIDATE (L88-110)
  ├─ Check session_id exists
  └─ Log: "[sid] STEP 1/6 VALIDATE ✓"

STEP 2: EXTRACT (L112-119)
  ├─ Get image, audio, text from payload
  └─ Log: "[sid] STEP 2/6 EXTRACT: text=X, image=Y, audio=Z"

STEP 3: SANITIZE (L121-123)
  ├─ scrub_pii(content)
  └─ Log: "[sid] STEP 3/6 SANITIZE ✓"

STEP 4: PREPARE (L125-145) ← **EXPENSIVE OPERATION**
  ├─ Call MultimodalProcessor.format_message_content()
  │   └─ If audio: Call audio_pipeline.process_audio()
  │       ├─ [1/4] DECODE + VALIDATE: base64 → bytes + format check
  │       ├─ [2/4] CONVERT: FFmpeg pipe async subprocess (60s timeout)
  │       ├─ [3/4] PARSE: numpy conversion
  │       └─ [4/4] TRANSCRIBE: faster-whisper STT (30s timeout per default)
  └─ Log: "[sid] STEP 4/6 PREPARE ✓"

STEP 5: LOCK (L149-167) ← **SERIAL LOCK**
  ├─ Acquire Redis session lock (120s timeout)
  └─ Log: "[sid] STEP 5/6 LOCK ✓"

STEP 6: STREAM (L238-356) ← **CRITICAL SECTION**
  ├─ Invoke LangGraph astream (L252)
  │   ├─ agent node processes message
  │   ├─ Emits message_stream chunks (L108 in app.jsx listener)
  │   └─ When agent responds (no tool calls):
  │       └─ Emit message_complete (L294)
  │       └─ Log: "Emitting message_complete early"
  │       └─ Set _release_lock_early = True
  │       └─ Create _drain_background_nodes task (L311)
  │       └─ Break loops (L313 + L318)
  │
  ├─ If no response sent by fallback (L320-343)
  │   ├─ Fetch final state from graph (L323)
  │   └─ Emit message_complete (L343)
  │
  └─ Finally block (L352-355)
      ├─ Reset context vars
      └─ Exit session_lock context
```

**KEY STREAMING ISSUE**: After emitting `message_complete`, the code breaks from astream loop. But at what point does the socket connection actually close?

---

## 2. Potential Problem Areas

### Problem A: Frontend Blob-to-Base64 Timeout
**Location**: app.jsx L179-186
```javascript
const blobToBase64 = (blob) => {
    return new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onloadend = () => resolve(reader.result);
        reader.onerror = reject;
        reader.readAsDataURL(blob);  // ← No timeout!
    });
};
```

**Issue**: 
- FileReader has NO timeout mechanism
- Large audio blobs (>10MB) may take seconds to convert
- If conversion fails silently, payload.audio remains undefined
- Backend receives incomplete data

**Symptom**: Frontend console shows "Converted audio Blob to base64" but socket never emits

### Problem B: max_http_buffer_size Insufficient
**Location**: socket_handler.py L28
```python
max_http_buffer_size=10000000,  # 10MB
```

**Issue**:
- Base64 encoding increases size by ~33%
- 10MB audio → ~13.3MB base64 string
- Socket.io may silently reject oversized packets
- Connection closes without error message

**Symptom**: "connection closed" logs, but no error event on frontend

### Problem C: Error in Graph Execution
**Location**: socket_handler.py L244-351
```python
try:
    agent_graph = get_agent_graph()
    astream_gen = agent_graph.astream(inputs, config, stream_mode="updates")
    async for chunk in astream_gen:
        # ... processing
except Exception as e:
    logger.error(f"Graph execution error: {str(e)}")
    await sio.emit('error', ..., room=sid)
```

**Issue**:
- If LangGraph node crashes (e.g., FFmpeg error, LLM timeout)
- Exception caught but error event may not reach frontend if connection unstable
- Socket closes after error emit attempt

**Symptom**: Backend logs show error, but frontend sees "connection closed" without error message

### Problem D: Background Node Task Holding Reference
**Location**: socket_handler.py L311
```python
asyncio.create_task(_drain_background_nodes(astream_gen))
_release_lock_early = True
break  # break inner for loop
```

**Issue**:
- `_drain_background_nodes()` is a detached asyncio task
- It holds a reference to `astream_gen` (the async generator)
- Generator may not be garbage-collected immediately
- Could cause memory bloat or connection issues with very long conversations

**Symptom**: Multiple voice messages work, but after 5+ turns, connection becomes unstable

### Problem E: Socket Connection Not Actually Closed
**Location**: varies
```
Logs show "connection closed" but:
  - Does it mean client→server disconnect?
  - Or server→client emit failure?
  - Or just a log message from socket.io internals?
```

**Issue**:
- Need to distinguish between:
  1. Client intentionally calling `socket.disconnect()`
  2. Server closing connection due to error
  3. Network timeout closing connection
  4. Socket.io internally logging transport closure

**Symptom**: Ambiguous logs make it hard to trace root cause

---

## 3. Diagnostic Checklist (What to Check)

### 3.1 Frontend Console (Browser DevTools)

When user clicks "Audio message" button and sends:

```
✅ Should see:
"FE Debug: Requesting microphone access..."
"FE Debug: Recording started"
"FE Debug: Recording complete, blob size: XXXXX"
"FE Debug: Recording stopped"
"FE Debug: Converted audio Blob to base64, length: YYYYY"
"FE Debug: Attaching audio to payload"

❌ If missing "Converted audio Blob to base64":
→ blobToBase64() hung or failed silently
→ payload.audio is undefined
→ Backend receives no audio data

❌ If missing completely:
→ startRecording() didn't execute
→ Check capabilities.audio flag
```

### 3.2 Backend Logs (docker compose logs core_backend)

```
✅ Expected sequence:
"[sid] STEP 1/6 VALIDATE ✓"
"[sid] STEP 2/6 EXTRACT: text=0, image=False, audio=True"
"[sid] STEP 3/6 SANITIZE ✓"
"[sid] STEP 4/6 PREPARE: building multimodal content (STT if audio)..."
"[sid] ├─ [1/4] DECODE: webm format, XXXXX bytes"
"[sid] ├─ [2/4] CONVERT: Y.YYs of 16kHz mono PCM"
"[sid] ├─ [3/4] PARSE: numpy (48000,) dtype=float32"
"[sid] └─ [4/4] TRANSCRIBE: 'transcribed text'"
"[sid] STEP 4/6 PREPARE ✓"
"[sid] STEP 5/6 LOCK ✓ acquired"
"[sid] STEP 6/6 STREAM: starting LangGraph astream..."
"[LANGGRAPH] Node 'agent' finished execution"
"[sid] Emitting message_complete early..."

❌ If stops at STEP 4:
→ STT timeout or FFmpeg error
→ Look for: "CONVERT TIMEOUT", "TRANSCRIBE FAILED", "Unknown format"

❌ If stops at STEP 5:
→ Session lock acquisition failed
→ Another message still processing (429 error)

❌ If doesn't show "message_complete":
→ _release_lock_early logic not triggered
→ Connection closes before message_complete
```

### 3.3 Socket.IO Event Tracing

**Frontend Console** (add extra logging):
```javascript
// Check socket connection state
console.log("Socket connected:", socketService.socket?.connected);

// Check if message_complete event arrives
socketService.on("message_complete", (data) => {
    console.log("[CRITICAL] message_complete RECEIVED", data);
});

// Check if error event arrives instead
socketService.on("error", (data) => {
    console.log("[CRITICAL] error RECEIVED", data);
});

// Check if disconnect event fires during message processing
socketService.socket.on("disconnect", (reason) => {
    console.log("[CRITICAL] socket.disconnect FIRED, reason:", reason);
});
```

### 3.4 Audio Size Check

```bash
# Log the actual size of base64 audio being sent
# Modify app.jsx L215:
const audioBase64 = await blobToBase64(attachments.audio);
const audioMB = (audioBase64.length / (1024 * 1024)).toFixed(2);
console.log("FE Debug: Audio base64 size:", audioMB, "MB");  # ← Add this
if (audioMB > 10) {
    console.warn("WARNING: Audio base64 exceeds 10MB buffer");
}
```

---

## 4. Fix Recommendations (Priority Order)

### FIX 1: Add Timeout to blobToBase64() [IMMEDIATE]
**File**: frontend/widget/src/app.jsx L179-186
**Change**:
```javascript
const blobToBase64 = (blob, timeout = 30000) => {
    return new Promise((resolve, reject) => {
        const reader = new FileReader();
        const timer = setTimeout(() => {
            reader.abort();
            reject(new Error("Base64 conversion timeout after 30s"));
        }, timeout);
        
        reader.onloadend = () => {
            clearTimeout(timer);
            resolve(reader.result);
        };
        reader.onerror = (err) => {
            clearTimeout(timer);
            reject(err);
        };
        reader.readAsDataURL(blob);
    });
};
```

**Why**: Prevents frontend from hanging indefinitely on large blobs. Provides early feedback to user.

### FIX 2: Increase max_http_buffer_size [IMMEDIATE]
**File**: core_backend/app/api/socket_handler.py L28
**Change**:
```python
max_http_buffer_size=50000000,  # 50MB to safely handle 10MB audio base64 + overhead
```

**Why**: Current 10MB is too tight for base64-encoded audio. 50MB provides 5x headroom.

### FIX 3: Add Detailed Socket Connection Logging [IMMEDIATE]
**File**: core_backend/app/api/socket_handler.py
**Add before line 71**:
```python
@sio.event
async def disconnect(sid):
    async with sio.session(sid) as session:
        user_id = session.get("user_id")
    logger.critical(f"[SOCKET CLOSE] Client {sid} disconnected (user_id: {user_id})")

@sio.event
async def connect(sid, environ, auth):
    # ... existing code ...
    # Add after successful connect:
    logger.info(f"[SOCKET OPEN] Client {sid} authenticated, waiting for messages...")
```

**Why**: Trace when connections actually open/close relative to message processing.

### FIX 4: Add Socket Emit Verification [IMMEDIATE]
**File**: core_backend/app/api/socket_handler.py L294
**Change**:
```python
logger.info(f"[{pfx}] About to emit message_complete...")
try:
    await sio.emit('message_complete', {'session_id': session_id}, room=sid)
    logger.info(f"[{pfx}] ✓ message_complete emitted successfully")
except Exception as emit_err:
    logger.error(f"[{pfx}] ✗ FAILED to emit message_complete: {emit_err}")
```

**Why**: Verify that emit succeeded. If it fails, socket.io internally handles connection cleanup.

### FIX 5: Frontend Socket State Tracking [IMMEDIATE]
**File**: frontend/widget/src/app.jsx
**Add after line 79 (in connect handler)**:
```javascript
socketService.socket.on("disconnect", (reason) => {
    console.error("[CRITICAL] Socket DISCONNECTED, reason:", reason);
    setAuthError(true);
    setMessages((prev) => [...prev, {
        sender: 'bot',
        text: `⚠️ Connection lost: ${reason}. Please refresh.`
    }]);
});

socketService.socket.on("connect_error", (err) => {
    console.error("[CRITICAL] Socket CONNECTION ERROR:", err.message);
});
```

**Why**: Gives user explicit feedback when connection closes unexpectedly.

### FIX 6: Audio Size Validation [SECONDARY]
**File**: frontend/widget/src/app.jsx L213-219
**Change**:
```javascript
if (attachments.audio && attachments.audio instanceof Blob) {
    try {
        if (attachments.audio.size > 50 * 1024 * 1024) {  // 50MB check
            throw new Error(`Audio too large: ${(attachments.audio.size / 1024 / 1024).toFixed(1)}MB`);
        }
        const audioBase64 = await blobToBase64(attachments.audio, 60000);  // 60s timeout
        payload.audio = audioBase64;
        const sizeMB = (audioBase64.length / 1024 / 1024).toFixed(2);
        console.log("FE Debug: Audio converted, base64 size:", sizeMB, "MB");
    } catch (err) {
        console.error("FE Error: Audio processing failed:", err);
        setMessages((prev) => [...prev, {
            sender: 'bot',
            text: `❌ Lỗi xử lý âm thanh: ${err.message}`
        }]);
        setLoading(false);
        return;
    }
}
```

**Why**: Validates audio before attempting network transmission. Gives clear error messages.

---

## 5. Testing the Fixes

### Step 1: Rebuild with increased buffer
```bash
# Apply fixes to code
# Rebuild socket_handler with 50MB buffer
docker compose stop core_backend
docker compose up -d --build core_backend
sleep 5
```

### Step 2: Test with browser console monitoring
```
1. Open DevTools (F12)
2. Go to Console tab
3. Click "Audio message"
4. Record for 5 seconds
5. Send

Expected logs:
- "FE Debug: Requesting microphone access..."
- "FE Debug: Recording stopped"
- "FE Debug: Converted audio Blob to base64, length: XXXXX"
- "FE Debug: Audio converted, base64 size: X.XX MB"
- "[CRITICAL] message_complete RECEIVED"

If you see "Socket DISCONNECTED", check reason.
```

### Step 3: Monitor backend logs
```bash
docker compose logs -f core_backend 2>&1 | grep -E 'STEP|SOCKET|message_complete|connection'
```

### Step 4: Verify message arrives at socket handler
Look for sequence:
```
[sid] STEP 1/6 VALIDATE ✓
[sid] STEP 4/6 PREPARE ✓
[sid] STEP 5/6 LOCK ✓
[SOCKET OPEN] Client sid authenticated
[sid] ✓ message_complete emitted successfully
```

---

## 6. Expected Outcome

After applying FIX 1 + FIX 2 + FIX 3:
- ✅ Frontend clearly logs audio conversion completion
- ✅ Backend accepts larger audio payloads
- ✅ Socket emit succeeds and is logged
- ✅ Frontend receives message_complete event
- ✅ No "connection closed" during normal voice message processing

If "connection closed" still appears:
- Check reason in new socket.io disconnect handler
- Most common: "client namespace disconnect" (normal cleanup after message_complete)
- If "server namespace disconnect": indicates error in node execution
- If "transport close": indicates network timeout

---

**Next Action**: Apply FIX 1 + FIX 2 + FIX 3 to code, then test with voice message from browser and monitor logs.
