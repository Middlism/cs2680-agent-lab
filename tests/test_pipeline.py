import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from news_pipeline import process_articles, run_pipeline
from news_pipeline.pipeline import sentiment


ROOT = Path(__file__).resolve().parents[1]


def article(**changes):
    result = {
        "title": "Company update", "source": "Local Desk",
        "timestamp": "2026-10-14T09:30:00+08:00", "body": "Meeting on Tuesday.",
    }
    result.update(changes)
    return result


class PipelineTests(unittest.TestCase):
    def test_normalization_and_no_mutation(self):
        raw = [article(title="  Ａcme\tupdate\n", source=" Local  Desk ",
                       body="Line one.\n\tLine two.")]
        before = copy.deepcopy(raw)
        item = process_articles(raw)["articles"][0]
        self.assertEqual(item["title"], "Acme update")
        self.assertEqual(item["source"], "Local Desk")
        self.assertEqual(item["body"], "Line one. Line two.")
        self.assertEqual(item["timestamp"], "2026-10-14T01:30:00Z")
        self.assertEqual(raw, before)

    def test_duplicates_ignore_case_whitespace_source_and_timestamp(self):
        first = article()
        second = article(title=" COMPANY  UPDATE ", body="meeting on tuesday.",
                         source="Another Desk", timestamp="2026-10-15T00:00:00Z")
        report = process_articles([first, second, second])
        self.assertEqual(report["summary"]["duplicates_removed"], 2)
        self.assertEqual(report["articles"][0]["source"], "Local Desk")
        self.assertEqual(report["summary"]["output_count"], 1)

    def test_different_bodies_and_titles_are_preserved_in_order(self):
        report = process_articles([article(), article(body="New details."),
                                   article(title="Other update")])
        self.assertEqual(report["summary"]["output_count"], 3)
        self.assertEqual(report["articles"][1]["body"], "New details.")
        self.assertEqual(len({a["id"] for a in report["articles"]}), 3)

    def test_deterministic_ids_and_report(self):
        self.assertEqual(process_articles([article()]), process_articles([article()]))
        first = process_articles([article()])["articles"][0]["id"]
        second = process_articles([article(source="Other")])["articles"][0]["id"]
        self.assertEqual(first, second)
        self.assertEqual(len(first), 64)

    def test_sentiment_labels_counts_and_ties(self):
        cases = [("Strong growth", "Profits rise", "positive", 4),
                 ("Weak demand", "Losses fall", "negative", -3),
                 ("Growth", "Loss", "neutral", 0),
                 ("Meeting", "Tuesday", "neutral", 0)]
        for title, body, label, score in cases:
            with self.subTest(title=title):
                result = sentiment(title, body)
                self.assertEqual(result["label"], label)
                self.assertEqual(result["score"], score)

    def test_matches_are_whole_words_and_repetitions_count(self):
        result = sentiment("PROFIT profit!", "profitable waterfall")
        self.assertEqual(result["positive_matches"], ["profit", "profit"])
        self.assertEqual(result["negative_matches"], [])

    def test_empty_input(self):
        report = process_articles([])
        self.assertEqual(report["articles"], [])
        self.assertEqual(report["summary"], {
            "input_count": 0, "output_count": 0, "duplicates_removed": 0,
            "sentiment_counts": {"positive": 0, "negative": 0, "neutral": 0},
        })

    def test_invalid_shapes(self):
        for raw in ({"articles": []}, None, "text", [None], [42]):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                process_articles(raw)

    def test_missing_blank_and_non_string_fields(self):
        for field in ("title", "source", "timestamp", "body"):
            for value in (None, 42, [], "", " \n\t"):
                with self.subTest(field=field, value=value):
                    with self.assertRaisesRegex(ValueError, rf"article\[0\].{field}"):
                        process_articles([article(**{field: value})])
            raw = article()
            del raw[field]
            with self.assertRaises(ValueError):
                process_articles([raw])

    def test_invalid_timestamps_and_invalid_duplicate(self):
        for value in ("yesterday", "2026-10-14", "2026-10-14T10:00:00",
                      "2026-02-30T00:00:00Z", "2026-10-14T10:00:00+25:00"):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, "timestamp"):
                process_articles([article(), article(timestamp=value)])

    def test_fractional_seconds_and_negative_offset(self):
        result = process_articles([article(timestamp="2026-10-14T23:30:00.123-02:00")])
        self.assertEqual(result["articles"][0]["timestamp"], "2026-10-15T01:30:00.123000Z")

    def test_sample_summary(self):
        report = process_articles(json.loads((ROOT / "samples/articles.json").read_text()))
        self.assertEqual(report["summary"], {
            "input_count": 4, "output_count": 3, "duplicates_removed": 1,
            "sentiment_counts": {"positive": 1, "negative": 1, "neutral": 1},
        })


class CLITests(unittest.TestCase):
    def run_cli(self, *args):
        return subprocess.run([sys.executable, "-m", "news_pipeline", *map(str, args)],
                              cwd=ROOT, capture_output=True, text=True)

    def test_cli_sample(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "report.json"
            result = self.run_cli(ROOT / "samples/articles.json", output)
            self.assertEqual(result.returncode, 0, result.stderr)
            report = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(report["summary"]["output_count"], 3)
            self.assertEqual(list(Path(directory).iterdir()), [output])

    def test_verbose_traces_flow_without_changing_report(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "report.json"
            normal = self.run_cli(ROOT / "samples/articles.json", output)
            self.assertEqual(normal.returncode, 0, normal.stderr)
            expected = output.read_bytes()
            self.assertEqual(normal.stderr, "")
            traced = self.run_cli(ROOT / "samples/articles.json", output, "--verbose")
            self.assertEqual(traced.returncode, 0, traced.stderr)
            self.assertEqual(output.read_bytes(), expected)
            stages = ["Reading JSON", "Processing 4 input articles",
                      "article[0]: validated and normalized", "article[0]: sentiment=",
                      "article[1]: duplicate removed", "Completed: 3 kept",
                      "Writing report", "Report saved successfully"]
            positions = [traced.stderr.index(stage) for stage in stages]
            self.assertEqual(positions, sorted(positions))

    def test_file_api_matches_core_and_written_report(self):
        with tempfile.TemporaryDirectory() as directory:
            source = ROOT / "samples/articles.json"
            output = Path(directory) / "report.json"
            result = run_pipeline(source, output)
            expected = process_articles(json.loads(source.read_text(encoding="utf-8")))
            self.assertEqual(result, expected)
            self.assertEqual(json.loads(output.read_text(encoding="utf-8")), expected)

    def test_errors_preserve_existing_output(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "input.json"
            output = Path(directory) / "report.json"
            output.write_text("original", encoding="utf-8")
            for content in ("{broken", '[{"title": "missing fields"}]'):
                source.write_text(content, encoding="utf-8")
                result = self.run_cli(source, output)
                self.assertEqual(result.returncode, 1)
                self.assertIn("error:", result.stderr)
                self.assertNotIn("Traceback", result.stderr)
                self.assertEqual(output.read_text(), "original")

    def test_missing_input_and_output_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            missing = Path(directory) / "missing" / "report.json"
            self.assertEqual(self.run_cli(missing, Path(directory) / "out.json").returncode, 1)
            result = self.run_cli(ROOT / "samples/articles.json", missing)
            self.assertEqual(result.returncode, 1)
            self.assertNotIn("Traceback", result.stderr)

    def test_reject_input_as_output(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "input.json"
            source.write_text("[]", encoding="utf-8")
            self.assertEqual(self.run_cli(source, source).returncode, 1)
            self.assertEqual(source.read_text(), "[]")


if __name__ == "__main__":
    unittest.main()
