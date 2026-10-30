---
name: deterministic-personas-engine
description: >-
  Governs Phases P4 and P5 (Deterministic Research Team and Independent Verification).
  Replaces paid LLM calls with an Explainable Quantitative System using Weighted Scoring
  Engines, Evidence-based Templates, INCONCLUSIVE fallbacks, and independent score auditing.
---

# Deterministic Personas & Verification Engine (`deterministic-personas-engine`)

Quy chuẩn thiết kế khối Phân tích Đa vai trò Tất định (**Phase P4**) và Kiểm định Độc lập (**Phase P5**) cho **VibeTrade v1.1**.

## 1. Triết lý Cốt lõi: Explainable Quantitative System
1. **Không gọi LLM trả phí ($0 API Cost):** Tuyệt đối không kết nối tới bất kỳ dịch vụ LLM đám mây hay mô hình sinh ngôn ngữ trả phí nào.
2. **Không giả vờ làm LLM (Zero Fake Roleplay):**
   - Không viết các đoạn hội thoại đóng kịch giả tạo, không chèn từ ngữ cảm tính ngẫu nhiên, không sinh văn bản không có số liệu hậu thuẫn.
   - Hệ thống thể hiện đúng bản chất là một **Hệ thống Định lượng Có khả năng Giải thích (Explainable Quantitative System)**: mỗi vai trò (`Persona`) là một bộ quy tắc toán học độc lập có trọng số tường minh và xuất báo cáo qua **Evidence-based Templates** gắn chặt với dữ liệu thật.
3. **Tính Tất định Tuyệt đối (`f(x) == f(x)`):** Cùng một gói dữ liệu đầu vào phải luôn cho ra chính xác cùng một điểm số, cùng một danh sách bằng chứng và từng ký tự báo cáo giống hệt nhau.

## 2. Kiến trúc Weighted Scoring Engine (Phase P4)

### A. Tầng `Analysts` (Chuẩn bị Vector Đặc trưng Định lượng)
Tính toán các chỉ số cơ sở đã đóng nến từ P1–P3:
- **Trend & Momentum Analyst:** Cấu trúc EMA (`EMA20/50/200`), độ mạnh xu hướng (`ADX`), động lượng (`RSI`, `MACD histogram slope`), vị trí giá trong cấu trúc biên độ.
- **Volume & Volatility Analyst:** Đột biến khối lượng (`Volume Z-Score` / `RVOL`), biên độ biến động chuẩn hóa (`ATR%`), độ nén/bung Bollinger-Keltner.
- **Liquidity & Microstructure Analyst:** Chênh lệch giá mua-bán (`spread_bps`), độ sâu sổ lệnh top-N quanh giá khớp (`orderbook_depth_usd`), mất cân bằng sổ lệnh (`orderbook_imbalance`).

### B. `Bull Researcher` (Tổng hợp Điểm Tích cực $S_{\text{Bull}} \ge 0$)
- Đánh giá tập quy tắc thuận chiều tăng giá $\{R_1^{+}, R_2^{+}, \dots, R_m^{+}\}$.
- Mỗi quy tắc $i$ có hàm chấm điểm chuẩn hóa $s_i^{+} \in [0, 1]$ và trọng số cố định $w_i^{+} > 0$ ($\sum w_i^{+} = 100$):
  $$S_{\text{Bull}} = \sum_{i=1}^{m} w_i^{+} \cdot s_i^{+} \in [0, 100]$$
- Ví dụ bằng chứng cộng điểm: xu hướng đa khung đồng thuận, breakout khối lượng vượt ngưỡng `RVOL >= 2.0`, động lượng bứt phá khỏi vùng tích lũy với thanh khoản sâu.

### C. `Bear Researcher` (Tổng hợp Điểm Rủi ro / Phản biện $S_{\text{Bear}} \ge 0$)
- Độc lập quét tập quy tắc rủi ro $\{R_1^{-}, R_2^{-}, \dots, R_k^{-}\}$ với trọng số $w_j^{-} > 0$ ($\sum w_j^{-} = 100$):
  $$S_{\text{Bear}} = \sum_{j=1}^{k} w_j^{-} \cdot s_j^{-} \in [0, 100]$$
- Ví dụ bằng chứng trừ điểm: giá sát vùng kháng cự đỉnh gần, quá mua cực đoan (`RSI > 75` kèm suy yếu khối lượng), `spread_bps` giãn rộng, thanh khoản mỏng dễ trượt giá, hoặc biến động đuôi cao bất thường.

### D. `Crucible` (Tổng hợp Điểm Ròng & Nhân Hệ số Chế độ Thị trường)
- Tính điểm chênh lệch cơ sở và điều chỉnh theo `Market Regime Multiplier` ($M_{\text{regime}}$) được xác định bằng quy tắc rõ ràng từ xu hướng chuẩn của thị trường chung (`BTC-USDT` + độ rộng thị trường):
  $$S_{\text{net}} = (S_{\text{Bull}} - S_{\text{Bear}}) \times M_{\text{regime}}$$
- Bảng `M_regime` phải được định nghĩa tường minh trong file cấu hình bất biến (ví dụ: `TRENDING_BULL = 1.10`, `NEUTRAL_RANGE = 0.85`, `HIGH_VOL_CHOP = 0.60`, `RISK_OFF_PANIC = 0.25` hoặc khóa chiều mua mới).
- Phân loại quyết định dựa trên ngưỡng rõ ràng của $S_{\text{net}}$ và ngưỡng trần rủi ro $S_{\text{Bear}} \le S_{\text{Bear,max}}$: `ACTIONABLE_LONG`, `WATCHLIST`, `NEUTRAL_PASS`, hoặc `AVOID_HIGH_RISK`.

## 3. Ràng buộc Bằng chứng (`Evidence Binding`) & Trạng thái `INCONCLUSIVE`
- **Cấu trúc Bằng chứng Bắt buộc:** Mọi kết luận thành phần của `Analysts`, `Bull`, `Bear`, `Crucible` phải đính kèm bản ghi có cấu trúc:
  ```json
  {
    "rule_id": "BULL_VOL_BREAKOUT_01",
    "persona": "bull_researcher",
    "metric": "rvol_20",
    "value": 2.45,
    "threshold": ">= 1.80",
    "weight": 20.0,
    "score_contribution": 16.2,
    "candle_timestamp": 1730268900000,
    "template_summary": "RVOL(20) đạt 2.45x (vượt ngưỡng >= 1.80x tại nến 2026-10-30T05:15:00Z), đóng góp +16.20 điểm."
  }
  ```
- **Quy tắc Bắt buộc `INCONCLUSIVE`:**
  - Nếu thiếu bất kỳ chuỗi dữ liệu bắt buộc nào (không đủ số nến warmup, thiếu sổ lệnh tính spread/thanh khoản, thiếu dữ liệu tính `Market Regime`, hoặc bất kỳ metric trọng yếu nào là `None`/`NaN`/`Inf`), hệ thống **bắt buộc dừng chấm điểm và trả về trạng thái `decision = "INCONCLUSIVE"`** kèm danh sách `missing_inputs` cụ thể. Tuyệt đối không tự điền `0` để tính tiếp.

## 4. Khối Kiểm định Độc lập (Phase P5 — Independent Verification)
Trước khi bất kỳ đề xuất nào từ `Crucible` được chuyển sang `Risk Controller` (P6), nó phải đi qua cổng kiểm định độc lập gồm 3 lớp:
1. **`Data Auditor`:** Xác minh lại tính toàn vẹn dữ liệu đầu vào (mốc thời gian nến đã đóng, không có khoảng trống thời gian bất thường, dữ liệu sổ lệnh không quá hạn, không chứa `NaN`/`Inf`).
2. **`Strategy Reviewer`:** Tính toán lại độc lập $S_{\text{Bull}}$, $S_{\text{Bear}}$, $M_{\text{regime}}$ và $S_{\text{net}}$ trực tiếp từ mảng `evidence` đã ghi nhận; kiểm tra tổng trọng số, kiểm tra mọi câu kết luận đều có `rule_id` hợp lệ. Nếu sai lệch số học `> 1e-9` -> đánh dấu `VERIFICATION_FAILED` và chặn ngay.
3. **`Test Engineer` (Runtime Contract Invariants):** Kiểm tra giới hạn biên của điểm số và đảm bảo đầu ra tuân thủ đúng JSON Schema chuẩn của `research_history.json`.

## 5. Bước Kiểm tra Xác thực (Validation Steps)
1. Unit test kiểm chứng tính tất định: gọi engine 10 lần trên cùng fixture cho kết quả byte-for-byte giống nhau.
2. Unit test thiếu dữ liệu (cắt ngắn nến, chèn `NaN`, bỏ trống orderbook) bắt buộc trả về `INCONCLUSIVE`.
3. Unit test cố tình làm lệch `S_net` so với tổng bằng chứng để xác minh `Strategy Reviewer` chặn thành công.
