# Local financial news pipeline

A dependency-free Python pipeline that reads local news JSON, normalizes articles,
removes duplicate content, and produces a JSON report with rule-based sentiment.
Requires Python 3.10 or later. No network calls, external APIs, API keys, packages,
or model downloads are used. `samples/articles.json` is fictional;
`samples/asia_hedge_funds.json` contains the user-supplied Reuters article.

From the project root:

```sh
python -m news_pipeline samples/articles.json report.json --verbose
python -m unittest discover -s tests -v
```

The sample produces 3 articles from 4 inputs, removes 1 duplicate, and assigns
one positive, one negative, and one neutral label.

## Repository structure and execution flow

```text
news_pipeline/
    __init__.py          Public Python API
    __main__.py          CLI arguments, logging, and error reporting
    io.py                Read JSON, invoke processing, atomically write report
    pipeline.py          Validate, normalize, deduplicate, and score sentiment
samples/
    articles.json        Fictional input with a duplicate
    asia_hedge_funds.json User-supplied negative article
tests/
    test_pipeline.py     Processing, file API, CLI, and trace tests
    test_hedge_funds.py   Reuters sentiment regression
    test_sentiment_robustness.py  Negation, irony warnings, and bias checks
README.md
AGENTS.md
.gitignore
report.json              Generated output; ignored by Git
```

There is one implementation: the `news_pipeline` package. Run it with
`python -m news_pipeline`; the former root-level `news_pipeline.py` was removed
because it duplicated the logic and produced a different report schema.

```text
samples/*.json (one input file per invocation)
    -> __main__.py: parse input/output paths
    -> io.py: read and decode JSON
    -> pipeline.py: validate and normalize each article
                   -> discard duplicate title/body pairs
                   -> score each retained article
                   -> build articles and summary
    -> io.py: atomically write report.json
```

Use `--verbose` to monitor these stages on stderr, including zero-based article
indices, removed duplicates, sentiment labels/scores, and final counts. Logs do
not include article bodies and do not change the JSON output. Omit the flag for
the normal one-line completion message.

To process the Reuters article instead:

```sh
python -m news_pipeline samples/asia_hedge_funds.json report.json --verbose
```

This replaces `report.json` with one negative article (score `-10`). Each command
processes the named file only; reports are replaced rather than appended.

## Input

Supply a UTF-8 JSON array (a UTF-8 BOM is accepted). Each article must contain
four non-empty string fields; extra fields are ignored:

```json
[
  {
    "title": "Acme reports strong growth",
    "source": "Example Finance",
    "timestamp": "2026-10-14T09:30:00+08:00",
    "body": "Acme profits rise."
  }
]
```

Timestamps must be ISO 8601 datetimes with a `T` separator and an explicit UTC
offset or `Z`. Dates without a time and datetimes without a timezone are rejected.
An empty array is valid. Invalid JSON, fields, or timestamps fail the entire run
with exit code 1 and an error on stderr identifying the article index (zero-based)
and field where applicable. Argument errors use exit code 2.

## Processing rules

1. Normalize text using Unicode NFKC, trim it, and collapse whitespace. Display
   casing and punctuation are preserved. Input is plain text; HTML is not stripped.
2. Convert timestamps to UTC, using `Z` and preserving fractional seconds.
3. Compare normalized, case-folded title **and** body pairs. Keep the first article,
   including its source and timestamp, in input order. Source and timestamp do not
   affect duplicate detection. Different bodies remain distinct even when titles
   match. This is exact content matching after normalization, not fuzzy matching.
   Every record is validated, including duplicates.
4. Score title and body together using whole-word, case-insensitive English
   vocabulary matches after Unicode normalization. Each occurrence contributes
   +1 or -1; repeated words count. A negator (`not`, `no`, `never`, `neither`,
   `nor`, `without`, or an `n't` contraction) reverses polarity for the next
   three words. Punctuation, contrast words (`but`, `however`, `yet`, `although`),
   and title/body boundaries end that scope. `Not only` is treated as emphasis.
   A positive score means `positive`, a negative score means `negative`, and zero
   means `neutral` (including ties and no matches). The complete vocabulary is in
   `news_pipeline/pipeline.py` as `POSITIVE_WORDS` and `NEGATIVE_WORDS`.

This is a bounded heuristic, not a general article-understanding model. It
handles selected English financial and general sentiment words and simple
negation, but cannot reliably interpret arbitrary articles, implicit irony,
complex negation, quotation attribution, financial context, or other languages.
For example, `losses fall` still scores negative. Negating a negative word also
does not necessarily imply a positive real-world outcome.

Explicit cues (`/s`, `yeah right`, `so-called`, `sarcastic`, `sarcastically`)
add a `possible_irony` warning. These cues can occur literally and implicit irony
can lack them. The returned label is still the lexical result, not an inferred
ironic meaning. No vocabulary matches produces a neutral label with a
`no_lexical_evidence` warning; this distinguishes missing evidence from a tie.
Either warning sets `needs_review` to true. A false review flag does not certify
accuracy. Summary counts include flagged articles using their lexical labels.
Labels describe lexical evidence and should not be treated as investment signals.

## Report

The report contains `summary` with `input_count`, `output_count`,
`duplicates_removed`, and `sentiment_counts`, plus an `articles` array. Each
article contains its four normalized fields, a stable SHA-256 `id` derived from
the case-folded title/body pair, and a `sentiment` object containing `label`,
`score`, `positive_matches`, `negative_matches`, `needs_review`, and `warnings`.
Match lists retain the words' literal vocabulary polarity, while the score
includes negation: `not strong` has `positive_matches: ["strong"]` and score `-1`.

Output is deterministic, indented UTF-8 JSON. Its parent directory must already
exist. A successful run atomically replaces an existing output file; processing
or write failures leave any existing report intact. Input and output must be
different files. The pipeline loads the input into memory and is intended for
local datasets that fit in memory.

The core can also be called directly:

```python
from news_pipeline import process_articles

report = process_articles(articles)  # list of dictionaries; raises ValueError
```

To run the same read/process/write flow from Python:

```python
from news_pipeline import run_pipeline

report = run_pipeline("samples/articles.json", "report.json")
```

Tests cover normalization, UTC conversion, validation, duplicate retention,
sentiment scoring, deterministic reports, sample data, and CLI success/failure.

## Sentiment robustness: red/green TDD

Run the behavioral checks independently with:

```sh
python -m unittest discover -s tests -p test_sentiment_robustness.py -v
```

The tests were added before the scoring changes. The red run passed all 21
existing tests but produced 8 assertion failures and 8 missing-field errors
within the new subtests. After implementation, all 29 test methods passed.
The new checks cover selected non-financial articles, negation/contractions,
scope boundaries, explicit irony cues, absent lexical evidence (including Chinese
and emoji text), and case/Unicode normalization.

Counterfactual checks replace names, gender descriptions, religious identities,
nationalities, and racial descriptions in otherwise identical positive, negative,
and neutral text. Separate checks replace the source, including sources whose
names contain sentiment words. Results must remain identical. These checks pass;
they do not prove the scorer or its hand-selected vocabulary is bias-free. This
small, synthetic regression suite is not a representative accuracy/fairness
benchmark. Broader claims require independently labeled articles across domains,
languages, identities, and implicit irony, with results reported per group.

The user-supplied Reuters hedge fund article is stored locally in
`samples/asia_hedge_funds.json` and tested for a negative label through
both the Python API and CLI. Its publication timestamp is used; the supplied
update date has no time. Copied page text is retained with whitespace cleaned.
Unlike the fictional sample news, this fixture comes from the supplied article.
Run just this regression with:

```sh
python -m unittest discover -s tests -p test_hedge_funds.py -v
```
