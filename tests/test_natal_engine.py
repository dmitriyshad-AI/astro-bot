import datetime as dt
import tempfile
from pathlib import Path
import unittest

from astro_bot import natal_engine


class NatalEngineTest(unittest.TestCase):
    def test_parse_birth_date(self):
        result = natal_engine.parse_birth_date("12.03.1990")
        self.assertEqual(result, dt.date(1990, 3, 12))

    def test_parse_birth_time(self):
        self.assertEqual(natal_engine.parse_birth_time("08:30"), dt.time(8, 30))
        self.assertIsNone(natal_engine.parse_birth_time("не знаю"))
        self.assertIsNone(natal_engine.parse_birth_time(None))
        with self.assertRaises(natal_engine.NatalError):
            natal_engine.parse_birth_time("25:99")

    def test_generate_chart_from_location(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            res = natal_engine.generate_natal_chart_from_location(
                birth_date=dt.date(1990, 3, 12),
                birth_time=dt.time(10, 30),
                lat=55.75,
                lng=37.62,
                tz_str="Europe/Moscow",
                place_label="Москва, Россия",
                user_identifier="testcase",
                charts_dir=Path(tmpdir),
            )
            self.assertTrue(res.svg_path.exists())
            self.assertIn("Sun", res.summary)


if __name__ == "__main__":
    unittest.main()
