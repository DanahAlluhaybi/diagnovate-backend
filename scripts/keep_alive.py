import requests, time, os

URL = os.getenv(
    "BACKEND_URL",
    "https://diagnovate-backend-production-f341.up.railway.app/api/diagnosis/health"
)

print(f"Keep-alive started → pinging {URL} every 14 min")

while True:
    try:
        r = requests.get(URL, timeout=10)
        print(f"[ping] {r.status_code}")
    except Exception as e:
        print(f"[ping] failed: {e}")
    time.sleep(840)
