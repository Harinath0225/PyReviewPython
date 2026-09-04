import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient

from backend.app.main import app

client = TestClient(app)
print(client.get('/healthz').json())
response = client.post(
    '/api/v1/review',
    json={
        'code_snippet': '''import subprocess
api_key = "secret"
subprocess.run("ls -l", shell=True)
assert True
''',
        'language': 'python',
    },
)
print(response.status_code)
print(response.json()['total_findings'])
print(response.json()['findings'][0])
