import json, time, urllib.request, urllib.error
t0 = time.time()
for _ in range(600):
    try:
        req = urllib.request.Request(
            "http://127.0.0.1:8099/api/faces/known",
            data=json.dumps({"name": "Warmup Probe"}).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=2) as r:
            print(f"{time.time()-t0:.2f}s status={r.status} body={r.read().decode()}")
            break
    except urllib.error.HTTPError as e:
        print(f"{time.time()-t0:.2f}s status={e.code} body={e.read().decode()}")
        break
    except Exception:
        time.sleep(0.03)
else:
    print("no answer")
