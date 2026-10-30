---
name: atomic-state-persistence
description: >-
  Governs Phases P6 and P7 state persistence, branch isolation (main vs data-state),
  GitHub Actions concurrency locking, atomic JSON writes (.tmp + schema validation +
  os.replace), smart diff commits, and bounded log rotation.
---

# Atomic State Persistence & Two-Branch Ops (`atomic-state-persistence`)

Quy chuẩn lưu trữ trạng thái bền vững chi phí `$0` phục vụ **Phase P6** và **Phase P7** trên GitHub Actions & GitHub Pages.

## 1. Kiến trúc Tách biệt 2 Nhánh Git (`main` vs `data-state`)

Tuyệt đối không trộn lẫn lịch sử commit mã nguồn với dữ liệu quét định kỳ 15 phút:

| Nhánh | Nội dung Lưu trữ | Quyền Ghi |
| :--- | :--- | :--- |
| **`main`** | Mã nguồn Python (`agent/`), giao diện (`frontend/`), JSON Schemas (`schema/`), bộ kiểm thử (`agent/tests/`), cấu hình Skills/Rules (`.agents/`, `GEMINI.md`), và GitHub Actions (`.github/workflows/`). | Chỉ cập nhật khi phát triển tính năng/sửa lỗi. Jobs chạy định kỳ **cấm** commit vào `main`. |
| **`data-state`** | Chỉ chứa 5 file trạng thái JSON chuẩn (cùng thư mục con archive có kiểm soát nếu cấu hình):<br>1. `market_snapshot.json`<br>2. `opportunity_queue.json`<br>3. `paper_portfolio.json`<br>4. `research_history.json`<br>5. `heartbeat.json` | Chỉ được cập nhật tự động bởi workflow chu kỳ đã giữ khóa `concurrency`. |

## 2. Giao thức Ghi File Nguyên tử (Atomic Write Protocol)
Mọi thao tác cập nhật bất kỳ file JSON nào trong 5 file trạng thái chuẩn **bắt buộc** đi qua hàm ghi nguyên tử 5 bước:
1. **Chuẩn hóa & Kiểm tra Schema trên Bộ nhớ:** Xác thực dữ liệu qua Pydantic model / JSON Schema tương ứng (`schema_version` tường minh, không có `NaN`/`Infinity` ngoài chuẩn JSON RFC 8259 — dùng `allow_nan=False` trong `json.dumps`).
2. **Ghi ra File Tạm cùng Thư mục (`.tmp`):** Ghi nội dung UTF-8 (`indent=2`, `sort_keys=True` hoặc thứ tự trường cố định) vào `<target_dir>/<filename>.json.tmp` (cùng filesystem để đảm bảo phép đổi tên là nguyên tử trên cả POSIX và Windows).
3. **Đẩy xuống Đĩa (`flush` + `os.fsync`):** Gọi `f.flush()` và `os.fsync(f.fileno())` trước khi đóng file tạm.
4. **Đọc Thử & Xác thực Lại File `.tmp`:** Parse lại JSON từ file `.tmp` để chắc chắn không bị cắt cụt giữa chừng.
5. **Hoán đổi Nguyên tử bằng `os.replace()`:** Gọi `os.replace(tmp_path, final_path)`. Nếu xảy ra bất kỳ lỗi nào ở bước 1–4, xóa `.tmp` trong khối `finally` và giữ nguyên trạng thái hợp lệ trước đó.

## 3. Khóa Đồng thời trên GitHub Actions (`concurrency`)
Mọi workflow đọc-sửa-ghi nhánh `data-state` bắt buộc khai báo khóa đồng thời cấp workflow để không bao giờ xảy ra xung đột `non-fast-forward` hoặc ghi đè chéo giữa job lịch trình (`schedule`) và job chạy tay (`workflow_dispatch`):

```yaml
concurrency:
  group: vibetrade-data-state-writer
  cancel-in-progress: false
```

- Đặt `cancel-in-progress: false` để chu kỳ đang chạy hoàn tất trọn vẹn bước khớp lệnh ảo và ghi sổ cái thay vì bị giết ngang.
- Khi push lên `data-state`, luôn `git fetch origin data-state` ở đầu bước hoặc checkout worktree riêng (`_data_state/`) để đọc trạng thái mới nhất trước khi chạy chu kỳ.

## 4. Smart Commit & Giới hạn Dung lượng Lịch sử (Rotation)
- **Smart Commit (Chống Commit Rác):**
  - Tách bạch các trường thay đổi thực chất (tín hiệu mới, khớp lệnh mới, thay đổi danh mục, thay đổi snapshot nến mới đã đóng) với dấu thời gian kiểm tra thuần túy.
  - Chỉ thực hiện `git commit` và `git push origin data-state` khi nội dung trạng thái thực sự thay đổi theo chính sách commit đã cấu hình (`git status --porcelain` trên worktree `data-state` khác rỗng).
- **Bounded Rolling Windows (Chống Phình Repo):**
  - Áp đặt giới hạn số lượng phần tử tối đa (FIFO / Ring Buffer) cho từng file JSON:
    - `research_history.json`: giữ tối đa `N` phiên phân tích gần nhất (ví dụ `200` bản ghi).
    - `opportunity_queue.json`: giữ các cơ hội đang hoạt động + tối đa `M` cơ hội đã đóng/hết hạn gần nhất (ví dụ `100` bản ghi).
    - `paper_portfolio.json`: giữ toàn bộ vị thế đang mở, số liệu tổng hợp lũy kế trọn đời (`cumulative_realized_pnl`, `total_trades`, `rejected_count`), đường cong vốn rút gọn theo mốc đóng nến, và cửa sổ `K` giao dịch gần nhất (ví dụ `500` bản ghi).
  - Định kỳ kiểm tra kích thước từng file JSON (mục tiêu mỗi file `< 1 MB`) để Dashboard trên GitHub Pages luôn tải tức thì dưới 1 giây.

## 5. Bước Kiểm tra Xác thực (Validation Steps)
1. Unit test mô phỏng lỗi ngoại lệ ngay giữa quá trình ghi (ví dụ dữ liệu chứa `float('nan')` hoặc lỗi schema): xác nhận file chính cũ vẫn còn nguyên vẹn 100% và không còn file `.tmp` mồ côi.
2. Unit test kiểm tra cơ chế cắt ngọn (FIFO rotation) khi số bản ghi vượt ngưỡng cấu hình.
3. Kiểm tra tĩnh file workflow GitHub Actions có khai báo đúng `concurrency` và tách biệt nhánh `data-state`.
