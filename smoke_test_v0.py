import json

import httpx


API_URL = "http://localhost:8000/runtime/dispatch"


def main() -> None:
    payload = {
        "action": "broadcast_update",
        "payload": {"topic": "v0_scaffold", "version": "runtime-first"},
    }
    response = httpx.post(API_URL, json=payload, timeout=10.0)
    response.raise_for_status()
    print("Smoke test passed.")
    print(json.dumps(response.json(), indent=2))


if __name__ == "__main__":
    main()
