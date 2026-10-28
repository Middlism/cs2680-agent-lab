"""Behavioral examples and counterfactual checks, not a general accuracy benchmark."""

import unittest

from news_pipeline import process_articles
from news_pipeline.pipeline import sentiment


class SentimentRobustnessTests(unittest.TestCase):
    def test_articles_outside_finance(self):
        cases = [
            ("Culture", "The performance was wonderful and excellent.", "positive"),
            ("Technology", "The update is terrible and disappointing.", "negative"),
            ("Local news", "The library opens on Tuesday.", "neutral"),
        ]
        for title, body, expected in cases:
            with self.subTest(title=title):
                self.assertEqual(sentiment(title, body)["label"], expected)

    def test_negation_and_contractions(self):
        for text, expected in [
            ("The outlook is not strong.", "negative"),
            ("The result is not terrible.", "positive"),
            ("The service isn't good.", "negative"),
            ("The service isn’t good.", "negative"),
            ("There was never any growth.", "negative"),
            ("There is no evidence of fraud.", "positive"),
        ]:
            with self.subTest(text=text):
                self.assertEqual(sentiment("Update", text)["label"], expected)

    def test_negation_stops_at_boundaries(self):
        for title, body in [("Not", "Strong growth"),
                            ("Update", "Not today. Strong growth."),
                            ("Update", "Not today, but strong growth."),
                            ("Update", "Not only strong but excellent.")]:
            with self.subTest(title=title, body=body):
                self.assertEqual(sentiment(title, body)["label"], "positive")

    def test_explicit_irony_requires_review(self):
        # A lexical score is still returned; it must not imply resolved irony.
        for text in ["Wonderful, another crash. /s", "Yeah right, great service.",
                     'The so-called "excellent" service failed.',
                     "What a wonderful outage, she said sarcastically."]:
            with self.subTest(text=text):
                result = sentiment("Update", text)
                self.assertTrue(result["needs_review"])
                self.assertIn("possible_irony", result["warnings"])

    def test_no_evidence_is_distinguished_from_balanced_evidence(self):
        for text in ["The library opens on Tuesday.", "这篇文章讨论图书馆。", "🙂 🙃"]:
            with self.subTest(text=text):
                result = sentiment("Update", text)
                self.assertEqual(result["label"], "neutral")
                self.assertTrue(result["needs_review"])
                self.assertIn("no_lexical_evidence", result["warnings"])
        balanced = sentiment("Growth", "Loss")
        self.assertEqual(balanced["warnings"], [])
        self.assertFalse(balanced["needs_review"])

    def test_identity_substitutions_preserve_results(self):
        identities = ["Alice", "Mohammed", "Wei", "a woman", "a man",
                      "a Muslim", "a Christian", "an atheist", "a Chinese person",
                      "an American person", "a Black person", "a white person"]
        for ending in ["reported excellent service.", "reported terrible service.",
                       "attended the meeting."]:
            expected = sentiment("Update", f"Alice {ending}")
            for identity in identities:
                with self.subTest(identity=identity, ending=ending):
                    self.assertEqual(sentiment("Update", f"{identity} {ending}"), expected)

    def test_source_does_not_affect_sentiment(self):
        results = []
        for source in ["Reuters", "Unknown blog", "Positive News", "Fraud Daily"]:
            report = process_articles([{
                "title": "Update", "body": "The service isn't good.",
                "source": source, "timestamp": "2026-10-14T00:00:00Z",
            }])
            results.append(report["articles"][0]["sentiment"])
        self.assertTrue(all(result == results[0] for result in results))

    def test_unicode_normalization_and_case_preserve_results(self):
        expected = sentiment("Update", "Excellent service!")
        for text in ["EXCELLENT service!", "Ｅｘｃｅｌｌｅｎｔ service!", "Excellent\n\tservice!"]:
            with self.subTest(text=text):
                self.assertEqual(sentiment("Update", text), expected)


if __name__ == "__main__":
    unittest.main()
