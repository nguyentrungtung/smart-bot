# 🛡️ Hướng dẫn Tích hợp Smart-Bot Widget (Developer Guide)

Chào mừng bạn đến với hướng dẫn tích hợp **Smart-Bot Advisor**. Hệ thống được thiết kế để nhúng vào bất kỳ website nào chỉ với **một dòng code**, tương tự như Google Analytics hoặc Intercom.

---

Hệ thống được thiết kế để nhúng vào bất kỳ website nào chỉ với **một đoạn mã bootloader**, tương tự như Google Analytics, Intercom hoặc Facebook Pixel.

---

## ⚡ 1. Tích hợp Nhanh (Google Analytics Style)

Đây là cách tích hợp chuyên nghiệp nhất. Copy đoạn mã sau vào trước thẻ đóng `</body>`:

```html
<script>
  (function(w,d,s,o,f,js,fjs){
    w['SmartBotObject']=o;w[o]=w[o]||function(){(w[o].q=w[o].q||[]).push(arguments)},w[o].l=1*new Date();
    js=d.createElement(s),fjs=d.getElementsByTagName(s)[0];
    js.id=o;js.src=f;js.async=1;fjs.parentNode.insertBefore(js,fjs);
  }(window,document,'script','smartbot','http://localhost:5173/embed.js'));

  // Khởi tạo Chatbot với Token (Nếu có)
  smartbot('init', {
    token: "ACCESS_TOKEN_CỦA_NGƯỜI_DÙNG"
  });
</script>
```

**Cơ chế hoạt động:**
- **Asynchronous**: Script tải không đồng bộ, không làm chậm tốc độ load trang web chính.
- **Command Queue**: Bạn có thể gọi `smartbot('init', ...)` ngay cả khi script chưa tải xong, các câu lệnh sẽ được đưa vào hàng đợi và xử lý ngay khi script sẵn sàng.
- **Auto-Injection**: Tự động nhận diện domain và thiết lập Iframe bảo mật.

**Ưu điểm:**
- Tự động tạo Container và Iframe.
- Tự động xử lý Resize (Thu nhỏ/Phóng to) mượt mà.
- Đã được tối ưu về Z-index để luôn hiển thị trên cùng.
- Hỗ trợ truyền Token JWT an toàn qua `postMessage`.
- Hỗ trợ cập nhật Token mới mà không cần tải lại trang (Token Rotation).

---

---

## 🏗️ 2. Quản lý vòng đời Token (Token Rotation)

Vì lý do bảo mật, Access Token thường có thời hạn ngắn (mặc định **60 phút**). Để duy trì chatbot lâu dài mà không bị gián đoạn, website vệ tinh cần thực hiện cơ chế **xoay vòng token**.

### Quy trình chuẩn:
1. **Login ban đầu**: Website gọi API `/auth/login` (hoặc `/auth/exchange-token`) để lấy bộ đôi `access_token` và `refresh_token`.
2. **Cập nhật định kỳ**: Trước khi `access_token` hết hạn, sử dụng `refresh_token` để lấy Access Token mới và nạp vào Bot qua lệnh `init`.

### Mã triển khai mẫu:
```javascript
let tokens = { access: null, refresh: null };

// 1. Hàm lấy Token (Thường gọi khi người dùng bắt đầu vào web)
async function authenticateBot() {
  const resp = await fetch('http://localhost:8000/api/v1/auth/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ user_id: 'visitor_123', password: 'password_neu_co' })
  });
  const data = await resp.json();
  tokens.access = data.access_token;
  tokens.refresh = data.refresh_token;

  // Nạp token vào Bot
  smartbot('init', { token: tokens.access });

  // Thiết lập tự động refresh sau mỗi 45 phút (đảm bảo trước khi Access Token 1h hết hạn)
  setInterval(refreshBotSession, 45 * 60 * 1000);
}

// 2. Hàm làm mới Session dùng Refresh Token
async function refreshBotSession() {
  console.log("Refreshing access token...");
  const resp = await fetch('http://localhost:8000/api/v1/auth/refresh', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ refresh_token: tokens.refresh })
  });
  
  if (resp.ok) {
    const data = await resp.json();
    tokens.access = data.access_token;
    // Cập nhật token mới cho Bot (Bot nhận tức thì, không load lại trang)
    smartbot('init', { token: tokens.access });
  }
}

authenticateBot();
```

**Ưu điểm:**
- **Duy trì lâu dài**: Chatbot có thể chạy liên tục miễn là `refresh_token` còn hạn.
- **Mượt mà**: Việc cập nhật token diễn ra ngầm, người dùng không hề hay biết.
- **Bảo mật**: Chỉ truyền `access_token` ngắn hạn cho Frontend Iframe.

---

## 🏗️ 3. Quy trình Xác thực Bảo mật (Server-to-Server)

Để bảo vệ dữ liệu và định danh người dùng chính xác, Smart-Bot sử dụng cơ chế **Token Exchange**.

### Sơ đồ hoạt động:
1. **Server của bạn** gọi API Smart-Bot để lấy Token cho khách truy cập (Visitor).
2. **Server của bạn** trả về Token này vào HTML của website (biến `window.SMART_BOT_TOKEN`).
3. **Embed Script** tự động đọc Token này và xác thực với Bot.

#### Bước 1: Đổi Token cho khách (Visitor)
Server của bạn gọi API sau (đã có Header Authorization của Partner):
```bash
POST /api/v1/auth/exchange-token
{
  "visitor_id": "user_id_trong_he_thong_cua_ban",
  "metadata": { "name": "Nguyễn Văn A", "tier": "VIP" }
}
```

#### Bước 2: Nhúng vào Frontend
```html
<script>
  window.SMART_BOT_TOKEN = "TOKEN_NHẬN_ĐƯỢC_TỪ_BƯỚC_1";
</script>
```

---

## 🛠️ 4. Tích hợp Thủ công (Manual Integration)

Nếu bạn muốn kiểm soát vị trí hoặc CSS của Iframe, bạn có thể tự tạo:

```html
<div id="smart-bot-wrapper" style="position:fixed; bottom:20px; right:20px; width:80px; height:80px;">
  <iframe 
    src="http://localhost:5173" 
    allow="microphone" 
    style="width:100%; height:100%; border:none;">
  </iframe>
</div>
```

**Lưu ý quan trọng:** Bạn phải tự lắng nghe sự kiện `SMART_BOT_RESIZE` để thay đổi kích thước `div` bọc ngoài, nếu không hộp chat sẽ bị cắt (clipping).

---

## 🎙️ 4. Điều kiện để Voice Chat (Microphone) hoạt động

Để người dùng có thể sử dụng chức năng giọng nói:
1. **HTTPS là bắt buộc**: Cả trang web của bạn (Parent) và Smart-Bot Widget phải chạy trên HTTPS. Trình duyệt sẽ chặn Microphone trên HTTP.
2. **Iframe Permission**: Phải có thuộc tính `allow="microphone"` trong thẻ iframe (Embed Script đã tự động thêm thuộc tính này).

---

## 🎨 5. Tùy chỉnh (Customization)

| Thuộc tính | Mô tả |
| :--- | :--- |
| `window.SMART_BOT_TOKEN` | Token JWT dùng để xác thực người dùng. |
| `window.SMART_BOT_THEME` | (Sắp có) Chế độ 'light' hoặc 'dark'. |
| `Z-Index` | Mặc định là `2147483647` để đảm bảo luôn ở trên cùng. |

---

## � 6. Kiểm tra & Troubleshooting

- **Lỗi 401/403**: Token hết hạn hoặc sai `visitor_id`. Hãy kiểm tra lại log tại `/auth/exchange-token`.
- **Widget không hiển thị**: Kiểm tra xem `http://localhost:5173/embed.js` có tải được không (Network tab trong Chrome DevTools).
- **Không thể gõ chữ**: Đảm bảo Iframe không bị che khuất bởi một thẻ `div` trong suốt khác của trang web chính.

---
*Tài liệu này được cập nhật vào: 2026-03-20*
