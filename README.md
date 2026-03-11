# Smart-Bot MVP: AI Sales Assistant

Smart-Bot là một giải pháp Chatbot Agentic hiện đại được xây dựng trên LangGraph, cung cấp khả năng hội thoại thông minh với RAG (Retrieval-Augmented Generation), Tool Calling tự động, và hỗ trợ đa phương tiện (Voice/Vision).

## 🚀 Tính năng nổi bật

- **Agentic Reasoning**: Sử dụng LangGraph để lập luận và quyết định hướng xử lý (RAG, Tools, hoặc Fallback).
- **RAG (pgvector)**: Tìm kiếm tri thức thời gian thực từ Database PostgreSQL với độ chính xác cao.
- **Autonomous Tools**: Tự động gọi các công cụ hỗ trợ (Thời tiết, Tra cứu giờ, Khởi tạo Xweb).
- **Hallucination Block**: Cơ chế bảo vệ Scenario B - Chỉ trả lời khi có dữ liệu tin cậy, nếu không sẽ chuyển sang thông báo hỗ trợ.
- **Multimodal**: Hỗ trợ gửi ảnh và giọng nói trực tiếp từ Widget.
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

1. **Chuẩn bị môi trường**:
   ```bash
   cp .env.example .env
   # Cập nhật các API Key cần thiết (OPENAI_API_KEY, LITELLM_API_KEY) trong .env
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

4. **Seed dữ liệu mẫu (RAG)**:
   ```bash
   docker-compose exec core_backend python scripts/seed_db.py
   ```

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

## ⚙️ Backend & API

Backend sử dụng **FastAPI** và kết nối qua **Socket.IO** để hỗ trợ streaming streaming và trạng thái "AI đang suy nghĩ" (Thinking).

- **Health Check**: `GET http://localhost:8000/health`
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

## 🛡️ Security & Auth

Dự án sử dụng cặp khóa RSA để ký và xác thực JWT.
- **Private Key**: Dùng để tạo token (thường ở phía Web App của bạn).
- **Public Key**: `/app/.keys/public_key.pem` (Backend dùng để giải mã).

Để tạo Token test, bạn có thể tham khảo logic trong `test_jwt_auth.py`.

---

## 📂 Cấu trúc thư mục chính

- `core_backend/`: FastAPI App, LangGraph nodes, Middleware.
- `frontend/widget/`: Mã nguồn Preact Widget.
- `mcp_servers/`: Các server công cụ (Model Context Protocol).
- `scripts/`: Script quản trị (Seed DB, Key Gen, E2E Test).
- `docs/`: Technical Design và tài liệu nghiên cứu.
