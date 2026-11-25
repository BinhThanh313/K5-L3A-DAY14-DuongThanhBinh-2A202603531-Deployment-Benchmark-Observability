# Deployment Information

## Public URL
https://k5-l3a-day14-duongthanhbinh-2a202603531-deployme-production.up.railway.app

## Platform
Railway (Root Directory: `06-lab-complete`, kèm managed Redis service)

## Test Commands

### Health Check
```bash
curl -sS https://k5-l3a-day14-duongthanhbinh-2a202603531-deployme-production.up.railway.app/health
# Expected: {"status":"ok"}
```

### Readiness Check
```bash
curl -sS https://k5-l3a-day14-duongthanhbinh-2a202603531-deployme-production.up.railway.app/ready
# Expected: {"status":"ready"}
```

### API Test (without key -> 401, with key -> 200)
```bash
curl -sS -o /dev/null -w '%{http_code}\n' \
  -X POST https://k5-l3a-day14-duongthanhbinh-2a202603531-deployme-production.up.railway.app/ask \
  -H "Content-Type: application/json" \
  -d '{"question": "Hello"}'
# Expected: 401

curl -sS -X POST https://k5-l3a-day14-duongthanhbinh-2a202603531-deployme-production.up.railway.app/ask \
  -H "X-API-Key: YOUR_AGENT_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"user_id": "test", "question": "Hello"}'
# Expected: 200
```

## Environment Variables Set
- `PORT` (`8000`)
- `REDIS_URL` (`${{Redis.REDIS_URL}}`)
- `AGENT_API_KEY` (đặt trực tiếp trên Railway Variables, không commit vào repo)

## Screenshots
- [Deployment dashboard](screenshots/dashboard.png)
- [Service running](screenshots/running.png)
- [Test results](screenshots/test.png)
