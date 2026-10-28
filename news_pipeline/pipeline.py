"""Validation, normalization, deduplication, and lexical sentiment scoring."""

import hashlib
import json
import logging
import re
import unicodedata
from datetime import datetime, timezone


POSITIVE_WORDS = frozenset({
    "beat", "beats", "boom", "gain", "gains", "growth", "improve", "improved",
    "profit", "profits", "rally", "record", "rise", "rises", "strong", "surge",
    "surges", "upgrade", "upgraded",
    "excellent", "good", "great", "happy", "success", "successful", "wonderful",
})
NEGATIVE_WORDS = frozenset({
    "bankruptcy", "crash", "decline", "declines", "default", "downgrade",
    "downgraded", "drop", "drops", "fall", "falls", "fraud", "loss", "losses",
    "miss", "misses", "recession", "slump", "weak",
    "declined", "drawdown", "drawdowns", "dropping", "eroded", "fell",
    "lost", "pullback", "retreated", "selloff", "selloffs", "slumped",
    "awful", "bad", "disappointing", "failure", "horrible", "sad", "terrible",
})
NEGATORS = frozenset({"not", "no", "never", "neither", "nor", "without"})
CLAUSE_BREAKS = frozenset({"but", "however", "yet", "although"})
TOKEN_PATTERN = re.compile(r"[^\W\d_]+(?:'[^\W\d_]+)*|[^\w\s]", re.UNICODE)
IRONY_PATTERN = re.compile(
    r"(?<!\w)/s\b|\byeah\s*,?\s*right\b|\bso[ -]called\b|\bsarcastic(?:ally)?\b"
)
FIELDS = ("title", "source", "timestamp", "body")
logger = logging.getLogger(__name__)


def normalize_text(value: str) -> str:
    """Apply Unicode NFKC and collapse all whitespace to single spaces."""
    return " ".join(unicodedata.normalize("NFKC", value).split())


def normalize_timestamp(value: str) -> str:
    """Require an ISO 8601 datetime with offset and return UTC with a Z suffix."""
    value = value.strip()
    if not re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}", value):
        raise ValueError("timestamp must be an ISO 8601 datetime with a timezone")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.utcoffset() is None:
            raise ValueError("missing timezone")
        return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    except (ValueError, OverflowError) as exc:
        raise ValueError("timestamp must be a valid ISO 8601 datetime with a timezone") from exc


def sentiment(title: str, body: str) -> dict:
    """Score English lexical evidence with a bounded, three-word negation scope.

    Match lists retain literal vocabulary polarity; score applies negation.
    Warnings indicate selected limitations, not calibrated model confidence.
    """
    positive, negative, warnings = [], [], []
    score = 0
    # Reset scope between fields so a headline cannot negate the article body.
    for field in (title, body):
        text = normalize_text(field).casefold().replace("\u2019", "'")
        if IRONY_PATTERN.search(text) and "possible_irony" not in warnings:
            warnings.append("possible_irony")
        tokens = TOKEN_PATTERN.findall(text)
        remaining = 0
        for index, token in enumerate(tokens):
            if not token[0].isalpha() or token in CLAUSE_BREAKS:
                remaining = 0
                continue
            if token in NEGATORS or token.endswith("n't"):
                # "Not only good" expresses emphasis, not a negation of good.
                if token == "not" and tokens[index + 1:index + 2] == ["only"]:
                    continue
                remaining = 3
                continue
            polarity = 0
            if token in POSITIVE_WORDS:
                positive.append(token)
                polarity = 1
            elif token in NEGATIVE_WORDS:
                negative.append(token)
                polarity = -1
            score += -polarity if remaining else polarity
            remaining = max(0, remaining - 1)
    if not positive and not negative:
        warnings.append("no_lexical_evidence")
    return {
        "label": "positive" if score > 0 else "negative" if score < 0 else "neutral",
        "score": score,
        "positive_matches": positive,
        "negative_matches": negative,
        "needs_review": bool(warnings),
        "warnings": warnings,
    }


def process_articles(data: object) -> dict:
    """Process a JSON array; keep the first instance of each title/body pair.

    Raises ValueError for invalid input. Extra article fields are ignored.
    Input objects are never mutated. Output order follows input order.
    """
    if not isinstance(data, list):
        raise ValueError("input must be a JSON array of articles")
    logger.info("Processing %d input articles", len(data))
    articles = []
    seen = set()
    duplicates = 0
    counts = {"positive": 0, "negative": 0, "neutral": 0}
    for index, raw in enumerate(data):
        prefix = f"article[{index}]"
        if not isinstance(raw, dict):
            raise ValueError(f"{prefix} must be an object")
        article = {}
        for field in FIELDS:
            value = raw.get(field)
            if not isinstance(value, str) or not normalize_text(value):
                raise ValueError(f"{prefix}.{field} must be a non-empty string")
            article[field] = normalize_text(value)
        try:
            article["timestamp"] = normalize_timestamp(article["timestamp"])
        except ValueError as exc:
            raise ValueError(f"{prefix}.{exc}") from exc
        logger.info("%s: validated and normalized", prefix)
        # JSON encoding prevents ambiguity between title/body boundaries.
        key = json.dumps(
            [article["title"].casefold(), article["body"].casefold()],
            ensure_ascii=False, separators=(",", ":"),
        )
        if key in seen:
            duplicates += 1
            logger.info("%s: duplicate removed", prefix)
            continue
        seen.add(key)
        article["id"] = hashlib.sha256(key.encode("utf-8")).hexdigest()
        article["sentiment"] = sentiment(article["title"], article["body"])
        logger.info("%s: sentiment=%s score=%d", prefix,
                    article["sentiment"]["label"], article["sentiment"]["score"])
        counts[article["sentiment"]["label"]] += 1
        articles.append(article)
    logger.info("Completed: %d kept, %d duplicates removed; sentiment counts=%s",
                len(articles), duplicates, counts)
    return {
        "summary": {
            "input_count": len(data),
            "output_count": len(articles),
            "duplicates_removed": duplicates,
            "sentiment_counts": counts,
        },
        "articles": articles,
    }
