import urllib.request
import json
url = "http://localhost:9090/api/v1/targets"
req = urllib.request.Request(url)
with urllib.request.urlopen(req) as response:
    data = json.loads(response.read().decode('utf-8'))
    for target in data.get("data", {}).get("activeTargets", []):
        if "myapp" in target.get("labels", {}).get("job", ""):
            print(f"Target: {target.get('labels', {}).get('instance')} Health: {target.get('health')}")
