import requests, time, os

URL = os.getenv("BACKEND_URL", "https://diagnovate-backend-production-f341.up.railway.app/api/diagnosis/health")

while True:
    try:
        r = requests.get(URL, timeout=10)
        print(f"ping {r.status_code}")
    except Exception as e:
        print(f"ping failed: {e}")
    time.sleep(840)
