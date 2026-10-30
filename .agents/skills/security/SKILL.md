---
name: security
description: >-
  Enforces Zero-Secret architecture, live-trading kill-switches, GitHub Actions
  hardening, and XSS-safe static dashboard security for VibeTrade v1.1. Activate
  this skill when configuring APIs, CI/CD workflows, persistence, or frontend rendering.
---

# Security & Operational Safety (`security`)

Tiêu chuẩn bảo mật và an toàn vận hành cho **VibeTrade v1.1** (hệ thống public/open-source-friendly chạy trên GitHub Actions & GitHub Pages với ngân sách `$0`).

## 1. Kiến trúc Zero-Secret & Khóa cứng Live Trading
- **Không lưu trữ khóa sàn hoặc khóa LLM:** VibeTrade v1.1 chỉ gọi **OKX Public API** (endpoints `/api/v5/market/*` và `/api/v5/public/*`). Cấm yêu cầu, đọc, hoặc ghi `OKX_API_KEY`, `OKX_SECRET_KEY`, `OKX_PASSPHRASE`, khóa ví private key, seed phrase, hay API key của các hãng LLM.
- **Fail-Closed đối với Đặt lệnh Thật:** Mọi đường dẫn thực thi giao dịch trong VibeTrade v1.1 chỉ được phép ghi vào sổ cái mô phỏng (`paper_portfolio.json`). Nếu phát hiện bất kỳ nỗ lực gọi endpoint đặt lệnh thật (`/api/v5/trade/*` hoặc broker connectors cũ), hệ thống phải chặn ngay lập tức (`PermissionError` / Halt).
- **Kiểm soát `.gitignore` & Git Staging:** Không bao giờ dùng `git add -A` hoặc `git add .` mù quáng mà không kiểm tra `git status`; tuyệt đối không commit `.env`, token cache, hoặc cấu hình cá nhân.

## 2. Bảo mật GitHub Actions (CI/CD Hardening)
- **Least-Privilege `permissions`:** Khai báo `permissions` tối thiểu ở mức workflow/job:
  - Job test/audit trên `main`: `contents: read`.
  - Job scanner cập nhật `data-state`: `contents: write` (chỉ push sang nhánh `data-state`, không bao giờ force-push hoặc ghi đè nhánh `main`).
  - Job deploy GitHub Pages: `contents: read`, `pages: write`, `id-token: write`.
- **Chống Script Injection:** Không bao giờ nhúng trực tiếp biến đầu vào bên ngoài (`${{ github.event.inputs.* }}`, commit message, tên nhánh) thẳng vào khối `run: |` của shell; luôn truyền qua biến môi trường (`env:`) trước khi đọc trong bash/python.
- **Timeout bảo vệ:** Mọi job GitHub Actions phải đặt `timeout-minutes` chặt chẽ (ví dụ `5`–`10` phút cho chu kỳ quét 15 phút) để tránh treo runner làm cạn quota miễn phí của GitHub Actions.

## 3. Toàn vẹn Dữ liệu Đầu vào & An toàn GitHub Pages
- **Untrusted External API Response:** Phản hồi JSON từ OKX Public API được xem là dữ liệu bên ngoài không tin cậy; bắt buộc kiểm tra kiểu dữ liệu, giới hạn độ dài chuỗi `instId`, chặn giá trị âm/vô cực (`NaN`, `Inf`, `<= 0` cho giá và khối lượng chuẩn) bằng Pydantic/JSON Schema trước khi lưu vào `data-state`.
- **An toàn XSS trên Dashboard tĩnh:**
  - Trên React frontend, luôn render dữ liệu snapshot qua cơ chế escape mặc định của JSX.
  - Cấm dùng `dangerouslySetInnerHTML`, `eval()`, hoặc `new Function()` trên dữ liệu đọc từ `data-state` JSON.
- **Bảo mật kết nối HTTP:** Luôn bật xác thực chứng chỉ TLS (`verify=True` với `certifi`), chỉ gọi giao thức `https://www.okx.com`.

## 4. Bước Kiểm tra Xác thực (Validation Steps)
1. Quét nhanh các chuỗi nhạy cảm hoặc endpoint đặt lệnh thật trước khi commit:
   Kiểm tra diff không chứa `/api/v5/trade`, `API-ACCESS-KEY`, `OKX-ACCESS-SIGN`, `sk-`, hoặc `PRIVATE KEY`.
2. Rà soát mọi file `.github/workflows/*.yml` đảm bảo có đủ `permissions`, `concurrency`, và `timeout-minutes`.
