import urllib.request
import json
import subprocess

def get_token():
    return subprocess.check_output(["gcloud", "auth", "print-access-token"]).decode('utf-8').strip()

token = get_token()
project = "wortz-project-352116"
region = "us-central1"
gw_name = "geap-workshop-ge-gateway-egress"
url = f"https://networkservices.googleapis.com/v1beta1/projects/{project}/locations/{region}/agentGateways?agentGatewayId={gw_name}"

data = {
    "name": f"projects/{project}/locations/{region}/agentGateways/{gw_name}",
    "type": "EGRESS"
}

req = urllib.request.Request(url, data=json.dumps(data).encode('utf-8'), method='POST')
req.add_header('Authorization', f'Bearer {token}')
req.add_header('Content-Type', 'application/json')

try:
    with urllib.request.urlopen(req) as response:
        print(response.read().decode('utf-8'))
except urllib.error.HTTPError as e:
    print(e.read().decode('utf-8'))
