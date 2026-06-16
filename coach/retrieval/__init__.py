"""Retrieval engine for the Purchasing Coach.

Pure-Python keyword and BM25 retrieval, no external dependencies.

Public API
----------
- :func:`tokenize`, :func:`stem`, :func:`ngrams`, :data:`STOPWORDS`
  — text tokenisation utilities.
- :class:`InvertedIndex` — postings-list based inverted index.
- :class:`BM25Ranker` — BM25 probabilistic scoring.
- :class:`CosineRanker` — TF-IDF cosine similarity.
- :func:`rrf_fusion` — Reciprocal Rank Fusion for combining rankings.
"""

from .tokenizer import STOPWORDS, ngrams, stem, tokenize
from .index import InvertedIndex
from .ranker import BM25Ranker, CosineRanker, rrf_fusion

__all__ = [
    "STOPWORDS",
    "tokenize",
    "stem",
    "ngrams",
    "InvertedIndex",
    "BM25Ranker",
    "CosineRanker",
    "rrf_fusion",
]
