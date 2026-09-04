import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient

from agent.review_event_broadcaster import review_event_broadcaster
from backend.app.main import app

client = TestClient(app)
with client.websocket_connect('/api/v1/ws/reviews/test-review') as ws:
    print(ws.receive_json())
    asyncio.run(review_event_broadcaster.publish('test-review', {'type': 'event', 'message': 'hello'}))
    print(ws.receive_json())
