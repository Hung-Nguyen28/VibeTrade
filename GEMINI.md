# VibeTrade v1.1 — Workspace Governance & Core Rules

Dự án **VibeTrade v1.1** (*Personal Autonomous Crypto Intelligence System*) được phát triển bằng phương pháp kế thừa và phẫu thuật có chọn lọc (*Surgical Refactor*) từ `HKUDS/Vibe-Trading` với ngân sách vận hành **$0 tuyệt đối**.

## 1. Bất biến kiến trúc ($0 Budget & Autonomous Integrity)

1. **$0 Tuyệt đối — Không LLM trả phí:**
   - Cấm gọi mọi API LLM thương mại hoặc cần API key trả phí (`OpenAI`, `Anthropic`, `DeepSeek`, `OpenRouter`, `Copilot`, v.v.) trong toàn bộ luồng vận hành của VibeTrade v1.1.
   - Không giả vờ làm LLM (không sinh hội thoại đóng vai ngẫu nhiên). Toàn bộ khối phân tích hoạt động như một **Explainable Quantitative System** (Weighted Scoring Engine + Evidence-based Templates).
2. **Nguồn dữ liệu duy nhất — OKX Public API:**
   - Ưu tiên cặp giao dịch **USDT Spot** (`*-USDT`) qua OKX Public REST v5 không cần API key.
   - Tuân thủ nghiêm ngặt **Bar-Close Confirmation** (`candle_close_time <= current_time`, không dùng nến đang chạy) và **Anti-Lookahead Bias** (cấm đọc dữ liệu tương lai).
3. **Không đập đi xây lại (No Full Rewrite):**
   - Mọi thay đổi trên mã nguồn gốc phải dựa trên phân loại kiểm toán 4 nhãn của `P0_AUDIT_REPORT.md`: `KEEP`, `ADAPT`, `REPLACE`, `REMOVE`.
   - Bảo toàn docstring, comment và interface hợp lệ khi chỉ thay ruột (`REPLACE`) hoặc điều chỉnh logic (`ADAPT`).
4. **Quyền bất khả xâm phạm của Risk Controller & Paper Trading $10:**
   - Khối nghiên cứu (`Analysts`, `Bull`, `Bear`, `Crucible`) không có quyền ghi hoặc ghi đè cấu hình của `Risk Controller`.
   - Tách biệt 3 mốc thời gian: `candle_close_time`, `signal_timestamp`, `execution_timestamp` (ghi nhận `schedule_drift_cost` khi chạy trên GitHub Actions).
   - Kiểm tra đầy đủ phí (`fee_rate: 0.001`), `spread_plus_latency` slippage, precision và minimum order size trên vốn ảo `$10.0`; từ chối minh bạch bằng trạng thái `REJECTED_BY_CONSTRAINT`, không bao giờ âm thầm bỏ qua.
   - Tách biệt hoàn toàn `realized_pnl` và `unrealized_pnl`.
5. **Tách nhánh & Ghi trạng thái nguyên tử (Atomic Persistence):**
   - Nhánh `main` chỉ chứa mã nguồn, frontend, schema, tests và GitHub Actions workflows.
   - Nhánh `data-state` chứa 5 snapshot JSON chuẩn (`market_snapshot.json`, `opportunity_queue.json`, `paper_portfolio.json`, `research_history.json`, `heartbeat.json`), luôn ghi qua `.tmp` + kiểm tra schema + `os.replace()`.

## 2. Bản đồ Skills trong Workspace (`.agents/skills/`)

Kích hoạt và đọc `SKILL.md` tương ứng trước khi thực thi từng tác vụ:

| Phân nhóm | Skill | Mục đích & Phase áp dụng |
| :--- | :--- | :--- |
| **Custom (P0)** | `codebase-surgical-auditor` | Kiểm toán Read-Only, phân loại `KEEP`/`ADAPT`/`REPLACE`/`REMOVE` có trích dẫn file & hàm/class. |
| **Custom (P1–P3)** | `quant-data-guard` | OKX Public API (USDT Spot), Bar-Close confirmation, Anti-Lookahead Bias, Idempotency `signal_id`. |
| **Custom (P4–P5)** | `deterministic-personas-engine` | Weighted Scoring (`Bull`/`Bear`/`Crucible`), Evidence Binding, `INCONCLUSIVE`, Independent Verification. |
| **Custom (P6–P7)** | `atomic-state-persistence` | Tách nhánh `main`/`data-state`, khóa `concurrency`, ghi `.tmp` + `os.replace()`, smart commit & log rotation. |
| **Custom (P6, P8)** | `immutable-risk-test-gate` | Bất khả xâm phạm Risk Controller, 3 mốc thời gian, `schedule_drift_cost`, `$10` constraints, test gates P1–P7. |
| **Standard** | `python-dev` | Chuẩn code Python >=3.11, typing/Pydantic, UTC timestamps, số học định lượng an toàn, `pytest` & `ruff`. |
| **Standard** | `webapp-testing` | Kiểm thử Dashboard React 19 + Vite + Vitest với static JSON snapshots, trạng thái lỗi/rỗng/trễ nhịp. |
| **Standard** | `code-review-and-quality` | Checklist review code, kiểm tra rò rỉ chi phí API, sai lệch định lượng, độ phủ unit/regression test. |
| **Standard** | `security` | Zero-secret architecture, khóa quyền GitHub Actions, fail-closed chặn live order, chống XSS trên GitHub Pages. |
| **Standard** | `frontend-design` | Thiết kế UI/UX chuẩn Quant Terminal cho 7 màn hình Dashboard tĩnh trên GitHub Pages. |
