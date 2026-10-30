---
name: codebase-surgical-auditor
description: >-
  Executes Read-Only surgical audits of the Vibe-Trading repository (Phase P0 and
  pre-refactor gates). Enforces the strict No-Full-Rewrite policy, classifies every
  module/file into KEEP, ADAPT, REPLACE, or REMOVE, and requires exact file path
  and symbol citations.
---

# Codebase Surgical Auditor (`codebase-surgical-auditor`)

Quy trình kiểm toán phẫu thuật mã nguồn phục vụ **Phase P0** và các bước tiền cải tạo của **VibeTrade v1.1**.

## 1. Nguyên tắc Bất biến (Hard Constraints)
1. **Chế độ Read-Only Tuyệt đối khi Audit:**
   - Trong quá trình kiểm toán, **cấm sửa đổi, xóa, đổi tên hoặc định dạng lại** bất kỳ dòng code hiện có nào của repository gốc (`HKUDS/Vibe-Trading`).
   - Luôn xác minh bằng `git diff` (phải rỗng đối với toàn bộ file đã được Git theo dõi của repo gốc).
2. **Cấm Đập đi Xây lại (`No Full Rewrite`):**
   - Không được viết mới từ con số 0 toàn bộ hệ thống khi `Vibe-Trading` đã có sẵn các thư viện toán định lượng, backtest/factor primitives, cấu trúc paper trading, hoặc UI components có thể tái sử dụng.
   - Mọi kế hoạch chuyển đổi sang kiến trúc **$0 tuyệt đối** phải tận dụng tối đa phần lõi định lượng sạch hiện có và chỉ phẫu thuật đúng điểm nghẽn.
3. **Trích dẫn Bằng chứng Mã nguồn Bắt buộc (Strict Code Citation):**
   - Mọi nhận định kỹ thuật và quyết định phân loại **bắt buộc** trích dẫn chính xác:
     - Đường dẫn file tương đối từ gốc workspace (ví dụ: `agent/src/providers/factory.py`, `frontend/src/App.tsx`).
     - Tên class, hàm, hằng số, endpoint hoặc hook cụ thể (ví dụ: `ChatModelFactory.build()`, `PaperTradeEngine.submit_order()`).

## 2. Hệ Phân loại 4 Nhãn Chuẩn (`KEEP` / `ADAPT` / `REPLACE` / `REMOVE`)

Mọi thư mục, module và file trọng yếu trong repository phải được gán **đúng 1 trong 4 nhãn** sau kèm lý do kỹ thuật rõ ràng:

| Nhãn | Định nghĩa Phẫu thuật | Tiêu chí Áp dụng trong VibeTrade v1.1 |
| :--- | :--- | :--- |
| **`KEEP`** | **Giữ nguyên 100%** | Module thuần toán học, thống kê, tính chỉ báo kỹ thuật không rò rỉ tương lai, tiện ích chuẩn hóa, hoặc UI primitives sạch, không gọi LLM trả phí và không phụ thuộc server chạy nền 24/7. |
| **`ADAPT`** | **Giữ khung kiến trúc, sửa logic bên trong** | Module có cấu trúc dữ liệu/luồng xử lý tốt nhưng cần điều chỉnh tham số và quy tắc nghiệp vụ (ví dụ: sổ cái Paper Trading điều chỉnh cho vốn `$10.0` + `schedule_drift_cost` + `REJECTED_BY_CONSTRAINT`; Frontend chuyển sang đọc 5 file JSON tĩnh trên 7 màn hình; GitHub Workflows chuyển sang chạy cron 15 phút đẩy `data-state`). |
| **`REPLACE`** | **Giữ interface/contract đầu vào-đầu ra, thay ruột** | Module đóng vai trò mắt xích cần thiết trong kiến trúc nhưng phần ruột hiện tại tốn phí hoặc sai nguồn dữ liệu (ví dụ: thay ruột LLM/LangGraph trong Personas/Swarm bằng **Weighted Scoring Engine + Evidence-based Templates**; thay các bộ nạp dữ liệu chứng khoán/đa sàn cũ bằng **OKX Public API USDT Spot Data Layer**). |
| **`REMOVE`** | **Loại bỏ / Ngắt kích hoạt hoàn toàn** | Module gây phát sinh chi phí API, mở rộng bề mặt rủi ro đặt lệnh thật, hoặc hoàn toàn dư thừa với hệ thống Crypto tự hành `$0` trên GitHub Actions/Pages (ví dụ: cổng xác thực LLM trả phí, 15+ kênh chat bot Discord/Telegram/Feishu/WeChat, vỏ Electron Desktop, đóng gói ZimaOS, Pixel Office, connector đặt lệnh thật chứng khoán/forex). |

## 3. Quy trình Kiểm toán 5 Khía cạnh Bắt buộc
Khi thực thi kiểm toán P0, lần lượt truy vết và lập sơ đồ luồng dữ liệu qua 5 trục:
1. **Phụ thuộc LLM API trả phí & Nguồn dữ liệu cũ:** Xác định mọi nơi khởi tạo model (`langchain`, `langgraph`, `openai`, `anthropic`, `deepseek`, v.v.) và mọi data loader (`yfinance`, `akshare`, `tushare`, `ccxt`, `duckdb`, broker SDKs).
2. **Cơ chế Lưu trữ Trạng thái (Persistence/State):** Kiểm tra SQLite (`sessions.db`, `memory_index.db`, `strategy_discovery.db`), DuckDB/Parquet, JSON/YAML runtime files, và đối chiếu khoảng cách tới kiến trúc 5 file JSON trên nhánh `data-state`.
3. **Cơ chế Lập lịch & Vòng lặp (Scheduling/Loop):** Kiểm tra daemon, cron nội bộ, `scheduled_research`, background tasks, WebSocket/SSE loops và đánh giá khả năng chuyển sang mô hình chạy ngắn hạn theo chu kỳ 15 phút trên GitHub Actions.
4. **Paper Trading, Tính toán PnL & Quản lý Rủi ro:** Kiểm tra cách khớp lệnh ảo hiện tại, phí, slippage, tách biệt `realized_pnl` / `unrealized_pnl`, kiểm tra `minSz`/precision và các cổng chặn rủi ro (`mandate`, `order_gate`, `killswitch`).
5. **Kiến trúc Frontend & Kết nối Backend:** Kiểm tra router, state store (`zustand`), các trang hiện có, REST/SSE/WebSocket client gọi `api_server.py`, và lộ trình chuyển sang Static JSON Dashboard 7 màn hình trên GitHub Pages.

## 4. Bước Xác thực Sau Kiểm toán (Validation Steps)
1. Chạy `git status --porcelain` để xác nhận **0 file gốc bị sửa đổi** (`M` hoặc `D` = 0).
2. Đảm bảo mọi đường dẫn file và tên hàm/class nêu trong báo cáo đều tồn tại thật trong workspace.
