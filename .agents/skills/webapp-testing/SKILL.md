---
name: webapp-testing
description: >-
  Guides automated testing and build verification for the VibeTrade v1.1 React,
  TypeScript, and Vite dashboard hosted on GitHub Pages. Activate this skill when
  writing frontend tests, validating JSON snapshot rendering, or checking UI states.
---

# Web Application Testing (`webapp-testing`)

Quy trình kiểm thử giao diện Dashboard tĩnh **VibeTrade v1.1** (`frontend/` — React 19, TypeScript 5.7, Vite 8, Vitest 5, Testing Library).

## 1. Nguyên tắc Kiểm thử Static-First ($0 GitHub Pages)
- Dashboard trên GitHub Pages hoạt động hoàn toàn bằng cách đọc 5 snapshot JSON tĩnh từ nhánh `data-state` (hoặc thư mục dữ liệu tĩnh được cấu hình) thay vì phụ thuộc vào backend FastAPI/WebSocket chạy 24/7.
- Mọi bài kiểm thử frontend phải chạy **offline 100%**, sử dụng mock `fetch` và bộ fixture JSON chuẩn khớp 1:1 với schema của nhánh `data-state`.

## 2. Ma trận Trạng thái Bắt buộc Kiểm thử (4-State Coverage)
Với mỗi màn hình trong 7 màn hình (`Overview`, `Market Scanner`, `Opportunity Queue`, `AI Research Room`, `Paper Portfolio`, `Performance`, `System Monitor`), đảm bảo kiểm thử đủ 4 kịch bản dữ liệu:
1. **Happy Path (Nominal Snapshot):** Hiển thị chính xác giá, phần trăm thay đổi, điểm `S_Bull` / `S_Bear` / `S_net`, bằng chứng định lượng, `realized_pnl` tách biệt khỏi `unrealized_pnl`, và chi phí `schedule_drift_cost`.
2. **Domain Edge States:**
   - Bản ghi nghiên cứu trả về `INCONCLUSIVE` (thiếu dữ liệu đầu vào) hiển thị cảnh báo rõ ràng, không crash biểu đồ hay bảng điểm.
   - Lệnh mô phỏng bị từ chối với trạng thái `REJECTED_BY_CONSTRAINT` hiển thị đầy đủ lý do từ chối (ví dụ: không đạt `minSz` trên vốn `$10.0`, spread vượt ngưỡng).
3. **Stale Heartbeat / Degraded Pipeline:** Khi `heartbeat.json` báo lần chạy gần nhất quá hạn (ví dụ `> 30` phút so với lịch 15 phút) hoặc job gần nhất lỗi, banner cảnh báo độ trễ dữ liệu phải kích hoạt rõ ràng.
4. **Empty / Initial Bootstrap State:** Khi danh mục mới khởi tạo (`$10.0` tiền mặt, `0` vị thế, lịch sử rỗng) hoặc lỗi tải JSON (`404` / malformed JSON), UI phải render Empty State / Error Boundary thân thiện thay vì màn hình trắng.

## 3. Chuẩn viết Test với Vitest & Testing Library
- Ưu tiên truy vấn theo ngữ nghĩa người dùng (`getByRole`, `getByText`, `getByLabelText`) thay vì phụ thuộc class CSS nội bộ.
- Mock ECharts hoặc kiểm tra props dữ liệu truyền vào wrapper chart để tránh lỗi canvas trong môi trường `jsdom`.
- Kiểm thử định dạng số học: số tiền nhỏ quanh `$10.00`, phí `0.1%` (`$0.01`–`$0.001`), và giá token nhiều chữ số thập phân không bị làm tròn thành `$0.00` gây hiểu nhầm.

## 4. Lệnh Xác thực Bắt buộc (Validation Steps)
Chạy tuần tự trong thư mục `frontend/`:
1. Chạy toàn bộ unit/component test một lần (không treo watch mode):
   `npm run test:run`
2. Kiểm tra kiểu TypeScript nghiêm ngặt và đóng gói production bundle cho GitHub Pages:
   `npm run build`
3. Đảm bảo bundle xuất ra trong `frontend/dist/` dùng đường dẫn tương đối (`base` hợp lệ cho GitHub Pages subpath `/<repo-name>/`) và không gọi cứng `http://localhost:8000` ở chế độ production.
