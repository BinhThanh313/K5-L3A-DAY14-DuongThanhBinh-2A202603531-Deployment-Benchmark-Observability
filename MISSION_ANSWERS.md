# Day 14 Lab — Mission Answers

**Họ tên:** Dương Thanh Bình  
**MSSV:** 2A202603531  
**Lớp:** K5-L3A  

---

## Part 1: Localhost vs Production

### Exercise 1.1: Anti-patterns phát hiện trong `01-localhost-vs-production/develop/app.py`
1. **Hardcode secret trong source code (dòng 17–18):** `OPENAI_API_KEY = "sk-hardcoded-fake-key-never-do-this"` và `DATABASE_URL = "postgresql://admin:password123@localhost:5432/mydb"`. Nếu commit lên GitHub sẽ bị lộ secret ngay lập tức.
2. **Hardcode cấu hình, không đọc từ biến môi trường (dòng 21–22):** `DEBUG = True`, `MAX_TOKENS = 500` không đổi được theo môi trường (`dev`, `staging`, `production`) nếu không sửa code.
3. **Dùng `print()` thay cho structured logging và in cả secret ra log (dòng 33–34, 38):** Dòng 34 `print(f"[DEBUG] Using key: {OPENAI_API_KEY}")` làm lộ API key trong log hệ thống; log dạng text khó parse/tìm kiếm.
4. **Không có health check endpoint `/health` và `/ready` (dòng 42–43):** Container orchestrator / cloud platform không biết app còn sống hay đã sẵn sàng nhận traffic.
5. **Bind `host="localhost"`, cố định `port=8000` và bật `reload=True` (dòng 51–53):** Trong container/cloud phải bind `0.0.0.0` và lắng nghe biến `PORT` do nền tảng cấp; `reload=True` gây tốn tài nguyên và không ổn định trên production.

### Exercise 1.2: Kết quả chạy bản `develop`
```http
HTTP/1.1 200 OK
date: Wed, 25 Nov 2026 08:04:19 GMT
server: uvicorn
content-length: 95
content-type: application/json

{"answer":"Agent đang hoạt động tốt! (mock response) Hỏi thêm câu hỏi đi nhé."}
```
*(Log server in ra `[DEBUG] Using key: sk-hardcoded-fake-key-never-do-this`, minh chứng rõ việc lộ secret khi dùng `print()`).*

### Exercise 1.3: Bảng so sánh `develop/app.py` vs `production/app.py`

| Feature | Develop (`develop/app.py`) | Production (`production/app.py`) | Tại sao quan trọng? |
|---|---|---|---|
| Config | Hardcode `OPENAI_API_KEY`, `port=8000`, `DEBUG=True` (dòng 17–22, 51–53) | Đọc từ biến môi trường qua `os.getenv(...)` và `Settings` | Tách biệt config khỏi code (12-Factor), không lộ secret trên Git, dùng 1 artifact cho nhiều môi trường |
| Health check | Không có (`/health`, `/ready`) | Có `GET /health` và `GET /ready` | Platform biết khi nào cần restart container (liveness) hoặc ngừng route traffic (readiness) |
| Logging | `print("[DEBUG] ...")`, lộ API key | Structured JSON logging (`logging` + `JsonFormatter`) | Dễ thu thập, tìm kiếm, lọc và theo dõi lỗi trên các công cụ như ELK/Datadog/Grafana |
| Shutdown | Tắt đột ngột | Graceful shutdown (xử lý `SIGTERM` / `lifespan`) | Hoàn thành các request đang xử lý (in-flight) trước khi thoát, không làm rớt kết nối của người dùng |

---

## Part 2: Docker

### Exercise 2.1: Câu hỏi về `02-docker/develop/Dockerfile`
1. **Base image:** `python:3.11` (chứa đầy đủ Debian OS + bộ công cụ biên dịch + Python 3.11).
2. **Working directory:** `/app` (`WORKDIR /app`).
3. **Tại sao `COPY requirements.txt` đứng trước `COPY . .`:** Để tận dụng **Docker layer cache**. Khi chỉ sửa code (`app.py`), các layer phía trước (`COPY requirements.txt` và `RUN pip install`) được dùng lại từ cache nên build lại chỉ mất vài giây thay vì cài lại toàn bộ thư viện.
4. **`CMD` vs `ENTRYPOINT`:** `CMD` định nghĩa lệnh/tham số mặc định và **có thể bị ghi đè** dễ dàng khi chạy `docker run <image> <lệnh_khác>`. `ENTRYPOINT` cố định file thực thi chính của container; nếu kết hợp cả hai thì `CMD` đóng vai trò là tham số truyền cho `ENTRYPOINT`.

### Exercise 2.2 & 2.3: Test container & So sánh kích thước image
- Kết quả chạy `my-agent:develop`:
  ```http
  HTTP/1.1 200 OK
  {"answer":"Container là cách đóng gói app để chạy ở mọi nơi. Build once, run anywhere!"}
  ```
- **So sánh dung lượng đo được bằng `docker images | grep my-agent`:**
  - `my-agent:develop`: **1.67 GB (1670 MB)**
  - `my-agent:advanced`: **240 MB**
  - **Chênh lệch:** Giảm **~85.6%** dung lượng!
- **Giải thích Multi-stage build (`02-docker/production/Dockerfile`):**
  - **Stage 1 (`builder`):** Dùng `python:3.11-slim`, cài `gcc`, `libpq-dev` và chạy `pip install --user -r requirements.txt` để biên dịch và cài đặt thư viện vào `/root/.local`.
  - **Stage 2 (`runtime`):** Bắt đầu từ image sạch `python:3.11-slim`, chỉ `COPY --from=builder /root/.local` và code ứng dụng, chạy bằng user non-root `appuser`. Không mang theo `gcc`, `libpq-dev` hay cache của `apt`/`pip` nên image nhẹ hơn rất nhiều và an toàn hơn.

### Exercise 2.4: Docker Compose stack (`02-docker/production/`)
**Sơ đồ kiến trúc:**
```text
Client ──▶ Nginx (:80) ──▶ Agent (:8000) ──┬──▶ Redis (:6379)
                                           └──▶ Qdrant (:6333)
```
**Kết quả test qua Nginx:**
- `GET http://localhost/health` → `HTTP/1.1 200 OK` (`{"status":"ok","uptime_seconds":4.1,"version":"2.0.0",...}`)
- `POST http://localhost/ask` → `HTTP/1.1 200 OK`

---

## Part 3: Cloud Deployment

### Exercise 3.1: Deploy Agent Part 6 lên Cloud
- **Nền tảng sử dụng:** *(Điền Railway hoặc Render sau khi deploy)*
- **URL Public:** *(Điền URL sau khi deploy ở bước CP6)*
- **Screenshots:** `screenshots/dashboard.png`, `screenshots/running.png`, `screenshots/test.png`

### Exercise 3.2: So sánh `railway.toml` và `render.yaml`

| Tiêu chí | `railway.toml` | `render.yaml` |
|---|---|---|
| Định dạng | TOML (`[build]`, `[deploy]`) | YAML (Infrastructure-as-Code Blueprint) |
| Khai báo service & DB | Chỉ cấu hình build/deploy cho 1 service hiện tại (`builder = "DOCKERFILE"`, `healthcheckPath = "/health"`); Redis tạo riêng trên dashboard và link qua `${{Redis.REDIS_URL}}` | Có thể khai báo cả danh sách `services:` (web service, Redis, envVars) ngay trong 1 file Blueprint |
| Quản lý Secret | Đặt biến môi trường trực tiếp trên Railway Dashboard / `railway variables set` | Khai báo trực tiếp trong `envVars` với `sync: false` hoặc `generateValue: true` để không lộ secret vào Git |

### Exercise 3.3: Mô tả pipeline CI/CD GCP Cloud Run (`03-cloud-deployment/production-cloud-run/`)
Pipeline trong `cloudbuild.yaml` gồm 4 bước chạy tuần tự (`waitFor`) khi push code lên nhánh `main`:
1. **`test`:** Dùng image `python:3.11-slim`, cài dependencies và chạy `pytest tests/` để đảm bảo code không lỗi trước khi đóng gói.
2. **`build`:** Build Docker image từ `Dockerfile` (tận dụng `--cache-from` từ bản `latest`), gắn tag `$COMMIT_SHA` và `latest`.
3. **`push`:** Đẩy các image tag lên Google Container Registry (`gcr.io/$PROJECT_ID/ai-agent`).
4. **`deploy`:** Dùng `gcloud run deploy` triển khai image vừa push lên Cloud Run (`asia-southeast1`), cấu hình public (`--allow-unauthenticated`), scale 1–10 instances (`min-instances=1` tránh cold start, khớp `service.yaml` với `containerConcurrency: 80`, liveness `/health` và startup `/ready`), và lấy secret từ Secret Manager.

---

## Part 4: API Security

### Exercise 4.1–4.3: Kết quả test (`04-api-gateway/`)
- **Bản `develop` (API Key):**
  - Không có `X-API-Key` → trả `HTTP/1.1 401 Unauthorized`
  - Có `X-API-Key: secret-key-123` → trả `HTTP/1.1 200 OK`
- **Bản `production` (JWT + Rate Limit 10 req/phút với user `student`):**
  - Lấy token qua `POST /auth/token` (`student` / `demo123`), sau đó gọi `POST /ask` với header `Authorization: Bearer <REDACTED_JWT_TOKEN>`:
  - **Request 1–10 (thành công):**
    ```http
    HTTP/1.1 200 OK
    content-type: application/json
    ...
    ```
  - **Request 11–12 (vượt ngưỡng 10 req/phút):**
    ```http
    HTTP/1.1 429 Too Many Requests
    x-ratelimit-limit: 10
    x-ratelimit-remaining: 0
    x-ratelimit-reset: 1795595159
    retry-after: 59
    ```

### Exercise 4.4: Giải thích Cost Guard
- **Cách triển khai:** Tính chi phí ước lượng dựa trên số token đầu vào (`input_tokens`) và đầu ra (`output_tokens`) theo đơn giá model, sau đó cộng dồn vào key theo ngày/tháng trong Redis (`INCRBYFLOAT`, kèm `EXPIRE`). Trước mỗi lần gọi LLM, gọi `check_budget()` để kiểm tra tổng chi phí đã chạm ngưỡng `DAILY_BUDGET_USD` / `MONTHLY_BUDGET_USD` chưa; nếu vượt thì từ chối ngay với mã **HTTP `402 Payment Required`**.
- **Vì sao cần cả Rate Limit và Cost Guard:** Rate Limit bảo vệ tốc độ request/phút (chống DDoS/spam), nhưng một user gửi ít request với prompt rất dài hoặc dùng model đắt tiền vẫn có thể đốt hết ngân sách. Cost Guard bảo vệ trực tiếp **chi phí tiền thật**.

---

## Part 5: Scaling & Reliability

### Exercise 5.1–5.3: Liveness, Readiness, Graceful Shutdown & Stateless
- **Liveness (`GET /health`) vs Readiness (`GET /ready`):** `/health` chỉ kiểm tra process còn sống (luôn trả `200`, kể cả khi Redis mất kết nối); nếu fail thì platform restart container. `/ready` kiểm tra các dependency như Redis (`r.ping()`); nếu lỗi trả `503` để Load Balancer tạm ngừng điều phối traffic vào instance đó mà không restart oan.
- **Graceful shutdown:** Khi nhận tín hiệu `SIGTERM` (từ `docker stop` hoặc Kubernetes), app ngừng nhận kết nối mới, xử lý hoàn tất các request đang chạy rồi mới thoát với exit code `0`.
- **Stateless design:** Lưu `conversation_history`, rate limit và cost trong **Redis** thay vì biến dict trong RAM, giúp mọi instance khi scale ngang đều dùng chung trạng thái.

### Exercise 5.4–5.5: Kết quả chạy `test_stateless.py` với 3 instance (`--scale agent=3`)
```text
Session ID: ccebda07-3ac2-4daf-874f-abd58ed22557
Total requests: 5
Instances used: {'instance-43ae8e', 'instance-721e80', 'instance-c2fb6d'}
✅ All requests served despite different instances!
Total messages: 10
✅ Session history preserved across all instances via Redis!
```
**Giải thích:** Nginx phân tán 5 request của cùng 1 session lần lượt qua cả 3 container (`instance-c2fb6d`, `instance-43ae8e`, `instance-721e80`). Vì cả 3 instance cùng đọc/ghi lịch sử vào một Redis chung nên toàn bộ 10 tin nhắn (5 hỏi + 5 đáp) vẫn được bảo toàn nguyên vẹn.

---

## Part 6: Final Project — Kết quả `check_production_ready.py`

```text
================================================================
  📋 Checklist Deliverable
     ✅ Dockerfile (multi-stage, < 500 MB)
     ✅ docker-compose.yml (agent + redis)
     ✅ .dockerignore
     ✅ Health check endpoint (GET /health)
     ✅ Readiness endpoint (GET /ready)
     ✅ API Key authentication
     ✅ Rate limiting
     ✅ Cost guard
     ✅ Config từ environment variables
     ✅ Structured logging
     ✅ Graceful shutdown
     ✅ Public URL ready (Railway / Render config)
----------------------------------------------------------------
  Result: 12/12 tiêu chí đạt · 43/43 checks passed
  🎉 PASS 12/12 — PRODUCTION READY! Deploy nào!
================================================================
```

---

## AI Log (Khai báo sử dụng AI)
- **Công cụ sử dụng:** Antigravity (Gemini)
- **Mục đích hỏi & nhận hỗ trợ:**
  - Chẩn đoán và xử lý lỗi môi trường WSL2 (tạo user Ubuntu, cài `pip`/`venv`, xử lý lỗi Docker Hub 429 rate limit khi pull image, và phát hiện thiếu `ENV PYTHONUSERBASE=/home/agent/.local` trong `benchmark-observability/production/Dockerfile`).
  - Gợi ý cấu trúc hoàn thiện các `TODO` trong `06-lab-complete/` (`config.py`, `auth.py`, `rate_limiter.py`, `cost_guard.py`, `redis_client.py`, `main.py`, multi-stage `Dockerfile`, `docker-compose.yml`, `railway.toml`, `render.yaml`), thêm metric `agent_question_length_chars` và bổ sung `KNOWLEDGE_BASE` trong `mock_llm.py`.
- **Tự kiểm tra:** Tự chạy lại toàn bộ các bài thực hành trên WSL2 & Docker Desktop: `check_production_ready.py` đạt `PASS 12/12` (43/43 checks), `eval/run_eval.py` đạt `23/23 (100%)` không regression, tự vận hành Locust/Grafana/Jaeger/Prometheus để xuất toàn bộ file JSON/CSV và chụp các ảnh bằng chứng.
