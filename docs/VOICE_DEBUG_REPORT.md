# Voice Chat Pipeline — 完整诊断报告

**时间**: 2026-04-07  
**现象**: 用户点击"Audio message"按钮，始终收到错误

---

## 📊 问题分析 (3层)

### Layer 1: Frontend (Browser)
✅ **代码正确**:
- `InputArea.jsx` L56-83: MediaRecorder captures audio → Blob
- `InputArea.jsx` L70: sends `onSendMessage('', { audio: blob })`
- `app.jsx` L179-186: `blobToBase64()` 正确转换
- `app.jsx` L210-219: 检查 `instanceof Blob` 并转换为base64
- `app.jsx` L263: `socketService.emit("message", payload)`

**检查点**:
```javascript
// Frontend converts correctly:
const audioBase64 = await blobToBase64(attachments.audio);
payload.audio = audioBase64;  // data:audio/webm;base64,...
console.log("FE Debug: Converted audio Blob to base64, length:", audioBase64.length);
```

⚠️ **可能的错误**: 
- Browser console 里可能有错误信息
- 需要检查 `blobToBase64()` 是否真的被执行
- 需要查看 socket.io 是否真的发送了消息

---

### Layer 2: Backend Socket Handler
✅ **代码正确**:
- `socket_handler.py` L28: `max_http_buffer_size=10000000` (10MB足够)
- Backend 正在接收消息并处理

📊 **从latest logs看**:
```
[cc3aff83] AUDIO └─ [4/4] TRANSCRIBE: empty result
Guard: Bypass triggered for: [Giọng nói của người dùng]: [K...
Guard: Bypass triggered for: [Giọng nói của người dùng]: Mấ...
```

✅ **结论**: Backend 正在成功接收voice消息！

---

### Layer 3: STT Pipeline (Whisper)
⚠️ **发现问题**:

```
[5db45122] AUDIO └─ [4/4] TRANSCRIBE TIMEOUT: STT exceeded 30s
AUDIO: STT failed or returned error: [Lỗi nhận diện giọng nói (quá lâu)]
[cc3aff83] AUDIO └─ [4/4] TRANSCRIBE: empty result
```

**两个问题**:
1. **首次运行**: STT timeout 30秒 (model loading first time)
2. **后续运行**: 返回 "empty result" (synthetic WAV或silence会这样)

---

## 🔍 关键发现

### 问题A: 用户看到错误但backend正在处理
从logs来看:
```
Guard: Bypass triggered for: [Giọng nói của người dùng]: Mấy...
```

说明:
- ✅ Voice message received at backend
- ✅ Audio processing happened
- ✅ STT returned (possibly empty/timeout)
- ✅ Guard triggered and responded

**但用户界面显示错误！**

**根本原因**: 需要检查:
1. Frontend 是否收到 `message_complete` 事件?
2. Frontend 是否收到错误事件?
3. Socket.io 连接是否稳定?

---

## 🧪 测试流程 (用户应该做的)

### Step 1: 打开浏览器 DevTools
```
F12 → Console Tab
```

### Step 2: 观察以下日志
按"Audio message"按钮时，应该看到:

✅ 正常流程:
```
FE Debug: Requesting microphone access...
FE Debug: Recording started
FE Debug: Recording complete, blob size: 12345
FE Debug: Recording stopped
FE Debug: Converted audio Blob to base64, length: 65432  ← KEY LOG!
FE Debug: Attaching audio to payload
```

❌ 如果看不到 "Converted audio Blob to base64", 说明:
- `blobToBase64()` 没有执行
- 或者出现异常但没有显示

### Step 3: 检查错误消息
```
FE Error: Failed to convert audio Blob: ...
```

如果看到这个，说明 `blobToBase64()` 失败了。

### Step 4: 检查 Socket.io 事件
```
// Search console for:
"Converted audio Blob to base64"

// 或查看:
socketService.emit("message", payload)  // Should emit here
```

---

## 🔧 可能的前端修复

### Issue 1: `max_http_buffer_size` 可能太小
虽然设置是 10MB,但这是Socket.io层限制。

**尝试这样改**:

在 `socket_handler.py`:
```python
# Current: 10MB
max_http_buffer_size=10000000,

# Try: 50MB (for large audio base64)
max_http_buffer_size=50000000,
```

原因: Base64编码会把原始大小增加33%
- 10MB audio → ~13.3MB base64
- Socket.io缓冲可能拒绝

### Issue 2: `blobToBase64()` 超时或失败

如果录音很长(> 30秒), FileReader 转换可能超时

**改进**:
```javascript
// app.jsx 中的 blobToBase64
const blobToBase64 = async (blob, timeout = 30000) => {
    return new Promise((resolve, reject) => {
        const reader = new FileReader();
        const timer = setTimeout(() => {
            reader.abort();
            reject(new Error("Base64 conversion timeout"));
        }, timeout);
        
        reader.onloadend = () => {
            clearTimeout(timer);
            resolve(reader.result);
        };
        reader.onerror = () => {
            clearTimeout(timer);
            reject(reader.error);
        };
        reader.readAsDataURL(blob);
    });
};
```

### Issue 3: 检查 `capabilities.audio` 状态

如果 `capabilities.audio === false`, 按钮甚至不会显示。

检查:
```javascript
// InputArea.jsx L12
const hasAudio = capabilities.audio !== false;

// 如果 capabilities 没有正确接收, hasAudio 会是 false
```

---

## 🩺 完整诊断清单

运行以下命令诊断:

### 1. 检查Socket.io连接
```javascript
// 在 browser console 输入:
console.log(window.socketService?.socket?.connected);
// 应该返回: true
```

### 2. 检查 capabilities
```javascript
// In console:
fetch('http://localhost:8000/api/v1/health').then(r => r.json()).then(console.log);
```

### 3. 查看完整后端日志
```bash
docker compose logs core_backend --since=5m 2>&1 | grep -A5 "AUDIO\|Giọng"
```

### 4. 测试with verbose logging

修改 `InputArea.jsx` L58:
```javascript
const startRecording = async () => {
    try {
        console.log("FE VERBOSE: getUserMedia options:", { audio: true });
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        console.log("FE VERBOSE: Stream acquired:", stream);
        const recorder = new MediaRecorder(stream);
        console.log("FE VERBOSE: MediaRecorder created");
        // ... rest of code
```

---

## 📋 症状 → 根本原因 映射

| Frontend看到的现象 | 根本原因 | 解决方案 |
|---|---|---|
| 点击Mic按钮无反应 | Browser拒绝权限 | 检查浏览器权限设置 |
| "Microphone not available" | getUserMedia failed | 检查browser console错误 |
| 按钮灰色无法点击 | capabilities.audio === false | Backend未发送multimodal_config |
| 可以录音但发送后显示错误 | blobToBase64失败或timeout | 增加timeout或检查blob大小 |
| 发送后无反应无错误 | Socket.io连接断开 | 检查socket连接状态 |
| 后端有日志但FE无响应 | message_complete事件未到达 | 检查socket.io事件流 |

---

## 🎯 立即排查步骤

### Step 1: 打开DevTools
```
F12 按Enter
```

### Step 2: 看Console
点"Audio message"按钮，寻找:
```
✅ "FE Debug: Requesting microphone access..."
✅ "FE Debug: Recording started"
✅ "FE Debug: Recording complete, blob size: ..."
✅ "FE Debug: Converted audio Blob to base64, length: ..."
```

### Step 3: 如果没有这些日志
- 说明代码没有执行到该点
- 可能是 `onSendMessage` 没有被触发
- 检查InputArea.jsx L133的按钮onClick

### Step 4: 检查错误
```
FE Error: ...
```

如果有错误，直接显示给我。

---

## 总结: Voice Pipeline 完整流程

```
User clicks "Audio message" 
  ↓
startRecording() (InputArea.jsx L56)
  ├─ navigator.mediaDevices.getUserMedia() (请求Mic权限)
  ├─ new MediaRecorder() (创建录音器)
  ├─ recorder.start() (开始录音)
  └─ recorder.onstop = () => { ... } (设置完成处理)
  ↓
User speaks 
  ↓
User clicks "Stop" or auto-stop
  ↓
recorder.onstop() 触发
  ├─ new Blob(chunks, 'audio/webm') (创建音频Blob)
  └─ onSendMessage('', { audio: blob }) (发送给app.jsx)
  ↓
app.jsx handleSendMessage() (L188)
  ├─ blobToBase64(blob) (转换为 data:audio/webm;base64,...)
  ├─ payload.audio = audioBase64 (加到payload)
  └─ socketService.emit("message", payload) (发送到backend)
  ↓
Backend socket_handler.py
  ├─ validate & extract audio from payload
  ├─ MultimodalProcessor.speech_to_text()
  │   └─ audio_pipeline.process_audio() (4步: DECODE, CONVERT, PARSE, TRANSCRIBE)
  ├─ Inject: "[Giọng nói của người dùng]: {transcription}"
  └─ LangGraph workflow → AI response → stream chunks
  ↓
Frontend receives
  ├─ message_stream events (chunks)
  ├─ message_complete event
  └─ Display response to user
```

---

**Next Action**: 
1. 打开DevTools Console
2. 点击"Audio message"
3. 记下所有console.log输出
4. 告诉我:
   - 是否看到 "Requesting microphone access..."
   - 是否看到 "Converted audio Blob to base64"
   - 是否有任何 "FE Error" 消息

