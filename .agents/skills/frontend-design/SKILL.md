---
name: frontend-design
description: >-
  Guides the UI/UX architecture, visual hierarchy, typography, and static data
  binding for the 7-screen VibeTrade v1.1 Dashboard on GitHub Pages. Activate this
  skill when designing or building frontend components under frontend/.
---

# Frontend Design System (`frontend-design`)

Tiêu chuẩn thiết kế giao diện **Quant Intelligence Terminal** cho 7 màn hình của **VibeTrade v1.1** trên GitHub Pages (`frontend/` — React 19, Tailwind CSS, ECharts 6, Lucide Icons, Zustand).

## 1. Triết lý Thiết kế: Explainable Institutional Quant Terminal
- **Trung thực & Định lượng (No Chat-Bot Gimmicks):** Giao diện phản ánh đúng bản chất hệ thống chấm điểm định lượng có giải thích, không dùng giao diện khung chat giả lập LLM đối thoại khi không có backend LLM.
- **Mật độ thông tin có phân cấp rõ ràng:** Người dùng nhìn vào trong 3 giây phải nắm được ngay: (1) Hệ thống còn sống không (`heartbeat`), (2) Thị trường đang ở Regime nào, (3) Danh mục `$10.0` đang lời/lỗ thực tế bao nhiêu sau phí, và (4) Tín hiệu nào đang được chấm điểm cao nhất.
- **Typography chuẩn Tài chính:**
  - Văn bản giao diện: `Inter`.
  - Mọi con số giá, khối lượng, điểm số, phần trăm, PnL, phí, drift và mốc thời gian UTC: bắt buộc dùng `JetBrains Mono` kèm thuộc tính `tabular-nums` để các cột số luôn thẳng hàng tuyệt đối.

## 2. Kiến trúc 7 Màn hình Chuẩn (P7 Specification)
1. **Overview:** Thẻ KPI tổng hợp (`Total Equity`, `Cash`, `Realized PnL`, `Unrealized PnL`, `Market Regime`, `Active Opportunities`, `System Heartbeat`), mini equity curve và top tín hiệu mới nhất.
2. **Market Scanner:** Bảng quét toàn bộ vũ trụ cặp `*-USDT` Spot trên OKX (giá đóng nến gần nhất, biến động, volume quote 24h, spread bps, thanh khoản, cờ bất thường từ Surveillance Mode).
3. **Opportunity Queue:** Hàng đợi các cơ hội đã vượt bộ lọc Scanner, trạng thái kích hoạt Focus Session, mã định danh `signal_id` (`symbol:timeframe:candle_ts`), và lịch sử chuyển trạng thái.
4. **AI Research Room (Deterministic Personas):** Trình bày trực quan bảng đối đầu định lượng:
   - Thang điểm `Bull Score (+)` vs `Bear Score (-)` -> `Crucible Net Score` x `Regime Multiplier`.
   - Bảng **Evidence Binding** chi tiết từng rule (`metric`, `value`, `threshold`, `points`, `timestamp`).
   - Huy hiệu kiểm định độc lập (`Data Auditor`, `Strategy Reviewer`) và trạng thái `INCONCLUSIVE` rõ nét khi thiếu dữ liệu.
5. **Paper Portfolio ($10 Virtual Account):** Tách bạch số dư tiền mặt USDT, vị thế đang mở (`Unrealized PnL`), lịch sử khớp lệnh (`Realized PnL`), bảng kê chi tiết phí (`0.1%`), slippage, `schedule_drift_cost`, và nhật ký lệnh bị chặn `REJECTED_BY_CONSTRAINT`.
6. **Performance:** Đường cong vốn sau chi phí (Net Equity Curve vs `$10.0` baseline & BTC Buy-and-Hold baseline), Max Drawdown, Win Rate, Profit Factor, phân rã tổng chi phí ma sát (phí + spread/slippage + schedule drift).
7. **System Monitor:** Trạng thái `heartbeat.json` (lần chạy cuối, độ trễ lịch GitHub Actions, thời gian chạy job, phiên bản schema, dung lượng/số bản ghi của 5 file JSON trên nhánh `data-state`).

## 3. Quy ước Màu sắc Ngữ nghĩa & Khả năng Đọc
- Tông nền tối chuyên sâu (Slate/Zinc Carbon) có độ tương phản đạt chuẩn WCAG AA, kèm thẻ phân tách viền mảnh `1px` sắc nét.
- Màu ngữ nghĩa nhất quán:
  - Tích cực / `Bull` / Lãi ròng: Emerald/Teal.
  - Rủi ro / `Bear` / Lỗ ròng: Rose/Crimson.
  - Cảnh báo / `REJECTED_BY_CONSTRAINT` / Heartbeat trễ: Amber.
  - `INCONCLUSIVE` / Trung tính / Chờ đóng nến: Slate/Indigo trung tính.
- Responsive hoàn chỉnh trên cả màn hình rộng Desktop và điện thoại di động (bảng rộng có cuộn ngang mượt kèm cột `Symbol` ghim cố định).

## 4. Kết nối Dữ liệu Tĩnh (Static Data Layer)
- Tầng client fetch trực tiếp 5 file JSON (`market_snapshot.json`, `opportunity_queue.json`, `paper_portfolio.json`, `research_history.json`, `heartbeat.json`) với cơ chế chống cache cũ hợp lý (query mốc phiên bản từ `heartbeat.json`) và xác thực kiểu dữ liệu an toàn trước khi đưa vào Zustand store.
