"""Regression coverage for the user-supplied Reuters article (local text only)."""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from news_pipeline import process_articles
from news_pipeline.pipeline import sentiment


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "samples" / "asia_hedge_funds.json"


class HedgeFundArticleTests(unittest.TestCase):
    def test_financial_downturn_vocabulary(self):
        for word in ("declined", "drawdown", "drawdowns", "dropping", "eroded",
                     "fell", "lost", "pullback", "retreated", "selloff",
                     "selloffs", "slumped"):
            with self.subTest(word=word):
                result = sentiment(word, "")
                self.assertEqual(result["label"], "negative")
                self.assertEqual(result["score"], -1)

    def test_article_is_negative(self):
        records = json.loads(FIXTURE.read_text(encoding="utf-8"))
        report = process_articles(records)
        self.assertEqual(report["summary"], {
            "input_count": 1, "output_count": 1, "duplicates_removed": 0,
            "sentiment_counts": {"positive": 0, "negative": 1, "neutral": 0},
        })
        article = report["articles"][0]
        self.assertEqual(article["title"], records[0]["title"])
        self.assertEqual(article["source"], "Reuters")
        self.assertEqual(article["timestamp"], "2026-08-05T10:58:00Z")
        self.assertEqual(article["sentiment"]["label"], "negative")
        self.assertLess(article["sentiment"]["score"], 0)

    def test_cli_report_is_negative(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "report.json"
            result = subprocess.run(
                [sys.executable, "-m", "news_pipeline", str(FIXTURE), str(output)],
                cwd=ROOT, capture_output=True, text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            report = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(report["articles"][0]["sentiment"]["label"], "negative")
            self.assertLess(report["articles"][0]["sentiment"]["score"], 0)


if __name__ == "__main__":
    unittest.main()
