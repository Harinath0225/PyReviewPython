"""Reference-based text similarity metrics: BLEU, METEOR and ROUGE.

Pure Python (NLTK is used for BLEU only when installed) so the same scores are
available to the Agent Lab evaluator, the scorecard and the ADK Web UI metrics.
All scores are in [0, 1]; an empty candidate or reference scores 0.
"""

from __future__ import annotations

import math
import re
from collections import Counter

# Keeps the O(n*m) longest-common-subsequence bounded for very long outputs.
_MAX_LCS_TOKENS = 1500


def _tokenize(text: str) -> list[str]:
    """Tokenizes string into lowercase alphanumeric words and symbols."""
    return re.findall(r"\w+|[^\w\s]", text.lower(), re.UNICODE)


def _words(text: str) -> list[str]:
    """Word-only tokens, as used by ROUGE (punctuation ignored)."""
    return re.findall(r"\w+", text.lower(), re.UNICODE)


# ---------------------------------------------------------------------------
# BLEU
# ---------------------------------------------------------------------------

def calculate_sentence_bleu(candidate_text: str, reference_text: str) -> float:
    """Calculates smoothed sentence BLEU (1 to 4 n-grams) with brevity penalty."""
    # Attempt to use nltk if available
    try:
        import nltk
        from nltk.translate.bleu_score import SmoothingFunction, sentence_bleu

        cand_tokens = _tokenize(candidate_text)
        ref_tokens = _tokenize(reference_text)
        if not cand_tokens or not ref_tokens:
            return 0.0

        chencherry = SmoothingFunction()
        score = sentence_bleu([ref_tokens], cand_tokens, smoothing_function=chencherry.method1)
        return float(score)
    except Exception:
        pass

    # Pure Python robust fallback
    cand = _tokenize(candidate_text)
    ref = _tokenize(reference_text)
    if not cand or not ref:
        return 0.0

    c_len = len(cand)
    r_len = len(ref)

    # Brevity penalty
    if c_len > r_len:
        bp = 1.0
    else:
        bp = math.exp(1.0 - (r_len / max(1, c_len)))

    precisions = []
    for n in range(1, 5):
        cand_ngrams: dict[tuple[str, ...], int] = {}
        for i in range(len(cand) - n + 1):
            ngram = tuple(cand[i : i + n])
            cand_ngrams[ngram] = cand_ngrams.get(ngram, 0) + 1

        ref_ngrams: dict[tuple[str, ...], int] = {}
        for i in range(len(ref) - n + 1):
            ngram = tuple(ref[i : i + n])
            ref_ngrams[ngram] = ref_ngrams.get(ngram, 0) + 1

        total_cand = sum(cand_ngrams.values())
        if total_cand == 0:
            precisions.append(1.0 / (2**n))
            continue

        clipped_matches = sum(
            min(count, ref_ngrams.get(ngram, 0)) for ngram, count in cand_ngrams.items()
        )
        # Smoothing
        precision = (clipped_matches + 0.1) / (total_cand + 0.1)
        precisions.append(precision)

    geo_mean = math.exp(sum(0.25 * math.log(p) for p in precisions))
    return float(min(1.0, max(0.0, bp * geo_mean)))


# ---------------------------------------------------------------------------
# METEOR
# ---------------------------------------------------------------------------

def calculate_meteor_score(candidate_text: str, reference_text: str) -> float:
    """Calculates METEOR score (unigram precision & recall harmonic mean with chunk penalty)."""
    cand = _tokenize(candidate_text)
    ref = _tokenize(reference_text)
    if not cand or not ref:
        return 0.0

    # Unigram matches (exact + basic stem)
    ref_pool = list(ref)
    matched_indices_cand = []
    for idx, c_word in enumerate(cand):
        matched = False
        if c_word in ref_pool:
            ref_pool.remove(c_word)
            matched = True
        else:
            # Simple stemming heuristic (strip s, ed, ing)
            c_stem = re.sub(r"(ing|ed|es|s)$", "", c_word)
            for r_word in ref_pool:
                r_stem = re.sub(r"(ing|ed|es|s)$", "", r_word)
                if len(c_stem) > 2 and c_stem == r_stem:
                    ref_pool.remove(r_word)
                    matched = True
                    break
        if matched:
            matched_indices_cand.append(idx)

    m = len(matched_indices_cand)
    if m == 0:
        return 0.0

    p = m / len(cand)
    r = m / len(ref)

    # Weighted harmonic mean with alpha = 0.9 (9x weight on recall)
    f_mean = (10.0 * p * r) / (r + 9.0 * p) if (r + 9.0 * p) > 0 else 0.0

    # Chunk fragmentation penalty
    # Count contiguous chunks of matched indices
    chunks = 0
    prev = None
    for idx in matched_indices_cand:
        if prev is None or idx != prev + 1:
            chunks += 1
        prev = idx

    penalty = 0.5 * ((chunks / m) ** 3)
    score = f_mean * (1.0 - penalty)
    return float(min(1.0, max(0.0, score)))


# ---------------------------------------------------------------------------
# ROUGE
# ---------------------------------------------------------------------------

def _f1(overlap: float, cand_total: int, ref_total: int) -> float:
    if overlap <= 0 or cand_total == 0 or ref_total == 0:
        return 0.0
    precision = overlap / cand_total
    recall = overlap / ref_total
    return 2 * precision * recall / (precision + recall)


def calculate_rouge_n(candidate_text: str, reference_text: str, n: int = 1) -> float:
    """ROUGE-N F1: clipped n-gram overlap between candidate and reference."""
    cand = _words(candidate_text)
    ref = _words(reference_text)
    cand_grams = Counter(tuple(cand[i : i + n]) for i in range(len(cand) - n + 1))
    ref_grams = Counter(tuple(ref[i : i + n]) for i in range(len(ref) - n + 1))
    overlap = sum(min(count, ref_grams[gram]) for gram, count in cand_grams.items())
    return _f1(overlap, sum(cand_grams.values()), sum(ref_grams.values()))


def _lcs_length(a: list[str], b: list[str]) -> int:
    if not a or not b:
        return 0
    previous = [0] * (len(b) + 1)
    for token_a in a:
        current = [0]
        for j, token_b in enumerate(b, start=1):
            current.append(previous[j - 1] + 1 if token_a == token_b else max(previous[j], current[j - 1]))
        previous = current
    return previous[-1]


def calculate_rouge_l(candidate_text: str, reference_text: str) -> float:
    """ROUGE-L F1: longest common subsequence, so word order matters."""
    cand = _words(candidate_text)[:_MAX_LCS_TOKENS]
    ref = _words(reference_text)[:_MAX_LCS_TOKENS]
    return _f1(_lcs_length(cand, ref), len(cand), len(ref))


def calculate_rouge(candidate_text: str, reference_text: str) -> dict[str, float]:
    """ROUGE-1, ROUGE-2 and ROUGE-L F1 scores."""
    return {
        "rouge1": calculate_rouge_n(candidate_text, reference_text, 1),
        "rouge2": calculate_rouge_n(candidate_text, reference_text, 2),
        "rougeL": calculate_rouge_l(candidate_text, reference_text),
    }


def reference_scores(candidate_text: str, reference_text: str) -> dict[str, float]:
    """Every reference-based metric at once, rounded for storage and display."""
    scores = {
        "bleu": calculate_sentence_bleu(candidate_text, reference_text),
        "meteor": calculate_meteor_score(candidate_text, reference_text),
        **calculate_rouge(candidate_text, reference_text),
    }
    return {name: round(value, 4) for name, value in scores.items()}
