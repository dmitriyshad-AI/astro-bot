"""API tests for insights and ask endpoints (mocked OpenAI)."""

from __future__ import annotations

import json
import importlib
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from astro_api import db
from astro_api.main import app
from astro_bot import natal_engine


class ApiAskInsightsTest(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        db.DB_PATH = Path(self.tempdir.name) / "test.db"
        os.environ["TELEGRAM_BOT_TOKEN"] = "dummy"
        os.environ["OPENAI_API_KEY"] = "test"

        conn = db.get_connection()
        db.init_db(conn)

        self.profile_id = db.insert_profile(
            conn,
            telegram_user_id=123,
            label="Test",
            birth_date="2000-01-01",
            birth_time=None,
            time_unknown=True,
            place_query="Test City",
            lat=1.0,
            lng=2.0,
            tz_str="UTC",
        )
        self.chart_payload = {
            "subject": {
                "sun": {"name": "Sun", "sign": "Aries", "position": 10.5, "house": "First_House", "retrograde": False},
                "first_house": {"sign": "Aries", "position": 0.0},
            },
            "aspects": [],
        }
        wheel_path = Path(self.tempdir.name) / "wheel.svg"
        wheel_path.write_text("<svg></svg>", encoding="utf-8")

        self.chart_id = db.insert_chart(
            conn,
            profile_id=self.profile_id,
            chart_json=json.dumps(self.chart_payload),
            wheel_path=str(wheel_path),
            summary="Summary text",
        )
        conn.close()

        self.client = TestClient(app)

    def tearDown(self):
        self.tempdir.cleanup()

    def test_insights_endpoint(self):
        with patch("astro_bot.openai_client.ask_gpt", return_value="insight text"):
            resp = self.client.get(f"/api/insights/{self.chart_id}")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["ok"])
        self.assertIn("insight", data["insights"])

    def test_ask_endpoint(self):
        with patch("astro_bot.openai_client.ask_gpt", return_value="answer text"):
            resp = self.client.post("/api/ask", json={"chart_id": self.chart_id, "question": "Что по солнцу?"})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["ok"])
        self.assertEqual(data["answer"], "answer text")
        self.assertTrue(data["history"])
        self.assertEqual(data["history"][-1]["question"], "Что по солнцу?")

    def test_recent_charts(self):
        resp = self.client.get("/api/charts/recent?limit=3")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["ok"])
        self.assertTrue(data["charts"])
        self.assertEqual(data["charts"][0]["id"], self.chart_id)

    def test_geo_search_with_mock(self):
        fake_loc = natal_engine.LocationResult(
            query="Moscow",
            display_name="Moscow",
            lat=55.75,
            lng=37.61,
            tz_str="Europe/Moscow",
        )
        with patch("astro_api.natal_service.resolve_location", return_value=fake_loc):
            resp = self.client.get("/api/geo/search?q=Moscow")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["ok"])
        self.assertAlmostEqual(data["location"]["lat"], 55.75)

    def test_natal_calc_mock(self):
        fake_result = {
            "chart_id": 99,
            "profile_id": 1,
            "summary": "summary",
            "wheel_path": "/tmp/wheel.svg",
            "context_text": "ctx",
            "chart": self.chart_payload,
            "location": {"display_name": "X", "lat": 0, "lng": 0, "tz_str": "UTC"},
        }
        with patch("astro_api.natal_service.calculate_natal_chart", return_value=fake_result):
            resp = self.client.post("/api/natal/calc", json={"birth_date": "01.01.2000", "place": "X"})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["ok"])
        self.assertEqual(data["chart_id"], 99)
        self.assertIn("wheel_url", data)

    def test_root_fallback_without_dist(self):
        # Force dist to non-existing dir and reload app module
        os.environ["WEBAPP_DIST_DIR"] = str(Path(self.tempdir.name) / "no_dist")
        from astro_api import main as main_module

        reloaded = importlib.reload(main_module)
        with TestClient(reloaded.app) as client2:
            resp = client2.get("/")
            self.assertEqual(resp.status_code, 200)
            self.assertIn("WebApp not built yet", resp.text)


if __name__ == "__main__":
    unittest.main()
