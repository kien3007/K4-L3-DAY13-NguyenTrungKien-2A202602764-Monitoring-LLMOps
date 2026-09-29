# Alert Rules và Runbooks

Mỗi alert phải dựa trên triệu chứng người dùng hoặc SLO, không dựa trực tiếp vào tên implementation nội bộ.

## Alert 1 {#alert-1}

- **Tên:** HighLatencyDegradation
- **Severity:** warning
- **Duration:** 5m
- **Kênh thông báo:** Slack `#llmops-alerts`
- **SLI/SLO liên quan:** Primary SLO `fast_successful_requests` (latency_ms <= 3000ms)
- **Điều kiện và thời gian duy trì:** `p95(latency_ms) > 3000ms` kéo dài liên tục trên 5 phút
- **Ảnh hưởng tới người dùng:** Người dùng bị chậm khi nhận phản hồi câu hỏi, thời gian phản hồi vượt quá 3 giây gây suy giảm trải nghiệm hội thoại.
- **Ba bước kiểm tra đầu tiên:**
  1. Kiểm tra panel **Latency** trên dashboard để xem TTFT có tăng hay chỉ tổng latency tăng.
  2. Lọc `data/logs.jsonl` tìm các request có `latency_ms > 3000`, trích xuất `correlation_id`.
  3. Mở Langfuse trace tương ứng với `correlation_id` để phân biệt span chậm nằm ở bước `retrieval` hay `generation`.
- **Mitigation tạm thời:** Nếu bước retrieval chậm, bật cache tạm thời hoặc giảm số lượng tài liệu `top_k`. Nếu LLM chậm, hạ nhiệt độ / max tokens hoặc fallback sang model nhẹ hơn.
- **Owner:** NguyenTrungKien

---

## Alert 2 {#alert-2}

- **Tên:** ElevatedErrorRate
- **Severity:** critical
- **Duration:** 2m
- **Kênh thông báo:** Slack `#llmops-critical`
- **SLI/SLO liên quan:** Guardrail `error_rate_pct_max <= 2.0%`
- **Điều kiện và thời gian duy trì:** `error_rate_pct > 2.0%` kéo dài liên tục trên 2 phút
- **Ảnh hưởng tới người dùng:** Người dùng gặp lỗi 5xx hoặc thông báo hệ thống không thể xử lý yêu cầu, nguy cơ cạn kiệt error budget nhanh chóng.
- **Ba bước kiểm tra đầu tiên:**
  1. Xem panel **Errors** trên dashboard để xác định loại lỗi (`error_type`) chủ yếu (ví dụ `RuntimeError`, `Timeout`, `RateLimit`).
  2. Tra cứu correlation ID của các sự kiện `request_failed` trong `data/logs.jsonl`.
  3. Xem trace trên Langfuse để xác định span bị lỗi (bước retriever kết nối vector store hay generation gọi LLM).
- **Mitigation tạm thời:** Bật chế độ degraded/fallback answer để trả lời câu hỏi cơ bản, cô lập service lỗi hoặc restart container/pod nếu bị treo kết nối.
- **Owner:** NguyenTrungKien

---

## Alert 3 {#alert-3}

- **Tên:** RetrievalSuccessDrop
- **Severity:** warning
- **Duration:** 5m
- **Kênh thông báo:** Slack `#llmops-alerts`
- **SLI/SLO liên quan:** Guardrail `retrieval_success_rate_pct_min >= 90.0%`
- **Điều kiện và thời gian duy trì:** `retrieval_success_rate_pct < 90.0%` kéo dài liên tục trên 5 phút
- **Ảnh hưởng tới người dùng:** Câu trả lời của bot không có ngữ cảnh domain chính xác, chất lượng câu trả lời bị suy giảm (`quality_score` giảm).
- **Ba bước kiểm tra đầu tiên:**
  1. Kiểm tra panel **Errors & Retrieval Success** trên dashboard để đánh giá mức độ sụt giảm tỷ lệ retrieval.
  2. Lọc log sự kiện `tool_success == false` hoặc `tool_name == "retrieval"` trong `data/logs.jsonl`.
  3. Mở trace trên Langfuse xem observation `retrieval` có lỗi timeout, empty result hay lỗi phân tích vector.
- **Mitigation tạm thời:** Chuyển sang fallback corpus tĩnh cục bộ, kích hoạt fallback prompt hoặc cấu hình lại ngưỡng matching score.
- **Owner:** NguyenTrungKien
