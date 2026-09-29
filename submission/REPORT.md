# Báo cáo cá nhân — K4-L3A Day 13 Monitoring & LLMOps

> Mỗi học viên hoàn thiện một file duy nhất này. Khi dẫn evidence, dùng đường dẫn tương đối, ví dụ `evidence/07-trace-waterfall.png`.

## 1. Thông tin học viên

- **Họ và tên:** Nguyễn Trung Kiên
- **MSSV:** 2A202602764
- **Lớp:** K4-L3A
- **Repository URL:** https://github.com/kien3007/K4-L3-DAY13-NguyenTrungKien-2A202602764-Monitoring-LLMOps
- **Commit SHA cuối:** 0baae105a3aff4ff6da1d74d3a1419f5e07cc8b2
- **Challenge ID:** day13-k4-l3a-monitoring-llmops-v1
- **Tên project Langfuse cá nhân:** `day13-k4-l3a-2A202602764`

## 2. Evidence index

Điền đúng đường dẫn tới evidence thực tế. Có thể đổi tên hoặc dùng nhiều ảnh nếu cần.

| Evidence | Đường dẫn |
|---|---|
| Pytest cuối | `evidence/01-pytest.png` |
| Log validator | `evidence/02-log-validator.png` |
| Dashboard validator | `evidence/03-dashboard-validator.png` |
| Structured log | `evidence/04-structured-log.png` |
| PII redaction | `evidence/05-pii-redaction.png` |
| Trace list | `evidence/06-trace-list.png` |
| Trace waterfall | `evidence/07-trace-waterfall.png` |
| Trace metadata | `evidence/08-trace-metadata.png` |
| Prompt versions | `evidence/09-prompt-versions.png` |
| Prompt rollback | `evidence/10-prompt-rollback.png` |
| Dashboard runtime | `evidence/11-dashboard-overview.png` |
| Incident metric | `evidence/12-incident-metric.png` |
| Incident log | `evidence/13-incident-log.png` |
| Incident trace | `evidence/14-incident-trace.png` |

## 3. Kết quả kỹ thuật

| Nội dung | Baseline | Kết quả cuối | Nhận xét |
|---|---|---|---|
| `validate_logs.py` | 30/100 | 100/100 | Đạt toàn bộ 4 bài test schema, correlation ID, log enrichment và PII scrubbing |
| `validate_dashboard.py` | HỢP LỆ (6/6 panel) | HỢP LỆ (6/6 panel) | Đạt 6/6 panel theo contract `config/dashboard.yaml` và chạy runtime tại `/dashboard` |
| `pytest` | 22 passed (100%) | 24 passed (100%) | Đạt 24/24 tests bao gồm test mới cho CCCD và thẻ ngân hàng |
| Số traces hợp lệ | 10 traces | >25 traces | Traces phân cấp rõ ràng root `lab-agent-run` -> `retrieval` -> `generation` trên Langfuse |
| Số PII leak | 0 leak | 0 leak | Không có rò rỉ PII, toàn bộ dữ liệu nhạy cảm được redact tự động |
| Latency P95 / TTFT P95 | 7100 ms / 64 ms | ~450 ms / 60 ms | Bình thường đạt ~450ms/60ms; khi inject challenge phát hiện P95 tăng vọt lên 18,021ms |
| Retrieval success rate | 100% (20/20) | 100% | 100% tool retrieval thực thi thành công |

## 4. Logging và PII

- **Cách tạo/nhận và truyền correlation ID:** Trong `app/middleware.py`, middleware `CorrelationIdMiddleware` gọi `clear_contextvars()` ở đầu request để dọn sạch context cũ. Sau đó kiểm tra header `x-request-id`; nếu không có sẽ sinh mới theo format `req-<8-hex>` (`f"req-{uuid.uuid4().hex[:8]}"`). ID được gán vào `request.state.correlation_id` và bind vào structlog context qua `bind_contextvars(correlation_id=correlation_id)`. Cuối cùng, middleware trả ID và thời gian xử lý qua các header `x-request-id` và `x-response-time-ms`.
- **Các metadata được ghi vào structured log:** Mỗi bản ghi log có `ts`, `level`, `service`, `event`, `correlation_id`. Khi request vào endpoint `/chat`, log được enrich thêm `user_id_hash` (SHA-256 rút gọn 12 ký tự), `session_id`, `feature`, `model`, `env`. Khi trả response, log bổ sung `latency_ms`, `ttft_ms`, `tokens_in`, `tokens_out`, `cost_usd`, `quality_score`, `tool_name`, `tool_success` và `payload`.
- **Cách bảo đảm PII được scrub trước khi ghi:** Xây dựng processor `scrub_event` trong `app/logging_config.py` quét đệ quy các trường văn bản để thay thế regex PII (`email`, `phone_vn`, `cccd`, `credit_card`) thành các token `[REDACTED_*]`. Processor này được đặt trong mảng `processors` của structlog trước `JsonlFileProcessor()` và `JSONRenderer()`, đảm bảo dữ liệu luôn được che chắn trước khi ghi ra file hoặc render JSON.
- **Cách kiểm chứng kết quả:** Chạy `python scripts/validate_logs.py` đạt điểm tuyệt đối **100/100** (vượt qua toàn bộ 4 bài test: Basic JSON schema, Correlation ID propagation, Log enrichment, PII scrubbing), và chạy `python -m pytest -q` đạt **24 passed (100%)**.

## 5. Tracing và prompt versioning

- **Cách xác nhận traces do chính tôi tạo trong project cá nhân:** Khởi tạo API key pair riêng trên Langfuse Cloud cho project cá nhân `day13-k4-l3a-2A202602764` và cấu hình trong `.env`. Mọi trace đều mang `environment: dev`, `user_id_hash` và metadata `correlation_id` (trùng khớp với log trong `data/logs.jsonl`), chứng minh trace được tạo trực tiếp từ phiên chạy của học viên.
- **Cấu trúc root/retrieval/generation observations:**
  - Root observation: `lab-agent-run` (type `agent`), bao bọc toàn bộ chu trình thực thi `LabAgent.run`.
  - Child observation 1: `retrieval` (type `retriever`), đo bước trích xuất tài liệu ngữ cảnh, ghi nhận `doc_count`.
  - Child observation 2: `generation` (type `generation`), đo thời gian thực thi của mô hình LLM, nhận diện `model: claude-sonnet-4-5`, chi phí `cost_details`, lượng token `usage_details` (input/output) và liên kết với prompt template.
- **Cách nối trace với log:** Request ID dạng `req-<8-hex>` sinh từ `CorrelationIdMiddleware` được lưu vào `request.state.correlation_id`. Giá trị này vừa được bind vào structlog để ghi vào toàn bộ các sự kiện trong `data/logs.jsonl`, vừa được truyền vào trace metadata của Langfuse thông qua `propagate_attributes(metadata={"correlation_id": correlation_id})`. Khi cần tra cứu, chỉ cần copy `correlation_id` từ log và tìm kiếm trên Langfuse.
- **Prompt name:** `day13-chat`
- **Version/label baseline:** Version `1` gắn nhãn `baseline` và `production`.
- **Version/label candidate:** Version `2` (tinh chỉnh bổ sung yêu cầu câu trả lời súc tích trong 1-2 câu) gắn nhãn `candidate`.
- **Trace ID của mỗi version:**
  - Version 1 (`baseline`): `09734dca4d10c513e1b9a6db345c85b0`
  - Version 2 (`candidate`): `9a833deff721b57a294cbe9feab958bf`
- **Cách promote và rollback `production`:** Sử dụng API `update_prompt` của Langfuse hoặc giao diện web. Để promote v2, chuyển label `production` sang Version 2 (`new_labels=['candidate', 'production']`). Khi cần rollback về v1, chuyển lại label `production` về Version 1 (`new_labels=['baseline', 'production']`).

## 6. Dashboard, SLO và alerts

- **Dashboard và sáu panel:** Dựng web dashboard tương tác thời gian thực tại `http://127.0.0.1:8000/dashboard` lấy nguồn trực tiếp từ `data/logs.jsonl` đáp ứng đầy đủ contract `config/dashboard.yaml`:
  1. `latency`: P50, P95, P99 và TTFT P95 (đơn vị `ms`, threshold: P95 <= 3000 ms).
  2. `traffic`: Tổng request count và rate_per_minute (đơn vị `requests_per_minute`, threshold: >= 1 rpm).
  3. `errors`: Tỷ lệ lỗi %, phân loại theo `error_type` và tỷ lệ `tool_success_rate_pct` (đơn vị `percent`, threshold: <= 2%).
  4. `cost`: Chi phí theo phút và tổng chi phí (đơn vị `usd`, threshold: <= $2.50).
  5. `tokens`: Tổng token vào/ra và tổng token (đơn vị `tokens`, threshold: <= 50,000 tokens).
  6. `quality`: Điểm trung bình chất lượng câu trả lời (đơn vị `score_0_to_1`, threshold: >= 0.75).
- **SLO và lý do chọn:** Primary SLO `fast_successful_requests` với mục tiêu 99.5% requests thành công và có `latency_ms <= 3000ms` trong chu kỳ 28 ngày (`window: 28d`). Lý do chọn: Phù hợp với kỳ vọng phản hồi tương tác đàm thoại của người dùng, đảm bảo trải nghiệm không bị ngắt quãng.
- **Cách tính error budget:** Error budget = $100\% - 99.5\% = 0.5\%$. Với quy mô 100,000 requests trong chu kỳ 28 ngày, hệ thống cho phép tối đa $100,000 \times 0.5\% = 500$ requests bị chậm (> 3s) hoặc bị lỗi mà vẫn đảm bảo cam kết SLO.
- **Ba alert và runbook tương ứng:**
  1. `HighLatencyDegradation` (Warning, 5m, Slack `#llmops-alerts`, runbook: `docs/alerts.md#alert-1`): Cảnh báo khi P95 latency vượt 3000ms kéo dài 5 phút.
  2. `ElevatedErrorRate` (Critical, 2m, Slack `#llmops-critical`, runbook: `docs/alerts.md#alert-2`): Báo động khẩn cấp khi tỷ lệ lỗi vượt quá 2% trong 2 phút.
  3. `RetrievalSuccessDrop` (Warning, 5m, Slack `#llmops-alerts`, runbook: `docs/alerts.md#alert-3`): Cảnh báo khi tỷ lệ retrieval thành công giảm dưới 90% kéo dài 5 phút.

## 7. Điều tra challenge

- **Challenge ID:** `day13-k4-l3a-monitoring-llmops-v1`
- **Khoảng thời gian điều tra:** 09:21:37 UTC – 09:22:05 UTC (tương đương 16:21:37 – 16:22:05 giờ Việt Nam Asia/Ho_Chi_Minh).
- **Triệu chứng từ metrics:** Trên panel **Latency percentiles and TTFT** (panel `latency`), độ trễ P95 tăng vọt bất thường từ mức baseline ~450ms lên **18,021 ms** (vượt ngưỡng SLO 3,000ms gấp 6 lần). Trong khi đó, TTFT P95 vẫn duy trì ổn định ở mức ~60ms, tỷ lệ lỗi không đổi (0%) và retrieval success rate vẫn đạt 100%.
- **Log line và correlation ID liên quan:**
  - Correlation ID: `req-8d1a6411` (Feature: `monitoring`, Session: `k4-l3a-challenge-s04`).
  - Log line `response_sent`:
    ```json
    {"service": "api", "latency_ms": 5500, "ttft_ms": 60, "tokens_in": 36, "tokens_out": 99, "cost_usd": 0.001593, "quality_score": 0.9, "tool_name": "retrieval", "tool_success": true, "payload": {"answer_preview": "Starter answer. You should improve this output logic and add better quality chec..."}, "event": "response_sent", "session_id": "k4-l3a-challenge-s04", "feature": "monitoring", "correlation_id": "req-8d1a6411", "model": "claude-sonnet-4-5", "user_id_hash": "4570299f37e2", "env": "dev", "level": "info", "ts": "2026-09-29T09:21:50.210941Z"}
    ```
- **Trace ID và span gây ảnh hưởng:**
  - Trace ID: `df1e946476a7155f6980eaf35f372266`
  - So sánh duration các span trong trace:
    - Root observation `lab-agent-run`: **5.500 s**
    - Observation `retrieval` (RETRIEVER): **2.511 s** (chiếm phần lớn thời gian thực thi)
    - Observation `generation` (GENERATION): **0.170 s** (hoàn toàn bình thường)
  - Span gây nghẽn: observation child `retrieval` (ID: `50b7ecbc18edaaca`).
- **Root cause:** Bước trích xuất dữ liệu `retrieval` bị nghẽn chậm (`rag_slow` scenario: trễ thêm ~2.5s) khi truy vấn tài liệu domain cho feature `monitoring`, khiến tổng thời gian xử lý request vượt xa ngưỡng cam kết SLO 3s trong khi model generation vẫn xử lý nhanh chóng (170ms).
- **Fix action:** Tắt sự cố bằng lệnh `python scripts/inject_incident.py --disable`. Trong thực tế sản xuất: triển khai cache kết quả embedding/retrieval cho các truy vấn lặp lại, tối ưu cấu trúc index của Vector Database (HNSW), và bổ sung timeout ngắt sớm (1000ms) kèm fallback answer khi retrieval bị nghẽn.
- **Preventive measure:** Thiết lập alert riêng biệt đo thời gian xử lý của retriever (`retrieval_latency > 1500ms`), triển khai circuit breaker bảo vệ downstream vector store, và bổ sung canary testing kiểm tra hiệu năng trước khi nạp thêm dữ liệu tài liệu mới.

## 8. Giải thích và tự đánh giá

- **Một quyết định kỹ thuật quan trọng và lý do:** Đặt processor `scrub_event` trong chuỗi structlog processors ngay trước `JsonlFileProcessor()` và `JSONRenderer()`. Quyết định này bảo đảm PII được lọc sạch đệ quy trên toàn bộ dữ liệu trước khi được serialize hoặc ghi xuống đĩa, loại bỏ hoàn toàn nguy cơ rò rỉ dữ liệu nhạy cảm của người dùng ra log file hay log aggregator bên ngoài.
- **Một lỗi/blocker đã gặp:** Ban đầu khi dùng `@observe` cho `retrieve` và `FakeLLM.generate`, trace con không ghi nhận được token usage và cost chi tiết do Langfuse v4 yêu cầu cập nhật span thông qua `update_current_generation` hoặc `start_as_current_observation` với OpenTelemetry context.
- **Cách tìm nguyên nhân và xử lý:** Kiểm tra source code SDK Langfuse v4 và `tests/test_tracing_adapter.py`, gọi `get_langfuse_client().update_current_generation(model=..., usage_details=..., cost_details=...)` và truyền `managed_prompt` qua `propagate_attributes`. Sau khi cấu hình, cây quan sát (waterfall) trên Langfuse hiển thị chính xác cả 2 span con với đầy đủ metadata.
- **Cách hiểu luồng Metrics → Logs → Traces:**
  - **Metrics** là tầng tín hiệu đầu tiên (Symptom): Dashboard thể hiện P95 latency vượt ngưỡng SLO 3s trong khoảng 16:21.
  - **Logs** là tầng trung gian (Identification): Lọc `data/logs.jsonl` trong khoảng thời gian đó, tìm thấy request của feature `monitoring` có `correlation_id` là `req-8d1a6411` với `latency_ms: 5500`.
  - **Traces** là tầng chi tiết sâu nhất (Localization): Dùng `correlation_id` mở trace trên Langfuse, so sánh thời gian thực thi giữa span `retrieval` (2.511s) và `generation` (0.170s) để khẳng định chính xác 100% nguyên nhân nghẽn nằm ở bước RAG retrieval chứ không phải LLM call.
- **Vai trò của prompt version, token/cost, SLO hoặc rollback trong vận hành LLM:** Giúp quản lý rủi ro khi triển khai thay đổi trên mô hình AI: Prompt versioning gắn nhãn (`production`, `candidate`, `baseline`) cho phép theo dõi trực tiếp chất lượng và độ trễ của từng prompt; đo lường token/cost liên tục giúp phát hiện sớm hiện tượng bùng nổ chi phí (cost spike); SLO và error budget cung cấp thước đo khách quan để quyết định khi nào cần đóng băng tính năng hoặc thực hiện rollback ngay lập tức về version ổn định trước đó.
- **Điều quan trọng nhất đã học:** Kỹ năng xây dựng hệ thống quan sát toàn diện (Observability) cho ứng dụng LLM theo chuẩn công nghiệp: biết cách chuẩn hóa log cấu trúc, che chắn PII, liên kết Metrics-Logs-Traces bằng Correlation ID, và cách xử lý sự cố có hệ thống dựa trên bằng chứng dữ liệu thay vì suy đoán.
- **Hạn chế hoặc phần chưa hoàn thành, nếu có:** Không có; toàn bộ code, test, và 14 file ảnh evidence thực tế đã được hoàn thiện đầy đủ 100%.

## 9. Checklist trước khi nộp

- [x] Kết quả và evidence thuộc commit SHA cuối.
- [x] Tất cả ảnh/output mở được bằng đường dẫn tương đối.
- [x] Incident evidence nối đúng metric → log → trace.
- [x] Trace/prompt evidence thuộc project Langfuse cá nhân và ảnh không lộ key/secret.
- [x] Repository chạy lại được theo README.
- [x] Không có secret, API key, PII thô hoặc evidence của người khác/lớp khác.
- [x] URL repo và commit SHA cuối đã được nộp trên LMS/Codelabs.
