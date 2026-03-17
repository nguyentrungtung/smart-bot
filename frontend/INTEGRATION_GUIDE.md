# Hướng dẫn Tích hợp Smart-Bot Widget vào Website

Tài liệu này hướng dẫn cách nhúng hộp chat Smart-Bot vào bất kỳ website nào (hỗ trợ React, Vue, HTML tĩnh, v.v.).

---

## 🏗 Cơ chế Hoạt động

Widget được xây dựng dưới dạng **Iframe Isolated**. Điều này đảm bảo:
1. **An toàn**: Code của widget không xung đột với CSS/JS của trang web chính.
2. **Bảo mật**: Sử dụng giao thức `postMessage` để truyền nhận Token JWT và đồng bộ kích thước (Resize).
3. **Hiệu năng**: Widget tải độc lập, không làm chậm trang chính.

---

## ⚡ Cách 1: Sử dụng Bootloader Script (Khuyên dùng)

Đây là cách đơn giản nhất. Bạn chỉ cần thêm một đoạn script vào cuối thẻ `<body>`.

### 🛡️ Cơ chế Xác thực Server-to-Server (Khuyên dùng cho Sản phẩm)

Để đảm bảo bảo mật và quản lý người dùng theo từng đối tác (Partner), bạn nên sử dụng luồng "Token Exchange".

#### Quy trình 3 bước:

**Bước 1: Server của bạn (Partner) đăng nhập vào Smart-Bot**
Dùng Token/Tài khoản Partner đã được cấp để lấy Access Token cho Server.
`POST /api/v1/auth/login`

**Bước 2: Đổi Token cho khách hàng (Visitor)**
Server của bạn gọi API này để lấy một Token JWT (RS256) dành riêng cho khách hàng đang truy cập web của bạn.
`POST /api/v1/auth/exchange-token`
- **Body**: `{ "visitor_id": "ID_NGUOI_DUNG_CUA_BAN" }`
- **Header**: `Authorization: Bearer <TOKEN_SERVER_BUOC_1>`

**Bước 3: Nhúng Token vào Frontend**
Kết quả trả về sẽ là một Token an toàn. Bạn nhúng nó vào code HTML của trang web chính:

```html
<script>
  window.SMART_BOT_TOKEN = "TOKEN_JWT_DÀNH_RIÊNG_CHO_VISITOR_TỪ_BƯỚC_2";
</script>
<script src="https://your-domain.com/bootloader.js"></script>
```

---

### 🎙 Microphone cho Voice Chat
**Có bật được.** Trong file `bootloader.js`, Iframe đã được cấu hình thuộc tính `allow="microphone"`. 

Tuy nhiên, **điều kiện bắt buộc** để Microphone hoạt động là Website khách (Parent Site) và Website chứa Bot (Iframe Site) đều phải chạy trên **HTTPS** (hoặc `localhost` khi dev). Nếu chạy trên HTTP, trình duyệt sẽ chặn quyền truy cập Microphone vì lý do bảo mật.

### Ưu điểm:
- Tự động tạo container, iframe.
- Tự động xử lý thu nhỏ/phóng to (responsive).
- Người dùng không cần viết CSS.
- **Tự động truyền nhận Token** từ biến toàn cục `window.SMART_BOT_TOKEN`.

---

## 🛠 Cách 2: Tự tạo Iframe (Manual Integration)

Dành cho các dự án cần kiểm soát sâu hơn về layout.

### 1. HTML & CSS
Thêm container và iframe vào trang của bạn:

```html
<!-- Container để giữ widget cố định ở góc màn hình -->
<div id="smart-bot-container" style="
    position: fixed;
    bottom: 20px;
    right: 20px;
    z-index: 999999;
    width: 80px;
    height: 80px;
    transition: all 0.3s cubic-bezier(0.175, 0.885, 0.32, 1.275);
    overflow: hidden;
    border-radius: 50%;
">
    <iframe 
        id="smart-bot-iframe"
        src="https://your-smart-bot-widget.com" 
        style="width: 100%; height: 100%; border: none; background: transparent;"
        allow="microphone"
    ></iframe>
</div>
```

### 2. JavaScript Đồng bộ (Resize & Auth)
Bạn cần lắng nghe sự kiện từ widget để cập nhật kích thước container:

```javascript
const iframe = document.getElementById('smart-bot-iframe');
const container = document.getElementById('smart-bot-container');
const WIDGET_URL = "https://your-smart-bot-widget.com";

// 1. Gửi Token JWT để xác thực
window.onload = () => {
    const userJWT = "YOUR_USER_JWT_TOKEN";
    
    // Đợi 1 giây để iframe kịp load script
    setTimeout(() => {
        iframe.contentWindow.postMessage({
            type: "SMART_BOT_AUTH",
            token: userJWT
        }, WIDGET_URL);
    }, 1000);
};

// 2. Lắng nghe yêu cầu Resize từ Widget
window.addEventListener('message', (event) => {
    // Bảo mật: Kiểm tra đúng origin
    if (event.origin !== WIDGET_URL) return;

    if (event.data.type === "SMART_BOT_RESIZE") {
        const { width, height } = event.data;
        
        // Cập nhật kích thước container
        container.style.width = typeof width === 'number' ? width + 'px' : width;
        container.style.height = typeof height === 'number' ? height + 'px' : height;

        // Nếu chiều cao lớn (đang mở chat), đổi border-radius
        if (parseInt(height) > 100) {
            container.style.borderRadius = '16px';
        } else {
            container.style.borderRadius = '50%';
        }
    }
});
```

---

## 🔒 Bảo mật (Security)

1. **Origin Whitelist**: Trong file `src/services/iframeSync.js` của widget, bạn PHẢI thêm domain của client vào mảng `allowedOrigins`.
2. **Content Security Policy (CSP)**: Nếu trang web chính có CSP, hãy cho phép iframe từ domain của bạn: `frame-src https://your-smart-bot-widget.com`.
3. **JWT**: Luôn truyền JWT qua `postMessage` thay vì Query String để tránh rò rỉ token trong log server.

---

## 🎨 Tinh chỉnh Giao diện

Widget hỗ trợ Responsive tự động. Khi người dùng nhấn nút "Maximize" trong widget, nó sẽ gửi sự kiện `SMART_BOT_RESIZE` với các giá trị:
- `width`: `calc(100vw - 4rem)`
- `height`: `calc(100vh - 8rem)`

Đảm bảo container của bạn không bị giới hạn bởi thuộc tính `max-width` của trang cha.
