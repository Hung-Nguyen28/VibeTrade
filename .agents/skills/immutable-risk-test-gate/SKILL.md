---
name: immutable-risk-test-gate
description: >-
  Enforces inviolable Risk Controller sovereignty, 3-timestamp execution integrity,
  schedule_drift_cost tracking, configurable $10 micro-portfolio constraints
  (REJECTED_BY_CONSTRAINT), realized vs unrealized PnL separation, and mandatory
  unit/regression test gates across Phases P1-P8.
---

# Immutable Risk Controller & Milestone Test Gate (`immutable-risk-test-gate`)

Quy chuẩn quản trị rủi ro bất khả xâm phạm, mô phỏng khớp lệnh trung thực trên vốn nhỏ `$10.0` (**Phase P6, P8**) và cổng kiểm thử bắt buộc cho mọi cột mốc (**P1–P7**).

## 1. Quyền Bất khả Xâm phạm của `Risk Controller`
- **Tách quyền Đọc/Ghi Tuyệt đối:**
  - `Research Engine` (`Analysts`, `Bull`, `Bear`, `Crucible`) chỉ được xuất ra đối tượng đề xuất chỉ-đọc (`TradeProposal` / `ResearchVerdict`) và **không có tham chiếu sửa đổi** tới cấu hình của `Risk Controller`.
  - Cấu hình `RiskConfig` phải được nạp thành đối tượng bất biến (`frozen=True`), niêm phong bằng mã băm SHA-256 (`config_hash`) ngay lúc khởi tạo chu kỳ và ghi kèm vào mỗi quyết định kiểm duyệt rủi ro.
  - Nếu phát hiện bất kỳ sai lệch `config_hash` hoặc nỗ lực ghi đè tham số rủi ro lúc runtime -> kích hoạt khóa an toàn (`RISK_TAMPER_HALT`) và từ chối toàn bộ lệnh.

## 2. Toàn vẹn Thời gian & Khớp lệnh (3-Timestamp Execution Integrity)
Mọi lệnh đề xuất và khớp lệnh mô phỏng phải lưu trữ tách biệt **3 mốc thời gian UTC**:
1. **`candle_close_time`:** Thời điểm đóng hoàn toàn của cây nến tạo ra tín hiệu.
2. **`signal_timestamp`:** Thời điểm Scanner / Crucible hoàn tất tính toán và phát ra tín hiệu.
3. **`execution_timestamp`:** Thời điểm bộ khớp lệnh Paper Trading thực sự thực hiện giao dịch mô phỏng.

### Quy tắc Giá Khớp Lệnh Bắt buộc:
- **Trong Chế độ Backtest (`mode = "backtest"`):**
  - Lấy giá `Open` của cây nến kế tiếp (`t + 1`, mở ngay sau `candle_close_time` của nến `t`) làm giá tham chiếu cơ sở, sau đó cộng độ trượt giá bất lợi (`spread + slippage`) và trừ phí giao dịch. **Cấm tuyệt đối** khớp lệnh ăn gian ngay tại giá `Close` của nến `t` mà bỏ qua độ trễ sang nến sau.
- **Trong Chế độ Live Paper Trading (`mode = "live_paper"` trên GitHub Actions):**
  - Do GitHub Actions cron có thể trễ vài phút so với `candle_close_time`, hệ thống **bắt buộc lấy dữ liệu giá/sổ lệnh thực tế của OKX ngay tại `execution_timestamp`** (mua tại `best_ask` + latency slippage, bán tại `best_bid` - latency slippage).
  - **Cấm tuyệt đối** quay ngược thời gian lấy giá lịch sử lúc `candle_close_time` để khớp lệnh!
  - **Ghi nhận Chi phí Trễ Lịch (`schedule_drift_cost`):**
    Tính và lưu tường minh độ lệch giữa giá lúc đóng nến (`price_at_candle_close`) và giá tham chiếu thực tế lúc khớp lệnh (`price_at_execution`):
    - `schedule_drift_ms = execution_timestamp - candle_close_time`
    - `schedule_drift_bps` và `schedule_drift_cost` (quy đổi ra USDT theo chiều lệnh: dương nếu trễ lịch làm giá mua đắt hơn / giá bán rẻ hơn, âm nếu có lợi ngẫu nhiên) để đánh giá trung thực tác động của hạ tầng miễn phí GitHub Actions ở Phase P8.

## 3. Cấu hình Chi phí & Ràng buộc Danh mục Vi mô `$10.0`
Mọi thông số chi phí và ràng buộc phải được cấu hình hóa tường minh (không hardcode rải rác), với bộ mặc định chuẩn cho VibeTrade v1.1:
```yaml
initial_balance: 10.0          # USDT
fee_rate: 0.001                # 0.10% mỗi chiều (mua và bán đều chịu phí)
slippage_model: spread_plus_latency
minimum_order_check: true
```
- **Kiểm tra Ràng buộc Sàn & Thanh khoản Thực tế:**
  Trước khi khớp lệnh, `Risk Controller` & `Paper Broker` phải kiểm tra tuần tự:
  1. Quy tắc cặp giao dịch trên OKX Spot: bước làm tròn khối lượng (`lotSz`), bước giá (`tickSz`), khối lượng đặt lệnh tối thiểu (`minSz`), và giá trị lệnh tối thiểu khả thi sau khi làm tròn xuống (`ROUND_DOWN`).
  2. Số dư tiền mặt khả dụng đủ trả cả giá trị lệnh lẫn phí mua (`notional + fee <= available_cash`).
  3. Ngưỡng chênh lệch `spread_bps <= max_allowed_spread_bps` và độ sâu sổ lệnh tại top-of-book đủ hấp thụ lệnh mà không vượt ngưỡng trượt giá tối đa.
  4. Giới hạn tỷ trọng tối đa trên một vị thế, tổng mức phơi nhiễm danh mục, và ngưỡng ngắt mạch sụt giảm vốn (`max_drawdown_halt`).
- **Trạng thái Bắt buộc `REJECTED_BY_CONSTRAINT`:**
  - Nếu lệnh vi phạm **bất kỳ** điều kiện nào ở trên (đặc biệt phổ biến với tài khoản `$10.0` khi chia nhỏ vốn gặp rào cản `minSz` của sàn), hệ thống **cấm tự động bỏ qua âm thầm** và **cấm tự ý nâng khối lượng vượt trần rủi ro**.
  - Bắt buộc ghi bản ghi đầy đủ vào nhật ký lệnh với `status = "REJECTED_BY_CONSTRAINT"`, mã quy tắc chặn (`constraint_code`, ví dụ `BELOW_OKX_MIN_SZ`, `SPREAD_TOO_WIDE`, `INSUFFICIENT_CASH_AFTER_FEE`, `MAX_POSITION_EXCEEDED`), và thông số thực tế lúc kiểm tra.

## 4. Kế toán PnL Tách biệt Hoàn toàn
- **`realized_pnl`:** Chỉ ghi nhận từ các phần vị thế đã đóng thực tế, đã khấu trừ đầy đủ phí chiều mở + phí chiều đóng + thực giá khớp (bao gồm spread/slippage).
- **`unrealized_pnl`:** Đánh giá lại theo giá thị trường hiện hành (`mark-to-market` tại `bid` cho vị thế Long Spot) của các vị thế đang mở trừ phí đóng ước tính; cập nhật mỗi chu kỳ quét nhưng tuyệt đối không cộng trộn vào `cash_balance` hay `realized_pnl`.
- Luôn kiểm tra bất biến kế toán sau mỗi chu kỳ:
  `total_equity == cash_balance + open_positions_net_liquidation_value`.

## 5. Cổng Kiểm thử Bắt buộc cho Mọi Milestone (P1–P7 Test Gate)
Mỗi phase từ **P1 đến P7** chỉ được coi là hoàn thành khi có đủ cả 2 lớp kiểm thử tự động chạy xanh:
1. **Unit Tests của Phase hiện tại:** Bao phủ logic cốt lõi, các biên toán học, trạng thái lỗi (`INCONCLUSIVE`, `REJECTED_BY_CONSTRAINT`), bất biến kế toán và tính tất định.
2. **Regression Test Suite Lũy kế:** Chạy lại toàn bộ test của các phase trước đó để đảm bảo nâng cấp ở phase sau không làm gãy hợp đồng dữ liệu hoặc làm suy yếu hàng rào rủi ro đã khóa.
