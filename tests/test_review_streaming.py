from __future__ import annotations

import asyncio
import unittest
from unittest.mock import AsyncMock

from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from agent.review_event_broadcaster import ReviewEventBroadcaster
from backend.app import main
from backend.app.routes import review as review_routes


class ReviewStreamingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(main.app)

    def test_review_creation_returns_id_before_processing(self) -> None:
        original = review_routes._run_review

        async def fake_run(review_id: str, repo_path: str | None, code_snippet: str | None, language: str) -> None:
            return None

        review_routes._run_review = fake_run
        try:
            response = self.client.post("/api/v1/review/start", json={"code_snippet": "print('ok')"})
        finally:
            review_routes._run_review = original
        self.assertEqual(response.status_code, 202)
        self.assertTrue(response.json()["review_id"].startswith("review-"))
        self.assertEqual(response.json()["status"], "started")

    def test_websocket_connection_receives_connected(self) -> None:
        original = review_routes._run_review

        async def fake_run(review_id: str, repo_path: str | None, code_snippet: str | None, language: str) -> None:
            return None

        review_routes._run_review = fake_run
        try:
            review_id = self.client.post("/api/v1/review/start", json={"code_snippet": "print('ok')"}).json()["review_id"]
            with self.client.websocket_connect(f"/api/v1/ws/reviews/{review_id}") as websocket:
                self.assertEqual(websocket.receive_json(), {"type": "connected", "review_id": review_id})
        finally:
            review_routes._run_review = original

    def test_live_dag_event_delivery(self) -> None:
        async def scenario() -> None:
            broadcaster = ReviewEventBroadcaster()
            broadcaster.create("live-test", asyncio.get_running_loop())
            websocket = AsyncMock()
            self.assertTrue(await broadcaster.attach("live-test", websocket))
            event = {"review_id": "live-test", "node": "static_analysis", "event": "ast_parsed", "timestamp": "now", "payload": {"source_length": 12}}
            await broadcaster.publish("live-test", event)
            self.assertEqual(websocket.send_json.await_args_list[-1].args[0], event)

        asyncio.run(scenario())

    def test_completed_review_retrieval(self) -> None:
        original = review_routes._run_review

        async def fake_run(review_id: str, repo_path: str | None, code_snippet: str | None, language: str) -> None:
            await review_routes.review_event_broadcaster.set_status(review_id, "completed", result={"review_id": review_id, "total_findings": 0})

        review_routes._run_review = fake_run
        try:
            review_id = self.client.post("/api/v1/review/start", json={"code_snippet": "print('ok')"}).json()["review_id"]
            response = self.client.get(f"/api/v1/review/{review_id}")
        finally:
            review_routes._run_review = original
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "completed")
        self.assertEqual(response.json()["result"]["total_findings"], 0)

    def test_failed_review_handling(self) -> None:
        original = review_routes._run_review

        async def fake_run(review_id: str, repo_path: str | None, code_snippet: str | None, language: str) -> None:
            await review_routes.review_event_broadcaster.set_status(review_id, "failed", error="worker failed")

        review_routes._run_review = fake_run
        try:
            review_id = self.client.post("/api/v1/review/start", json={"code_snippet": "raise RuntimeError"}).json()["review_id"]
            response = self.client.get(f"/api/v1/review/{review_id}")
        finally:
            review_routes._run_review = original
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "failed")
        self.assertEqual(response.json()["error"], "worker failed")

    def test_unknown_review_status_returns_not_found(self) -> None:
        response = self.client.get("/api/v1/review/unknown-review")
        self.assertEqual(response.status_code, 404)

    def test_unknown_websocket_id_closes_gracefully(self) -> None:
        with self.client.websocket_connect("/api/v1/ws/reviews/unknown-review") as websocket:
            message = websocket.receive_json()
            self.assertEqual(message["event"], "review_failed")
            with self.assertRaises(WebSocketDisconnect):
                websocket.receive_json()

    def test_late_subscriber_receives_replayed_events(self) -> None:
        async def scenario() -> None:
            broadcaster = ReviewEventBroadcaster()
            broadcaster.create("late-test", asyncio.get_running_loop())
            event = {"review_id": "late-test", "node": "review_lifecycle", "event": "review_completed", "timestamp": "now", "payload": {"status": "completed"}}
            await broadcaster.publish("late-test", event)
            websocket = AsyncMock()
            self.assertTrue(await broadcaster.attach("late-test", websocket))
            self.assertEqual(websocket.send_json.await_args_list[0].args[0], {"type": "connected", "review_id": "late-test"})
            self.assertEqual(websocket.send_json.await_args_list[1].args[0], event)

        asyncio.run(scenario())


if __name__ == "__main__":
    unittest.main()
