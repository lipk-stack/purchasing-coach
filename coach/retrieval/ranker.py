"""Ranking algorithms for the Purchasing Coach retrieval engine.

Provides two complementary rankers and a fusion function:

* :class:`BM25Ranker` — classic BM25 probabilistic scoring.
* :class:`CosineRanker` — TF-IDF cosine similarity.
* :func:`rrf_fusion` — Reciprocal Rank Fusion to combine multiple rankings.

All implementations operate on an :class:`~coach.retrieval.index.InvertedIndex`
and use only the Python standard library.
"""

from __future__ import annotations

import math
from typing import Any

from .index import InvertedIndex
from .tokenizer import tokenize


class BM25Ranker:
    """BM25 scoring ranker.

    Implements the Okapi BM25 ranking function, which scores a document *d*
    for a query *q* as:

    .. math::

        \\text{score}(q, d) = \\sum_{q_i \\in q}
            \\text{IDF}(q_i) \\cdot
            \\frac{f(q_i, d) \\cdot (k_1 + 1)}
                 {f(q_i, d) + k_1 \\cdot \\left(1 - b + b \\cdot \\frac{|d|}{\\text{avgdl}}\\right)}

    Args:
        index: The inverted index to score against.
        k1:    Term-frequency saturation parameter (default 1.5).
               Higher values give more weight to term frequency.
        b:     Document-length normalisation parameter (default 0.75).
               0 disables length normalisation; 1 fully normalises.
    """

    def __init__(
        self,
        index: InvertedIndex,
        k1: float = 1.5,
        b: float = 0.75,
    ) -> None:
        self.index = index
        self.k1 = k1
        self.b = b

    def score(
        self, query: str, top_k: int = 10
    ) -> list[tuple[int, float, dict[str, Any]]]:
        """Score the *query* against every document in the index.

        Args:
            query: Free-text search query.
            top_k: Maximum number of results to return.

        Returns:
            A list of ``(doc_id, score, metadata)`` tuples sorted by
            descending score.  Only documents with a positive score are
            included.
        """
        if self.index.N == 0:
            return []

        query_tokens = tokenize(query)
        if not query_tokens:
            return []

        scores: dict[int, float] = {}
        avgdl = self.index.avgdl if self.index.avgdl > 0 else 1.0

        for qt in query_tokens:
            postings = self.index.postings.get(qt)
            if not postings:
                continue
            idf = self.index.idf(qt)
            for doc_id, tf_val in postings.items():
                doc_len = self.index.doc_lengths.get(doc_id, 0)
                # BM25 term score.
                numerator = tf_val * (self.k1 + 1.0)
                denominator = (
                    tf_val
                    + self.k1
                    * (1.0 - self.b + self.b * doc_len / avgdl)
                )
                term_score = idf * numerator / denominator
                scores[doc_id] = scores.get(doc_id, 0.0) + term_score

        # Sort by descending score, break ties by doc_id ascending.
        ranked = sorted(scores.items(), key=lambda x: (-x[1], x[0]))
        results: list[tuple[int, float, dict[str, Any]]] = []
        for doc_id, sc in ranked[:top_k]:
            if sc <= 0.0:
                break
            meta = self.index.documents.get(doc_id, {})
            results.append((doc_id, sc, meta))
        return results


class CosineRanker:
    """TF-IDF cosine similarity ranker.

    Represents each document and the query as TF-IDF vectors and computes
    the cosine similarity between them.  The IDF component uses the same
    BM25-variant formula stored on the index for consistency.

    Args:
        index: The inverted index to score against.
    """

    def __init__(self, index: InvertedIndex) -> None:
        self.index = index

    def score(
        self, query: str, top_k: int = 10
    ) -> list[tuple[int, float, dict[str, Any]]]:
        """Compute cosine similarity between the query and each document.

        The query TF-IDF vector is built from the tokenised query; each
        document's TF-IDF vector is derived from the postings list.  Only
        terms that appear in both the query and the document contribute to
        the dot product, so scoring is efficient even for large indices.

        Args:
            query: Free-text search query.
            top_k: Maximum number of results to return.

        Returns:
            A list of ``(doc_id, score, metadata)`` tuples sorted by
            descending cosine similarity.  Only documents with a positive
            similarity are included.
        """
        if self.index.N == 0:
            return []

        query_tokens = tokenize(query)
        if not query_tokens:
            return []

        # Build query TF map.
        qtf: dict[str, int] = {}
        for tok in query_tokens:
            qtf[tok] = qtf.get(tok, 0) + 1

        # Pre-compute query IDF weights and query vector norm.
        query_idf: dict[str, float] = {}
        for term in qtf:
            query_idf[term] = self.index.idf(term)

        query_norm_sq = sum(
            (qtf[t] * query_idf[t]) ** 2 for t in qtf
        )
        if query_norm_sq == 0.0:
            return []
        query_norm = math.sqrt(query_norm_sq)

        # For each candidate document, compute the dot product using only
        # the query terms (most terms will not appear in a given document).
        scores: dict[int, float] = {}
        for term, q_freq in qtf.items():
            postings = self.index.postings.get(term)
            if not postings:
                continue
            idf_val = query_idf[term]
            q_weight = q_freq * idf_val
            for doc_id, tf_val in postings.items():
                d_weight = tf_val * idf_val
                scores[doc_id] = scores.get(doc_id, 0.0) + q_weight * d_weight

        # Normalise by query norm and document vector norm.
        results: list[tuple[int, float, dict[str, Any]]] = []
        for doc_id, dot_product in scores.items():
            if dot_product <= 0.0:
                continue
            # Compute document vector norm for the terms it shares with query.
            doc_norm_sq = 0.0
            for term in qtf:
                tf_val = self.index.tf(term, doc_id)
                if tf_val > 0:
                    idf_val = query_idf[term]
                    doc_norm_sq += (tf_val * idf_val) ** 2
            if doc_norm_sq == 0.0:
                continue
            doc_norm = math.sqrt(doc_norm_sq)
            cosine = dot_product / (query_norm * doc_norm)
            meta = self.index.documents.get(doc_id, {})
            results.append((doc_id, cosine, meta))

        results.sort(key=lambda x: (-x[1], x[0]))
        return results[:top_k]


def rrf_fusion(
    *rankings: list[tuple[int, float, dict[str, Any]]],
    k: int = 60,
    top_k: int = 10,
) -> list[tuple[int, float, dict[str, Any]]]:
    """Reciprocal Rank Fusion (Cormack et al., 2009).

    Combines multiple ranked lists into a single consensus ranking.  Each
    document's RRF score is the sum of ``1 / (k + rank)`` across every
    input list where it appears, with *rank* being the 1-based position in
    that list.

    RRF is robust to the absolute score scales of the individual rankers,
    making it ideal for fusing BM25 and cosine results (which operate on
    very different numeric ranges).

    Args:
        *rankings: Two or more ranked result lists, each a sequence of
                   ``(doc_id, score, metadata)`` tuples.
        k:         Smoothing constant (default 60).  Higher values compress
                   the score range and reduce the advantage of top-ranked
                   items.
        top_k:     Maximum number of results to return.

    Returns:
        A merged list of ``(doc_id, rrf_score, metadata)`` tuples sorted
        by descending RRF score.  Metadata is taken from the first ranking
        in which the document appeared.
    """
    if not rankings:
        return []

    rrf_scores: dict[int, float] = {}
    metadata_map: dict[int, dict[str, Any]] = {}

    for ranking in rankings:
        for rank_0based, (doc_id, _score, meta) in enumerate(ranking):
            rank = rank_0based + 1  # 1-based rank
            rrf_scores[doc_id] = rrf_scores.get(doc_id, 0.0) + 1.0 / (k + rank)
            if doc_id not in metadata_map:
                metadata_map[doc_id] = meta

    ranked = sorted(rrf_scores.items(), key=lambda x: (-x[1], x[0]))
    results: list[tuple[int, float, dict[str, Any]]] = []
    for doc_id, rrf_score in ranked[:top_k]:
        results.append((doc_id, rrf_score, metadata_map.get(doc_id, {})))
    return results
