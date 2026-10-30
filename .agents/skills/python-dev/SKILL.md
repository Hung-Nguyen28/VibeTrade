---
name: python-dev
description: >-
  Enforces Python >=3.11 engineering standards for VibeTrade v1.1 backend modules,
  data pipelines, scoring engines, and paper trading logic. Activate this skill when
  writing, refactoring, or debugging Python code under agent/ or scripts/.
---

# Python Development Standard (`python-dev`)

Hướng dẫn kỹ thuật chuẩn cho phát triển Python (`>=3.11`) trong dự án **VibeTrade v1.1**.

## 1. Kiến trúc Module & Surgical Refactoring
- **Tôn trọng cấu trúc gói hiện hữu:** Mã nguồn Python đặt dưới `agent/` (`pythonpath = ["agent"]` theo `pyproject.toml`).
- **Bảo toàn hợp đồng (Interface Preservation):** Khi thực hiện `ADAPT` hoặc `REPLACE` một module, giữ nguyên chữ ký hàm/class hoặc kiểu dữ liệu đầu ra nếu các module `KEEP` phía sau đang phụ thuộc vào nó.
- **Bảo toàn tài liệu:** Giữ nguyên toàn bộ docstring và comment hợp lệ không liên quan đến phần code thay đổi.
- **Không kéo thêm thư viện tốn phí hoặc nặng nề:** Tận dụng tối đa stdlib, `httpx`/`requests`, `pandas`, `numpy`, `pydantic>=2.0` đã có sẵn trong `pyproject.toml`.

## 2. Kiểu dữ liệu, Schema & Tính tất định (Determinism)
- **Explicit Type Hints:** Mọi hàm public bắt buộc khai báo đầy đủ kiểu tham số và kiểu trả về (`from __future__ import annotations`).
- **Immutability cho Cấu hình & Kết quả:** Sử dụng `@dataclass(frozen=True)` hoặc `pydantic.BaseModel` (`ConfigDict(frozen=True, extra="forbid")`) cho cấu hình rủi ro, snapshot thị trường, tín hiệu và kết quả chấm điểm.
- **Không dùng tính ngẫu nhiên không kiểm soát:** Cấm dùng `random` trong pipeline chấm điểm hoặc khớp lệnh mô phỏng. Thứ tự duyệt dictionary/list khi xuất JSON phải cố định để hash trạng thái ổn định.

## 3. Xử lý Thời gian & Số học Tài chính
- **UTC Tuyệt đối:** Mọi đối tượng `datetime` phải có `tzinfo=timezone.utc` (dùng `datetime.now(timezone.utc)` thay vì `datetime.utcnow()` hoặc giờ local). Khi chuẩn hóa sang số nguyên, thống nhất dùng **epoch milliseconds (`int`)** khớp với chuẩn OKX v5.
- **An toàn số thực & làm tròn theo sàn:**
  - Luôn kiểm tra `math.isfinite(val)` và `not pd.isna(val)` trước khi đưa metric vào tính điểm hoặc khớp lệnh.
  - Khi kiểm tra `lotSz` (bước khối lượng) và `tickSz` (bước giá) trên vốn nhỏ (`$10.0`), dùng `decimal.Decimal` với `ROUND_DOWN` cho khối lượng đặt lệnh để không bao giờ vượt số dư khả dụng do sai số dấu phẩy động.

## 4. Mạng, Lỗi & Logging
- **HTTP Discipline:** Mọi request tới OKX Public API phải đặt `timeout` tường minh (ví dụ `connect=5.0, read=10.0`), retry có giới hạn kèm exponential backoff cho lỗi `429`/`5xx`, và không bao giờ nuốt ngoại lệ bằng `except Exception: pass`.
- **Fail-Closed & Rõ trạng thái:** Dữ liệu lỗi hoặc thiếu phải chuyển hóa thành trạng thái tường minh (`INCONCLUSIVE`, `REJECTED_BY_CONSTRAINT`, hoặc mã lỗi trong `heartbeat.json`), kèm structured logging dễ truy vết.

## 5. Quy trình Kiểm tra Chất lượng (Validation Steps)
Chạy các bước kiểm tra sau sau mỗi thay đổi Python:
1. Kiểm tra cú pháp nhanh:
   `python -m py_compile <danh_sach_file_vua_sua>`
2. Kiểm tra lint theo cấu hình repo (`line-length = 120`, `target-version = "py311"`):
   `ruff check <danh_sach_file_vua_sua>`
3. Chạy unit test cô lập mạng:
   `pytest -m "not integration and not slow" <file_test_muc_tieu> --tb=short -q`
