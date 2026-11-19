# Global Shop Dianshang by Peng (`v1.0.1`)

Hệ thống **Nghiên cứu Sản phẩm Tiềm năng để Bán thương mại**, **Theo dõi Từ khoá / Sản phẩm / Shop (Shopee & TikTok Shop)**, **Tìm Nguồn hàng Nội địa Trung Quốc (1688 · Taobao/Tmall · Pinduoduo · Douyin)** và **Quản trị Chiến dịch Ngành hàng & Lợi nhuận Nhà bán** — xây dựng trên nền tảng gọn nhẹ chuẩn Peng (100% Python 3 Standard Library + SQLite WAL + macOS Keychain SecretStore + Vanilla HTML/CSS/JS SPA, hỗ trợ **Loopback** và **Tailscale**).

---

## 4 Phần Chính Của Hệ Thống

### Phần 1 · Nghiên cứu Thị trường, Từ khoá & Theo dõi Tự động
- **Săn Sản phẩm Bán chạy Đa sàn (`/san-sp`)**: Quét sản phẩm trên Shopee, TikTok Shop, Lazada, Facebook Ads, Google Trends; chấm điểm **Tiềm năng Nhập bán (6 trụ cột Seller bằng TypeSafe Jev `jev-1.14.0`)**.
- **Tra cứu Từ khoá Shopee & TikTok (`/tu-khoa`)**: Gợi ý từ khoá mở rộng, kiểm tra tổng số lượng sản phẩm trên từ khoá, tổng lượt bán, dải giá (TB / trung vị / min-max), tỷ lệ Mall, mức độ tập trung của Top 3 shop và chấm điểm cơ hội từ khoá bằng Jev AI.
- **Theo dõi Định kỳ & Đối chiếu Sản phẩm Mới (`/theo-doi`)**:
  - **Theo dõi Từ khoá (Shopee / TikTok)**: Mỗi lần kiểm tra tự động đối chiếu với kỳ trước để phát hiện **`+N` sản phẩm mới xuất hiện**, sản phẩm đang tăng vọt lượt bán và biến động tổng dung lượng từ khoá.
  - **Theo dõi Sản phẩm (Shopee / TikTok)**: Theo dõi biến động giá, lượt mua mới (`+delta_sold`), doanh số ước tính theo thời gian.
  - **Theo dõi Shop Đối thủ (Shopee / TikTok)**: Phát hiện sản phẩm mới shop đối thủ vừa đăng bán và sản phẩm chủ lực kéo doanh số.
- **Quét Sản phẩm theo Shop & Công cụ Creator TikTok (`/soi-shop`, `/creators`)**: Bóc tách danh mục sản phẩm của shop đối thủ (phân tách SP chủ lực `Hero` vs SP mồi kéo traffic) và tìm sản phẩm hot qua kênh Creator TikTok / lưu KOC phục vụ booking cho shop.

### Phần 2 · Kho Sản phẩm, Nguồn hàng Trung Quốc (1688 · Taobao · Pinduoduo) & Kho Shop
- **Kho Sản phẩm & Phân loại 13 Ngành hàng (`/kho`)**: Đánh giá lượt mua, lượt bán, doanh số GMV, giá vốn về tay & biên lợi nhuận ròng; phân nhóm `Đang bùng nổ`, `Mới nổi ít cạnh tranh`, `Bán bền vững`, `Đã có nguồn nhập TQ`, `Đang nhập / Test bán`, `Đã loại`; so sánh 2–5 SP và xuất CSV chuẩn UTF-8 BOM.
- **Nguồn hàng Điện thương Trung Quốc (`/nguon-hang-tq`)**: Tìm nguồn sỉ trên **1688, Taobao/Tmall, Pinduoduo (拼多多), Douyin** (hỗ trợ gợi ý từ khoá tiếng Việt → tiếng Trung `中文`) qua **Apify Store (#1)** → **Treg.to (#2)**; tính chính xác **Giá vốn về kho VN (`¥ CNY -> VND` + cước cân nặng + phí mua hộ)** và ghép 1-click vào sản phẩm trong Kho.
- **Kho Shop (`/kho-shop`)**: Quản lý danh sách **Shop vận hành của mình** và **Shop đối thủ trọng điểm** trên Shopee, TikTok Shop, Lazada.

### Phần 3 · Soi Đối thủ, Đánh giá Video AI & Clone Video 15s
- **Soi Link Sản phẩm & Fanpage Facebook (`/soi-san-pham`)**: Soi chi tiết link sản phẩm đa sàn, kiểm tra phủ sóng video TikTok và quảng cáo Facebook Ads Library.
- **Đánh giá Video Bán hàng Jev AI (`/video-jev`)**: Trích xuất **4 khung hình FFmpeg + kịch bản 3 phần (`Hook 0–3s · Body Demo · CTA`)**, lưu danh sách Video Mẫu Quan trọng.
- **Clone Video 15s cho Shop (`/clone-video`)**: Cắt cảnh `<=15s` bằng FFmpeg và sinh bộ JSON Prompt chuẩn **`Nano Banana 2.1`** (Ảnh 9:16) + **`Gemini Omni 1.2 Flash`** (Video 4K + khoá giọng đọc tiếng Việt) gắn trực tiếp với sản phẩm và shop của bạn.

### Phần 4 · Chiến dịch Ngành hàng, Doanh số Nhà bán & Hệ thống
- **Chiến dịch Bán hàng theo Ngành hàng (`/chien-dich`)**: Phễu triển khai 5 bước (`Chọn mẫu` → `Chốt xưởng TQ` → `Nhập test` → `Đăng sàn & Làm Video` → `Scale tồn kho Win`), gắn Shop vận hành, checklist hàng ngày và báo cáo 08:00 sáng qua Telegram.
- **Doanh số, Đơn bán CSV & Lợi nhuận Ròng (`/doanh-so`)**: Nhập CSV đơn hàng Shopee/TikTok Seller, theo dõi chi phí nhập hàng/quảng cáo, tính chính xác Lượt bán, Doanh số GMV, Giá vốn COGS, Phí sàn và Lãi ròng thực tế.
- **Hệ thống, Nhật ký `GS-XXXX`, MCP & Telegram Bot (`/nhat-ky`, `/caidat`)**: Mã nhật ký tuần tự `GS-0001..GS-XXXX`, cổng MCP `/mcp` (HTTP + Stdio), trình duyệt Chrome CDP riêng (`127.0.0.1:9349`), kết nối Telegram Bot `@tc_global1_shop_bot` (khoá cứng Chat ID được phép) và truy cập qua **Tailscale (`8999`)**.

---

## Khởi chạy & Kiểm thử

```bash
# Chạy ứng dụng trên cổng 8999
python3 run_webapp.py --data-dir ./local-data --port 8999

# Mở truy cập từ xa qua mạng riêng Tailscale
tailscale serve --bg --http 8999 http://127.0.0.1:8999

# Chạy toàn bộ Unit & HTTP E2E Tests
python3 -m unittest discover -s tests -v

# Chạy Smoke Test
bash scripts/smoke_api.sh http://127.0.0.1:8999
```
