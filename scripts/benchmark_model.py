"""Benchmark FinBERT on the Financial PhraseBank dataset.

Financial PhraseBank is a standard, human-annotated corpus of financial
sentences labeled negative / neutral / positive. Reporting FinBERT's accuracy
and macro-F1 on it turns "I used a sentiment model" into "I evaluated one."

Implementation note
-------------------
Newer versions of the `datasets` library removed support for script-based
datasets, which breaks `load_dataset("financial_phrasebank", ...)`. Instead of
pinning an old library, we download the raw corpus zip directly from the
Hugging Face Hub and parse it ourselves. Each line in the corpus has the form:

    <sentence>@<label>

where <label> is one of: positive, negative, neutral.

Usage
-----
    python -m scripts.benchmark_model
    python -m scripts.benchmark_model --config sentences_allagree --sample 500
"""
from __future__ import annotations

import argparse
import io
import logging
import random
import zipfile

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(name)s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("benchmark")

REPO_ID = "takala/financial_phrasebank"
ZIP_FILENAME = "data/FinancialPhraseBank-v1.0.zip"

# Config name -> filename inside the zip. The configs differ by how many
# human annotators had to agree on the label for a sentence to be included.
CONFIG_TO_FILE = {
    "sentences_50agree": "FinancialPhraseBank-v1.0/Sentences_50Agree.txt",
    "sentences_66agree": "FinancialPhraseBank-v1.0/Sentences_66Agree.txt",
    "sentences_75agree": "FinancialPhraseBank-v1.0/Sentences_75Agree.txt",
    "sentences_allagree": "FinancialPhraseBank-v1.0/Sentences_AllAgree.txt",
}

VALID_LABELS = {"negative", "neutral", "positive"}
NAME2ID = {"negative": 0, "neutral": 1, "positive": 2}


def parse_phrasebank_lines(lines: list[str]) -> tuple[list[str], list[str]]:
    """Parse raw PhraseBank lines into (sentences, labels).

    Each valid line is '<sentence>@<label>'. We split on the *last* '@' in
    case a sentence itself contains the character, strip whitespace, and skip
    empty or malformed lines.
    """
    sentences: list[str] = []
    labels: list[str] = []
    for raw in lines:
        line = raw.strip()
        if not line or "@" not in line:
            continue
        sentence, _, label = line.rpartition("@")
        sentence = sentence.strip()
        label = label.strip().lower()
        if sentence and label in VALID_LABELS:
            sentences.append(sentence)
            labels.append(label)
    return sentences, labels


def load_phrasebank(config: str) -> tuple[list[str], list[str]]:
    """Download the corpus zip from the HF Hub and parse the chosen subset."""
    if config not in CONFIG_TO_FILE:
        raise ValueError(
            f"Unknown config '{config}'. Choose from: {sorted(CONFIG_TO_FILE)}"
        )
    from huggingface_hub import hf_hub_download

    logger.info("Downloading PhraseBank corpus from %s ...", REPO_ID)
    zip_path = hf_hub_download(
        repo_id=REPO_ID, filename=ZIP_FILENAME, repo_type="dataset"
    )
    with zipfile.ZipFile(zip_path) as zf:
        with zf.open(CONFIG_TO_FILE[config]) as fh:
            # The corpus is ISO-8859-1 (Latin-1) encoded.
            text = io.TextIOWrapper(fh, encoding="latin-1").read()
    sentences, labels = parse_phrasebank_lines(text.splitlines())
    if not sentences:
        raise RuntimeError("Parsed zero sentences — corpus format may have changed.")
    return sentences, labels


def main() -> None:
    parser = argparse.ArgumentParser(description="Benchmark FinBERT on PhraseBank")
    parser.add_argument(
        "--config",
        default="sentences_75agree",
        choices=sorted(CONFIG_TO_FILE),
        help="PhraseBank subset (annotator-agreement level).",
    )
    parser.add_argument(
        "--sample",
        type=int,
        default=None,
        help="Evaluate on a random sample of N sentences (default: all).",
    )
    args = parser.parse_args()

    from sklearn.metrics import accuracy_score, classification_report, f1_score

    from src.sentiment import get_scorer

    sentences, label_names = load_phrasebank(args.config)
    if args.sample and args.sample < len(sentences):
        rng = random.Random(42)
        idx = rng.sample(range(len(sentences)), args.sample)
        sentences = [sentences[i] for i in idx]
        label_names = [label_names[i] for i in idx]
    logger.info("Evaluating on %d sentences (%s).", len(sentences), args.config)

    y_true = [NAME2ID[l] for l in label_names]

    scorer = get_scorer()
    results = scorer.score_batch(sentences)
    y_pred = [NAME2ID[r["label"]] for r in results]

    acc = accuracy_score(y_true, y_pred)
    macro_f1 = f1_score(y_true, y_pred, average="macro")

    logger.info("=" * 52)
    logger.info("FinBERT on Financial PhraseBank (%s)", args.config)
    logger.info("Accuracy : %.4f", acc)
    logger.info("Macro F1 : %.4f", macro_f1)
    logger.info("=" * 52)
    print(
        classification_report(
            y_true,
            y_pred,
            labels=[0, 1, 2],
            target_names=["negative", "neutral", "positive"],
            digits=4,
        )
    )


if __name__ == "__main__":
    main()