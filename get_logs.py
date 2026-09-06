import urllib.request
import json
req2 = urllib.request.urlopen(f'https://api.github.com/repos/sheshagiri-62/zero-downtime-k8s/actions/jobs/101554916993')
job = json.loads(req2.read())
for step in job['steps']:
    print(f"{step['name']}: {step['conclusion']}")
