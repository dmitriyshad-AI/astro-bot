"""Tests for compatibility endpoints."""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from astro_api import db
from astro_api.main import app


class CompatibilityApiTest(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        db.DB_PATH = Path(self.tempdir.name) / "test.db"
        os.environ["TELEGRAM_BOT_TOKEN"] = "dummy"
        os.environ["OPENAI_API_KEY"] = "test"

        conn = db.get_connection()
        db.init_db(conn)
        conn.close()

        self.client = TestClient(app)

    def tearDown(self):
        self.tempdir.cleanup()

    def test_calc_compatibility_endpoint(self):
        fake_result = {
            "id": 123,
            "score": {"value": 75, "description": "good"},
            "top_aspects": [],
            "key_aspects": [],
            "wheel_path": str(Path(self.tempdir.name) / "wheel.svg"),
        }
        Path(fake_result["wheel_path"]).write_text("<svg></svg>", encoding="utf-8")
        with patch("astro_api.compatibility_service.calculate_compatibility", return_value=fake_result):
            resp = self.client.post(
                "/api/compatibility/calc",
                json={
                    "self_birth_date": "01.01.2000",
                    "self_place": "City",
                    "partner_birth_date": "02.02.2000",
                    "partner_place": "Town",
                },
            )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["ok"])
        self.assertEqual(data["compatibility_id"], 123)
        self.assertIn("wheel_url", data)

    def test_get_compatibility_and_wheel(self):
        conn = db.get_connection()
        db.init_db(conn)
        wheel_path = Path(self.tempdir.name) / "comp.svg"
        wheel_path.write_text("<svg></svg>", encoding="utf-8")
        comp_id = db.insert_compatibility(
            conn,
            user_id="1",
            self_profile_id=None,
            partner_profile_id=None,
            synastry_json=json.dumps({"a": 1}),
            score_json=json.dumps({"value": 10}),
            top_aspects_json=json.dumps({"top": []}),
            wheel_path=str(wheel_path),
        )
        resp = self.client.get(f"/api/compatibility/{comp_id}")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["ok"])
        self.assertIn("synastry", data)

        resp2 = self.client.get(f"/api/compatibility/{comp_id}/wheel.svg")
        self.assertEqual(resp2.status_code, 200)
        self.assertEqual(resp2.headers["content-type"], "image/svg+xml")


if __name__ == "__main__":
    unittest.main()
