# Benchmark & Observability Report — Day 14

> Mọi con số dưới đây được lấy trực tiếp từ các file trong `reports/`, `benchmark-results/` và các ảnh chụp trong `screenshots/`.

**Họ tên:** Dương Thành Bình (MSSV: 2A202603531)
**Ngày chạy:** 2026-11-25
**Môi trường:** Windows 11 + WSL2 (Ubuntu 24.04, Python 3.12.3) + Docker Desktop (Docker 29.9.3)

---

## 1. SLO của agent

| SLI | SLO | Lý do chọn ngưỡng này |
|---|---|---|
| p95 latency `/ask` | < 500 ms | Latency cơ bản của mock LLM ~150–200ms; ngưỡng 500ms đảm bảo 95% người dùng nhận phản hồi nhanh, đồng thời phát hiện ngay khi tail latency (1.7s) vượt quá 5% tổng traffic |
| Error rate `/ask` | < 2.0 % | Mock LLM có tỉ lệ lỗi upstream ~1%; ngưỡng 2% chừa error budget hợp lý cho lỗi thoáng qua mà vẫn chặn được sự cố diện rộng |
| Accuracy trên golden dataset | ≥ 80 % | Đảm bảo chất lượng trả lời của agent v2 (RAG) ở mức đạt chuẩn sản xuất trước khi merge/deploy (sau khi sửa KB đạt 100%) |

---

## 2. Benchmark hiệu năng (develop, `load_test.py`)

### 2.1 Concurrency vs latency (agent v2)

| Concurrency | RPS | p50 (ms) | p95 (ms) | p99 (ms) | Error rate | SLO |
|---|---|---|---|---|---|---|
| 1 | 4.15 | 187.8 | 218.7 | 1691.0 | 1.33% | PASS |
| 10 | 37.75 | 188.0 | 219.7 | 1696.5 | 1.67% | PASS |
| 50 | 106.65 | 194.6 | 246.9 | 1691.0 | 1.33% | PASS |
| 100 | 72.00 | 293.8 | 2493.5 | 2695.6 | 0.00% | FAIL |

**Nhận xét:** RPS có tăng tuyến tính theo concurrency không? Vì sao?

Không. Từ concurrency `1 → 10 → 50`, RPS tăng gần tuyến tính (`4.15 → 37.75 → 106.65 req/s`) nhờ `asyncio` xử lý I/O bất đồng bộ song song hiệu quả. Tuy nhiên khi lên `100`, RPS giảm xuống `72.00 req/s` và p95 vọt lên `2493.5 ms` (vượt SLO 500ms) do 1 process uvicorn chạm ngưỡng xử lý kết nối đồng thời/event loop contention trên môi trường local, khiến các request bị xếp hàng chờ nhau.

### 2.2 Tail latency

| `MOCK_SLOW_RATE` | avg (ms) | p95 (ms) | p99 (ms) |
|---|---|---|---|
| 0 | 187.2 | 216.3 | 220.5 |
| 0.03 (mặc định) | 270.6 | 1657.1 | 1701.2 |
| 0.1 | 365.5 | 1703.2 | 1715.8 |

**Nhận xét:** Chỉ số nào nhạy nhất với request chậm? Vì sao SLO không nên đặt theo average?

**p99** (và **p95** khi tỉ lệ chậm > 5%) nhạy nhất với request chậm: khi `MOCK_SLOW_RATE` tăng từ `0` lên `0.03` (chỉ 3% request chậm), `avg` chỉ tăng nhẹ từ `187.2 ms` lên `270.6 ms` (trông vẫn "ổn"), trong khi `p99` nhảy vọt gần 8 lần lên `1701.2 ms`. Khi lên `0.1` (10% request chậm), cả `p95` cũng nhảy lên `1703.2 ms` dù `avg` mới là `365.5 ms`. Vì giá trị trung bình (`average`) bị kéo thấp bởi 90–97% request nhanh nên che giấu trải nghiệm tệ của nhóm người dùng gặp tail latency; do đó SLO phải đặt theo **p95 hoặc p99**.

---

## 3. Benchmark chất lượng (develop, `eval/run_eval.py`)

| Chỉ số | Agent v1 | Agent v2 | Agent v2 (sau khi sửa KB) |
|---|---|---|---|
| Accuracy | 4.3% (1/23) | 91.3% (21/23) | 100.0% (23/23) |
| Avg tokens / câu | 58.0 | 109.1 | 113.7 |
| Tổng cost (USD) | $0.000417 | $0.000762 | $0.000790 |
| Cost / câu đúng (USD) | $0.00041655 | $0.00003627 | $0.00003436 |
| Quality gate | FAIL | PASS | PASS |

**Những câu v2 trả lời sai ban đầu và cách bạn sửa:**

| ID | Keyword bị thiếu | Bạn đã sửa gì |
|---|---|---|
| `security-02` | `token`, `hết hạn`, `chữ ký` | Thêm entry `(["jwt"], ...)` giải thích JWT (token có chữ ký số, chứa thông tin user và thời điểm hết hạn) vào `KNOWLEDGE_BASE` trong `develop/utils/mock_llm.py` và `production/utils/mock_llm.py` |
| `scaling-03` | `cpu`, `memory`, `custom metrics` | Thêm entry `(["hpa", "kubernetes", "autoscal"], ...)` giải thích Kubernetes HPA scale pod theo CPU, memory hoặc custom metrics vào `KNOWLEDGE_BASE` |

**Nhận xét về trade-off chất lượng / chi phí / latency giữa v1 và v2:**

Agent v2 (có bước retrieval/RAG) tốn trung bình ~1.9 lần số token mỗi câu (`109.1` vs `58.0` tokens) và thêm ~20ms cho bước tìm tài liệu nên tổng chi phí tăng từ `$0.000417` lên `$0.000762`. Đổi lại, độ chính xác tăng vọt từ `4.3%` lên `91.3%` (và `100%` sau khi bổ sung KB), giúp **cost / câu trả lời đúng** giảm hơn **11 lần** (từ `$0.00041655` xuống `$0.00003436`).

**Cách dùng exit code của `run_eval.py` để chặn merge trong CI:**
Script `eval/run_eval.py` trả về `exit code = 1` nếu `accuracy < --min-accuracy` hoặc có bất kỳ câu nào bị regression so với `--baseline`. Trong GitHub Actions (`.github/workflows/eval.yml`), ta khởi động agent nền rồi chạy `python eval/run_eval.py --url http://localhost:8000 --min-accuracy 0.85 --baseline reports/eval_v2_fixed.json` — nếu job trả về exit code khác 0 thì CI tự động fail và chặn merge Pull Request.

---

## 4. Observability stack (production)

### 4.1 Screenshot

- [x] Dashboard Grafana khi đang có tải: [grafana-dashboard.png](screenshots/grafana-dashboard.png)
- [x] Một trace chậm trong Jaeger: [jaeger-slow-trace.png](screenshots/jaeger-slow-trace.png)
- [x] Một trace lỗi trong Jaeger: [jaeger-error-trace.png](screenshots/jaeger-error-trace.png)
- [x] Trang Alerts của Prometheus với 3 alert đang **firing**: [prometheus-alert-firing.png](screenshots/prometheus-alert-firing.png)

**Trả lời câu hỏi Exercise 7.4 (Grafana & Nginx):**
1. **Khoảng cách giữa `avg` và `p95`:** Trong dashboard khi có tải, `p50`/`avg` nằm quanh ~200–240ms nhưng `Latency p95` vọt lên `1.98s` (màu đỏ) vì ~3% request bị slow path (~1.7s) làm đuôi phân phối kéo dài.
2. **Nginx chia đều traffic:** Trên panel *Requests/s theo instance*, hai instance `172.19.0.6:8000` và `172.19.0.8:8000` có đường biểu đồ trùng nhau ở mức ~30 req/s mỗi instance → Nginx chia đều tải theo round-robin.
3. **`input tokens/s` lớn hơn `output tokens/s`:** Vì agent v2 chèn thêm system prompt + tài liệu tìm được từ `KNOWLEDGE_BASE` (context) vào input prompt trước khi gọi LLM, nên lượng token đầu vào (~70–90 tokens) luôn lớn hơn câu trả lời đầu ra (~35–55 tokens).
4. **`curl http://localhost:8080/metrics` trả về 404:** Vì trong `nginx/nginx.conf`, route `/metrics` bị chặn từ bên ngoài (`return 404;`) để không lộ thông tin nội bộ hệ thống ra internet; chỉ Prometheus nằm trong cùng Docker network mới scrape trực tiếp `agent:8000/metrics`.

### 4.2 Thí nghiệm "phá hệ thống"

| # | Thay đổi | Alert nào firing | Thời gian từ lúc đổi → firing | Panel nào phản ánh rõ nhất |
|---|---|---|---|---|
| A | `MOCK_ERROR_RATE=0.2` | `AgentHighErrorRate` | ~1–2 phút (`for: 1m`, giá trị đo được `18.67% > 5%`) | Golden Signals: `Error rate`, `Requests/s theo status code` (503) |
| C | `LLM_MODEL=mock-llm-large` | `LLMCostBurnRateHigh` | ~2–3 phút (`for: 2m`, giá trị đo được `$8.42/giờ > $2/giờ`) | `Cost burn rate (USD/giờ)`, `LLM cost (1h)` |
| D | `docker pause k5-day14-observability-agent-1` | `AgentInstanceDown` | ~30–40 giây (`for: 30s`, `up == 0`) | `Instances up` (giảm còn 1) |

**Thí nghiệm E (`AGENT_VERSION=v1`) không làm alert nào firing. Bạn sẽ phát hiện loại sự cố này trong production bằng cách nào?**

Alert hạ tầng chỉ theo dõi HTTP status code, latency, CPU/RAM và chi phí nên không phát hiện được việc câu trả lời bị sai về mặt ngữ nghĩa. Để phát hiện sự cố suy giảm chất lượng trong production cần:
1. Chạy **Eval tự động trên golden dataset** trong CI/CD trước khi deploy (quality gate).
2. Giám sát **chỉ số chất lượng nghiệp vụ** trên production như: tỉ lệ retrieval hit (`retrieval_hit_ratio` bị tụt về 0% trên Grafana khi chuyển sang v1), **LLM-as-a-judge** chấm mẫu traffic thật định kỳ, và thu thập **feedback của người dùng** (thumbs up/down).

### 4.3 Debug bằng trace

**Trace chậm nhất trong Jaeger** ([jaeger-slow-trace.png](screenshots/jaeger-slow-trace.png)):
- `trace_id` (rút gọn trên UI): `2c35a26`
- Tổng thời gian: `1.7 s` (`~1700 ms`)
- Span chiếm nhiều thời gian nhất: `chat mock-llm-small` (`1.7 s`, chiếm ~98.5% tổng thời gian request; trong khi `agent.retrieve_context` chỉ mất `21.7 ms`).

**Trace lỗi trong Jaeger & dòng log JSON tương ứng** ([jaeger-error-trace.png](screenshots/jaeger-error-trace.png)):
- Trace lỗi mẫu trên UI: `f0f471a` (`107 ms`, HTTP `503`, event `exception: Upstream LLM error: 503 Service Unavailable (mock)`).
- Dòng log JSON thực tế từ container `agent` có `trace_id` để tra cứu trong Jaeger:

```json
{"ts": "2026-11-25T09:43:46.057875+00:00", "level": "INFO", "service": "observable-agent", "instance": "0b2936365b0d", "event": "llm_error", "trace_id": "bb7055fcb91d2b0bc365eae002838ced", "span_id": "131cb49b9dbf2f13", "request_id": "030bde12d531", "error": "Upstream LLM error: 503 Service Unavailable (mock)"}
```

---

## 5. Benchmark scaling (production, Locust headless, 100 users, 2 phút)

| Số instance | RPS | p50 (ms) | p95 (ms) | p99 (ms) | Failures |
|---|---|---|---|---|---|
| 1 | 65.83 (Aggregated) / 59.88 (`/ask`) | 190 | 220 (Agg) / 230 (`/ask`) | 1700 | 72 / 7873 (0.91% Agg, 1.00% `/ask`) |
| 3 | 66.24 (Aggregated) / 60.04 (`/ask`) | 190 | 220 (Agg) / 220 (`/ask`) | 1700 | 71 / 7922 (0.90% Agg, 0.99% `/ask`) |

**Giải thích kết quả:** Scale có cải thiện p95 không? Nút thắt nằm ở đâu?

Scale từ 1 lên 3 instance gần như **không làm thay đổi RPS (~66 req/s) hay p95 (~220 ms)**. Nguyên nhân là vì agent xử lý I/O bất đồng bộ (`async/await`) không bị nghẽn CPU ở mức 100 users, và nút thắt chính nằm ở **latency giả lập chờ phản hồi của upstream LLM** (~150–200ms cho mỗi request, 3% request chậm ~1.7s) kết hợp với số lượng user đồng thời cố định của Locust (100 users lần lượt chờ response rồi mới gửi tiếp).

---

## 6. Kết luận

- 3 điều học được về benchmark & observability:
  1. Không bao giờ dùng `average latency` để đặt SLO vì tail latency (p95/p99) phản ánh chính xác hơn nhóm người dùng bị chậm.
  2. Eval trên golden dataset + quality gate bằng exit code giúp chặn regression chất lượng mà các công cụ giám sát hạ tầng (Prometheus/Grafana) không thể tự phát hiện.
  3. Kết hợp 3 trụ cột **Metrics (Prometheus/Grafana) + Traces (Jaeger) + Structured Logs (`trace_id`)** giúp khoanh vùng nhanh nguyên nhân chậm/lỗi nằm ở code của mình hay ở upstream LLM.
- Nếu đưa agent này lên production thật, sẽ thêm metric / alert:
  - **Rate limit / Cost guard rejections (`429`, `402`):** cảnh báo khi có user bị chặn bất thường hoặc tấn công brute-force.
  - **Redis connection & latency metrics:** theo dõi độ trễ/lỗi kết nối Redis để phòng sự cố readiness probe (`/ready` → 503).
  - **Automated eval score metric (LLM-as-a-judge / user feedback ratio):** phát hiện suy giảm chất lượng trả lời theo thời gian thực.
