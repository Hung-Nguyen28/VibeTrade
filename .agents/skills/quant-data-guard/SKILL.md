---
name: quant-data-guard
description: >-
  Enforces quantitative data integrity across Phases P1, P2, and P3 (OKX Public API
  Data Layer, Market Scanner, and Hybrid Event Engine). Mandates USDT Spot priority,
  strict Bar-Close Confirmation, Anti-Lookahead Bias, and deterministic signal idempotency.
---

# Quantitative Data & Signal Guard (`quant-data-guard`)

Bộ quy tắc bảo vệ toàn vẹn dữ liệu thị trường và chống sai lệch định lượng cho **Phase P1 (OKX Data Layer)**, **Phase P2 (Market Scanner)** và **Phase P3 (Hybrid Event Engine)**.

## 1. Chuẩn Nguồn Dữ liệu: OKX Public API v5 ($0 & Zero-Key)
- **Ưu tiên Tuyệt đối USDT Spot (`instType=SPOT`, hậu tố `-USDT`):**
  - Toàn bộ danh sách cặp theo dõi phải là cặp giao dịch giao ngay định giá bằng `USDT` (ví dụ: `BTC-USDT`, `ETH-USDT`, `SOL-USDT`), loại bỏ cặp đòn bẩy/phái sinh, stablecoin-to-stablecoin (`USDC-USDT`, `FDUSD-USDT`) trừ khi dùng làm chỉ báo cấu trúc riêng.
- **Các Endpoint Public Chuẩn (Không dùng API Key):**
  - Danh mục & quy tắc bước lệnh (`tickSz`, `lotSz`, `minSz`, `state=="live"`): `GET /api/v5/public/instruments?instType=SPOT`
  - Quét nhanh toàn thị trường (Surveillance Mode): `GET /api/v5/market/tickers?instType=SPOT`
  - Dữ liệu nến lịch sử & xác nhận đóng nến: `GET /api/v5/market/candles` và `GET /api/v5/market/history-candles`
  - Độ sâu thanh khoản & chênh lệch giá mua/bán thực tế: `GET /api/v5/market/books?instId=<SYMBOL>&sz=20`
- **Chuẩn hóa Schema Đầu ra:**
  - Ép kiểu tường minh từ chuỗi của OKX sang số thực/Decimal hợp lệ; kiểm tra `high >= max(open, close) >= min(open, close) >= low > 0` và `vol_base >= 0`, `vol_quote >= 0`.
  - Mọi mốc thời gian chuẩn hóa về **UTC epoch milliseconds (`int`)**, sắp xếp tăng dần nghiêm ngặt (`ts[i] < ts[i+1]`).

## 2. Xác nhận Đóng Nến Nghiêm ngặt (Bar-Close Confirmation)
- **Cấm tuyệt đối tính tín hiệu trên nến đang chạy (Zero Repainting):**
  - Với mỗi cây nến có thời điểm mở `candle_open_time` và khung thời gian `bar_duration_ms`, thời điểm đóng nến là `candle_close_time = candle_open_time + bar_duration_ms`.
  - Một cây nến **chỉ được phép** đưa vào tính indicator và phát tín hiệu khi thỏa đồng thời:
    1. `candle_close_time <= current_utc_ms`
    2. Cờ xác nhận từ OKX `confirm == "1"` (nếu lấy từ `/api/v5/market/candles`, phần tử có `confirm == "0"` là nến chưa đóng — **bắt buộc loại bỏ ngay ở tầng parser**).
- Nếu sau khi lọc bỏ nến chưa đóng mà số lượng nến hợp lệ nhỏ hơn `min_warmup_bars` của chỉ báo (ví dụ `< 200` nến cho EMA200 hoặc `< 30` nến cho ATR/ADX), trả về trạng thái thiếu dữ liệu (`INCONCLUSIVE`), không tính ép.

## 3. Chống Rò rỉ Tương lai (Anti-Lookahead Bias)
- **Trong mọi hàm tính Indicator, Factor và Scanner:**
  - Cấm truy cập phần tử tương lai `i + k` (`k > 0`), cấm dùng `Series.shift(-k)` với số âm, cấm `rolling(..., center=True)`.
  - Cấm chuẩn hóa Z-score / Min-Max / Percentile bằng thống kê toàn chuỗi (`df.mean()`, `df.std()`); bắt buộc dùng cửa sổ trượt nhân quả (`rolling(window)` chỉ nhìn về quá khứ `<= t`).
  - Khi gộp đa khung thời gian (ví dụ ghép xu hướng `4H` vào tín hiệu `15m`), chỉ được join với cây nến `4H` gần nhất có `4h_candle_close_time <= 15m_candle_close_time` (`merge_asof(..., direction="backward")`).
- **Bài kiểm tra Bất biến Cắt cụt (Truncation Invariance Test bắt buộc):**
  - Với mọi hàm chỉ báo `F(df)` và mọi thời điểm `t` đủ warmup:
    `F(df.iloc[:t]).iloc[-1]` **phải bằng chính xác** `F(df).iloc[t - 1]` (sai số tuyệt đối `< 1e-12`).

## 4. Tính Lũy đẳng & Chống Xử lý Trùng lặp (Idempotency)
- **Định danh Tín hiệu Duy nhất (`signal_id`):**
  - Mọi sự kiện bất thường từ Market Scanner (P2) và tín hiệu kích hoạt Focus Session (P3) bắt buộc mang khóa chuẩn:
    `signal_id = f"{symbol}:{timeframe}:{candle_close_time}"`
    *(Ví dụ: `SOL-USDT:15m:1730268900000`)*.
- **Cơ chế Chống Trùng lặp (Deduplication Gate):**
  - Trước khi đưa tín hiệu vào `opportunity_queue.json` hoặc kích hoạt Research Team (P4), Hybrid Event Engine phải đối chiếu `signal_id` với tập `processed_signal_ids` đã lưu.
  - Nếu `signal_id` đã tồn tại (do job quét lại hoặc nến cũ chưa có nến mới đóng thêm), hệ thống bỏ qua an toàn và ghi nhận `skipped_duplicate_count` vào metrics của chu kỳ quét.

## 5. Bước Kiểm tra Xác thực (Validation Steps)
1. Viết và chạy unit test kiểm chứng parser tự động loại bỏ nến `confirm == "0"` và nến có `candle_close_time > current_time`.
2. Viết và chạy Truncation Invariance Test cho toàn bộ chỉ báo/bộ lọc mới.
3. Viết và chạy Idempotency Test: nạp cùng một chuỗi nến 2 lần liên tiếp phải cho ra đúng 0 tín hiệu mới ở lần quét thứ 2.
