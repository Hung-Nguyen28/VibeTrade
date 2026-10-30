---
name: code-review-and-quality
description: >-
  Provides a rigorous code review checklist and quality gate runbook for VibeTrade v1.1.
  Activate this skill before completing any phase milestone, reviewing diffs, or
  validating quantitative, risk, persistence, and UI changes.
---

# Code Review & Quality Gate (`code-review-and-quality`)

Quy trình rà soát chất lượng mã nguồn bắt buộc trước khi nghiệm thu bất kỳ task hoặc phase nào của **VibeTrade v1.1**.

## 1. Cổng Kiểm duyệt Kiến trúc & Ngân sách $0
- [ ] **Zero Paid API Check:** Không có import, khởi tạo client, hay lời gọi mạng nào tới LLM trả phí (`openai`, `anthropic`, `deepseek`, `openrouter`, v.v.) hoặc nguồn dữ liệu trả phí trong đường chạy của VibeTrade v1.1.
- [ ] **No Fake LLM Check:** Văn bản giải thích trong Research Room được sinh từ **Evidence-based Templates** gắn chặt với `{metric, value, timestamp, rule_id}`, tuyệt đối không dùng câu chữ phỏng đoán mơ hồ.
- [ ] **Surgical Scope Check:** Diff chỉ chạm đúng các file thuộc diện `ADAPT` / `REPLACE` / `REMOVE` của phase hiện tại; giữ nguyên docstring và comment không liên quan.

## 2. Cổng Kiểm duyệt Định lượng & Rủi ro
- [ ] **Bar-Close & Anti-Lookahead:** Chỉ dùng nến đã đóng (`candle_close_time <= current_time`); không có `.shift(-k)` âm, `center=True`, hoặc chuẩn hóa toàn chuỗi gây rò rỉ tương lai.
- [ ] **Idempotency:** Khóa `symbol + timeframe + candle_timestamp` được kiểm tra trước khi sinh sự kiện hoặc chạy Focus Session.
- [ ] **Edge-Case Math:** Mọi phép chia đều có bảo vệ mẫu số bằng `0`; dữ liệu thiếu/NaN trả về `INCONCLUSIVE` thay vì giá trị mặc định ngầm (`0.0`).
- [ ] **Execution & PnL Integrity:**
  - Phân tách rõ `candle_close_time`, `signal_timestamp`, `execution_timestamp` và ghi nhận `schedule_drift_cost`.
  - Tách biệt `realized_pnl` và `unrealized_pnl`; kiểm tra đẳng thức kế toán vốn ảo `$10.0`.
  - Lệnh vi phạm ràng buộc sàn/rủi ro được ghi log `REJECTED_BY_CONSTRAINT`.
  - `Risk Controller` không thể bị sửa đổi bởi Research Engine.

## 3. Cổng Kiểm duyệt Trạng thái & Vận hành
- [ ] **Atomic Persistence:** Mọi thao tác ghi JSON trạng thái đều ghi qua `.tmp`, kiểm tra schema hợp lệ rồi mới `os.replace()`.
- [ ] **Git Hygiene:** Không để lọt file tạm, cache, `.env`, hoặc dữ liệu runtime chưa chuẩn hóa vào nhánh `main`.

## 4. Lệnh Kiểm tra Tự động (Validation Steps)
1. Kiểm tra khoảng trắng thừa và xung đột Git:
   `git diff --check`
2. Kiểm tra danh sách file bị thay đổi ngoài ý muốn:
   `git status --short --branch`
3. Chạy linter và bộ unit + regression test của các phase từ P1 đến phase hiện tại:
   `ruff check agent && pytest -m "not integration and not slow" --tb=short -q`
4. Nếu có thay đổi `frontend/`:
   `cd frontend && npm run test:run && npm run build`
