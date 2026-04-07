# Smart-Bot MVP: AI Sales Assistant

Smart-Bot là một giải pháp Chatbot Agentic hiện đại được xây dựng trên LangGraph, cung cấp khả năng hội thoại thông minh với RAG (Retrieval-Augmented Generation), Tool Calling tự động, và hỗ trợ đa phương tiện (Voice/Vision).

## 🚀 Tính năng nổi bật

- **Agentic Reasoning**: Sử dụng LangGraph để lập luận và quyết định hướng xử lý (RAG, Tools, hoặc Fallback).
- **RAG (pgvector)**: Tìm kiếm tri thức thời gian thực từ Database PostgreSQL với độ chính xác cao.
- **Autonomous Tools**: Tự động gọi các công cụ hỗ trợ (Thời tiết, Tra cứu giờ, Khởi tạo Xweb).
- **Hallucination Block**: Cơ chế bảo vệ Scenario B - Chỉ trả lời khi có dữ liệu tin cậy, nếu không sẽ chuyển sang thông báo hỗ trợ.
- **Multimodal — Voice & Vision**: 
  - **Voice Chat**: Server-side STT (faster-whisper) converts audio (webm/ogg/mp4) to Vietnamese text automatically
  - **Vision**: Image analysis via Gemini 2.5-flash (base64 encoding)
- **Security**: Xác thực JWT RS256, Scrubbing PII (ẩn thông tin nhạy cảm), và Session Locking bằng Redis.

---

## 🛠️ Yêu cầu hệ thống

- Docker & Docker Compose
- Python 3.11+ (cho development cục bộ)
- Node.js 18+ (cho frontend development)
- Gemini không còn tồn tại tên model gemini-1.5-flash. hiện tại nếu bắt đầu thì đã thay đổi lên gemini-2.5-flash .Tuyệt đối không được phép chuyển về 1.5 dưới bất kỳ hình thức nào. không tồn tại nữa
---

## 🏗️ Hướng dẫn khởi chạy (Full Stack với Docker)

Đây là cách nhanh nhất để chạy toàn bộ hệ thống bao gồm Backend, Database, Redis và LiteLLM Proxy.

> **Kiến trúc Database**: Hệ thống dùng **hai** PostgreSQL độc lập để tránh xung đột schema:
> - `postgres` (port **5432**) — dành riêng cho `core_backend` / LangGraph / Alembic.
> - `postgres_litellm` (port **5433**) — dành riêng cho `litellm_proxy`. Tự khởi tạo schema khi startup, không liên quan đến Alembic.

1. **Chuẩn bị môi trường**:
   ```bash
   cp .env.example .env
   # Cập nhật các API Key cần thiết (OPENAI_API_KEY, GEMINI_API_KEY, ...) trong .env
   # Các biến LITELLM_DB_* đã có giá trị mặc định, không bắt buộc thay đổi
   ```

2. **Khởi tạo cặp khóa bảo mật (JWT)**:
   ```bash
   python scripts/generate_jwt_keys.py
   ```

3. **Chạy hệ thống (Khởi động tất cả Service)**:
   Do dự án phân chia các service theo `profiles` (`backend`, `tools`), lệnh `docker compose up -d` mặc định sẽ báo lỗi "no service selected".
   Để chạy toàn bộ hệ thống, bạn cần chỉ định các profile muốn khởi động:

   ```bash
   # Chạy toàn bộ hệ thống (bao gồm Database, Redis, Proxy, Backend và MCP Tools)
   docker compose --profile backend --profile tools up -d
   
   # Nếu muốn build lại image thay vì dùng image cũ, thêm cờ --build
   docker compose --profile backend --profile tools up -d --build

   # Để xem logs của hệ thống đang chạy
   docker compose --profile backend --profile tools logs -f
   ```

   Thứ tự khởi động được Docker Compose đảm bảo tự động (qua `healthcheck`):
   `postgres` & `postgres_litellm` → `redis` → `litellm_proxy` → `core_backend`

4. **Áp dụng Database Migration (chỉ cho core_backend)**:
   Migration Alembic chỉ chạy trên `postgres` (port 5432). `postgres_litellm` được LiteLLM tự quản lý, **không cần** và **không được** chạy Alembic vào đó.
   ```bash
   docker compose exec core_backend alembic upgrade head
   ```

5. **Seed dữ liệu mẫu (RAG & Admin)**:
   ```bash
   docker compose exec core_backend python scripts/seed_db.py
   ```

6. **Reset & Rebuild từ đầu (Clean Start)**:
   Nếu bạn muốn xóa toàn bộ dữ liệu (bao gồm cả hai Database volumes) và build lại:
   ```bash
   # Dừng và xóa toàn bộ volume (pgdata + pgdata_litellm)
   docker compose --profile backend --profile tools down -v
   
   # Build và chạy lại
   docker compose --profile backend --profile tools up -d --build
   
   # Áp dụng lại migration cho core_backend (bắt buộc sau khi xóa volume)
   docker compose exec core_backend alembic upgrade head
   ```

---

## 🎤 Voice Chat & Audio Pipeline

Smart-Bot hỗ trợ chat bằng **giọng nói tiếng Việt** với xử lý âm thanh phía máy chủ (Server-Side STT).

### Kiến trúc Audio Pipeline (STT — Community Standard)

```
Browser mic (webm/ogg/mp4) 
  → base64 encode 
  → Socket.IO 
  → [DECODE] base64 → bytes
  → [CONVERT] FFmpeg pipe: any format → 16kHz mono PCM s16le
  → [PARSE] numpy: bytes → float32 array
  → [TRANSCRIBE] faster-whisper Vietnamese STT
  → [Giọng nói của người dùng]: {transcription} 
  → LLM (model-agnostic: LM Studio, Gemini, OpenAI)
```

**Tại sao STT-First?**
- **Model-agnostic**: Hoạt động với mọi LLM backend (LM Studio, Gemini, OpenAI)
- **Auditable**: Transcription có thể ghi log, kiểm tra, và debug
- **No format lock-in**: Tránh sự không tương thích của `input_audio` giữa OpenAI Realtime, Gemini Live, và local models
- **Dễ fallback**: Nếu STT thất bại, hệ thống trả lại thông báo thân thiện (ví dụ: "[Không nghe rõ, vui lòng nhắc lại]") thay vì treo ứng dụng

### Kiểm tra Voice Pipeline

**Test E2E 7-Turn Voice Chat** (4 voice turns + 3 text turns, all Vietnamese):

```bash
docker compose exec core_backend python scripts/test_voice_chat.py
```

**Kết quả mong đợi**: ✅ 7/7 PASS

Kiểm tra các thành phần:
- **T1 (VOICE)**: Synthetic audio → AI asks to repeat if STT fails (VAD filter rejects non-speech)
- **T2 (TEXT)**: AI identity → SmartSales Assistant profile
- **T3 (VOICE+TEXT)**: Time query with tool call
- **T4 (VOICE+TEXT)**: Weather query for Hà Nội
- **T5 (TEXT)**: Profile seeding (name=Minh)
- **T6 (VOICE+TEXT)**: RAG search about Smart Bot features
- **T7 (TEXT)**: Memory recall ("Bạn có nhớ tên tôi không?") → AI recalls "Minh"

**Xem logs audio pipeline**:

```bash
docker compose logs core_backend 2>&1 | grep -E 'AUDIO|DECODE|CONVERT|PARSE|TRANSCRIBE|STT'
```

### Audio Requirements

- **Browser**: Chrome, Edge, Firefox (WebRTC audio capture)
- **Server**: FFmpeg binary (via `apt-get install ffmpeg` or similar)
- **Python**: faster-whisper package (included in `requirements.txt`)
- **Model**: faster-whisper small model (~500MB, auto-downloaded from HuggingFace on first use)

### Known Limitations

- **First audio message**: Takes ~10s to process (model loading). Subsequent messages: ~5s each (local LM Studio CPU).
- **Synthetic audio**: Sine waves at 440Hz will NOT transcribe (language confidence < 0.5). This is CORRECT — the filter rejects non-speech. For real testing, use actual Vietnamese voice recordings.
- **LM Studio quirks**: Local models sometimes output raw tool tokens like `<|tool_call>call:get_current_time{}<|tool_call|>`. These are now stripped before sending to client.
- **Session timeout**: 120s lock per message (prevents concurrent processing). Set longer timeouts if using very slow local models.

---

## 💻 Frontend (Widget UI)

Widget được xây dựng bằng **Preact** và **Vite**, thiết kế theo phong cách Glassmorphism cao cấp.

1. **Cài đặt**:
   ```bash
   cd frontend/widget
   npm install
   ```

2. **Chạy Development Mode**:
   ```bash
   npm run dev
   ```

3. **Sử dụng**:
   - Mở `frontend/test.html` trong trình duyệt để xem cách widget được nhúng vào website thật.
   - Iframe sẽ tự động co giãn và nhận JWT Token từ trang cha qua `postMessage`.

---

## 🗄️ Quản lý Database & Migration

Hệ thống dùng **hai** PostgreSQL độc lập, mỗi instance quản lý schema riêng:

| Instance | Port host | Quản lý bởi | Nội dung |
|---|---|---|---|
| `postgres` | **5432** | Alembic + LangGraph | UserProfile, ChatInteraction, SessionMetadata, Checkpoints |
| `postgres_litellm` | **5433** | LiteLLM tự động | LiteLLM internal tables |

> Việc tách biệt này loại bỏ hoàn toàn xung đột schema khi `docker compose down/up`: LiteLLM không còn ghi vào cùng database với core_backend nữa.

### Cách chạy Migration (Alembic — chỉ cho `postgres`:5432)
Nếu bạn thay đổi database model trong `app/memory/` hoặc `app/schemas/`, hãy chạy lệnh sau để cập nhật schema:

```bash
# 1. Tạo file migration mới (với cơ chế tự động phát hiện thay đổi)
docker compose exec core_backend alembic revision --autogenerate -m "Mô tả thay đổi"

# 2. Áp dụng migration vào database hiện tại
docker compose exec core_backend alembic upgrade head

# 3. Khởi tạo thủ công bảng Memory (LangGraph Checkpoints) nếu chưa thấy xuất hiện
docker compose exec core_backend python scripts/setup_checkpointer.py
```

*Lưu ý: Alembic chỉ connect đến `postgres:5432` (qua `DATABASE_URL` trong env). Không cần và không được chạy migration vào `postgres_litellm`.*

---

## ⚙️ Backend & API

Backend sử dụng **FastAPI** và kết nối qua **Socket.IO** để hỗ trợ streaming streaming và trạng thái "AI đang suy nghĩ" (Thinking).

- **Health Check**: `GET http://localhost:8000/health`

### Tài liệu API (Interactive Docs)
Khi backend đang chạy, bạn có thể truy suất tài liệu API đầy đủ và thử nghiệm trực tiếp tại:
- **Swagger UI**: [http://localhost:8000/docs](http://localhost:8000/docs)
- **ReDoc**: [http://localhost:8000/redoc](http://localhost:8000/redoc)

### Ví dụ CURL (API Testing)

**1. Đăng nhập (Lấy Token):**
```bash
curl -X POST http://localhost:8000/api/v1/auth/login \
     -H "Content-Type: application/json" \
     -d '{"user_id": "admin", "password": "admin123"}'
```

**2. Trao đổi Token Partner (Partner Exchange):**
*Lưu ý: Partner cần được cung cấp Token quản trị trước để gọi API này.*
```bash
curl -X POST http://localhost:8000/api/v1/auth/exchange-token \
     -H "Content-Type: application/json" \
     -H "Authorization: Bearer <PARTNER_TOKEN>" \
     -d '{"visitor_id": "cust_99", "metadata": {"source": "website-vệ-tinh"}}'
```

**3. Làm mới Access Token (Refresh Token):**
```bash
curl -X POST http://localhost:8000/api/v1/auth/refresh \
     -H "Content-Type: application/json" \
     -d '{"refresh_token": "<YOUR_REFRESH_TOKEN>"}'
```

**4. Thu hồi Token / Đăng xuất (Revoke Token):**
```bash
curl -X POST http://localhost:8000/api/v1/auth/logout \
     -H "Authorization: Bearer <ACCESS_TOKEN>"
```

**5. Khởi tạo Session mới:**
```bash
curl -X POST http://localhost:8000/api/v1/chat/new-session \
     -H "Authorization: Bearer <ACCESS_TOKEN>" \
     -H "Content-Type: application/json" \
     -d '{}'
```

- **Socket.IO Endpoint**: `ws://localhost:8000/socket.io/`

### Kiểm tra tính năng (API/Logic)
Sử dụng script simulation để kiểm tra luồng Agent và Multimodal:
```bash
# Test luồng chat cơ bản
docker-compose exec core_backend python scripts/test_e2e_socket_flow.py

# Test Multimodal (Vision & Voice)
docker-compose exec core_backend python scripts/test_multimodal_vision_voice.py

# Test Bypass Logic (Scenario B)
docker-compose exec core_backend python scripts/test_bypass_logic.py
```

---

### Quản trị & Dọn dẹp bộ nhớ (Maintenance)
Sử dụng script `clear_memory.py` để dọn dẹp database khi cần thiết hoặc để phục vụ việc kiểm thử (test memory):
```bash
# Xóa Short-term memory (Xóa lịch sử chat trong LangGraph)
docker-compose exec core_backend python scripts/clear_memory.py --short-term

# Xóa Long-term memory (Xóa hồ sơ/sở thích khách hàng)
docker-compose exec core_backend python scripts/clear_memory.py --long-term

# Xóa Analytics & Session (Xóa metadata và chat interactions)
docker-compose exec core_backend python scripts/clear_memory.py --analytics

# Xóa SẠCH TOÀN BỘ ký ức (Short + Long + Analytics)
docker-compose exec core_backend python scripts/clear_memory.py --all
```

---

## 🛡️ Security & Auth
 
 Dự án sử dụng cặp khóa RSA để ký và xác thực JWT.

### Xác thực người dùng
- **Cơ chế**: Bắt buộc đăng nhập bằng `user_id` và `password`. Không cho phép Guest Login tự do.
 - **Status Dot**: Widget có chấm xanh (Đã xác thực) và chấm đỏ (Lỗi xác thực/Hết hạn).
- **Tài khoản dùng thử** (Sau khi chạy `seed_db.py`):
  - **Admin**: `admin` / `admin123`
  - **User**: `user68` / `user123`
- **Tích hợp Website vệ tinh**: Sử dụng `postMessage` với type `SMART_BOT_AUTH` để truyền Token từ trang cha vào Iframe.

### Key Management
- **Private Key**: Dùng để tạo token.
- **Public Key**: `/app/.keys/public_key.pem` (Backend dùng để xác minh).

---

## 📂 Cấu trúc thư mục chính

- `core_backend/`: FastAPI App, LangGraph nodes, Middleware.
- `frontend/widget/`: Mã nguồn Preact Widget.
- `mcp_servers/`: Các server công cụ (Model Context Protocol).
- `scripts/`: Script quản trị (Seed DB, Key Gen, E2E Test).
- `docs/`: Technical Design và tài liệu nghiên cứu.
