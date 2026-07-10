"""Read-only page API smoke probe; never places orders or injects data."""
import argparse, json, urllib.request

def probe(base: str, timeout: float = 30.0):
    paths = ["/api/v1/health", "/api/v1/runtime/readiness", "/api/v1/data/status"]
    results = []
    for path in paths:
        with urllib.request.urlopen(base.rstrip('/') + path, timeout=timeout) as response:
            results.append({"path": path, "status": response.status})
    return results

if __name__ == "__main__":
    parser = argparse.ArgumentParser(); parser.add_argument("--base", default="http://127.0.0.1:18080"); parser.add_argument("--timeout", type=float, default=30)
    print(json.dumps(probe(parser.parse_args().base, parser.parse_args().timeout)))
