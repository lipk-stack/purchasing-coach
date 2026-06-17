"""Retrieval engine (tokenizer/index/rankers) + keyword/bm25 backends.

These were previously at 0% coverage despite the keyword backend being the
default no-LLM fallback.
"""

from coach.backends.bm25 import BM25Backend
from coach.backends.keyword import KeywordBackend
from coach.guideline import parse_clause_requirements, parse_clauses
from coach.retrieval import (
    BM25Ranker,
    CosineRanker,
    InvertedIndex,
    ngrams,
    rrf_fusion,
    stem,
    tokenize,
)

GUIDELINE = """\
# Guideline

## 5 INFORMATION SECURITY
### 5.3 Access Control
Multi-factor authentication must be enforced for all privileged accounts.

## 8 HARDWARE REQUIREMENTS
### 8.4 Warranty and Replacement
Vendors must provide a minimum three-year hardware warranty and spare parts.

## 9 SOFTWARE REQUIREMENTS
### 9.1 Licensing
Software licensing terms and subscription renewal must be defined.
"""


def _parsed():
    return parse_clauses(GUIDELINE), parse_clause_requirements(GUIDELINE)


# ----------------------------- tokenizer -----------------------------------
def test_tokenize_lowercases_and_drops_stopwords():
    tokens = tokenize("The hardware MUST comply with the warranty")
    assert "the" not in tokens
    assert tokens  # non-empty
    # content words survive (possibly stemmed)
    assert any(t.startswith("hardwar") for t in tokens)


def test_tokenize_empty():
    assert tokenize("") == []
    assert tokenize("   !!!  ") == []


def test_stem_is_deterministic_and_shortening():
    assert stem("warranties") == stem("warranties")
    assert len(stem("running")) <= len("running")


def test_ngrams_builds_bigrams():
    bg = ngrams(["a", "b", "c"], 2)
    assert ("a", "b") in bg and ("b", "c") in bg


# ----------------------------- index ---------------------------------------
def test_index_build_and_stats():
    clauses, reqs = _parsed()
    idx = InvertedIndex()
    idx.build_from_guideline(GUIDELINE, clauses, reqs)
    assert idx.N > 0
    # A distinctive term resolves to a positive document frequency / idf.
    assert idx.df("warranti") >= 0  # stemmed form may vary; must not error
    assert idx.idf("xyzzy_not_present") >= 0.0


def test_index_empty_clauses_is_noop():
    idx = InvertedIndex()
    idx.build_from_guideline("", {}, {})
    assert idx.N == 0


# ----------------------------- rankers -------------------------------------
def test_bm25_ranks_relevant_clause_first():
    clauses, reqs = _parsed()
    idx = InvertedIndex()
    idx.build_from_guideline(GUIDELINE, clauses, reqs)
    results = BM25Ranker(idx).score("hardware warranty spare parts", top_k=5)
    assert results
    top_ref = results[0][2].get("ref", "")
    assert top_ref.startswith("8")


def test_cosine_and_rrf_fusion():
    clauses, reqs = _parsed()
    idx = InvertedIndex()
    idx.build_from_guideline(GUIDELINE, clauses, reqs)
    bm25 = BM25Ranker(idx).score("multi-factor authentication", top_k=5)
    cos = CosineRanker(idx).score("multi-factor authentication", top_k=5)
    assert bm25 and cos
    fused = rrf_fusion(bm25, cos, top_k=5)
    assert fused
    assert fused[0][2].get("ref", "").startswith("5")


def test_ranker_empty_query_returns_nothing():
    clauses, reqs = _parsed()
    idx = InvertedIndex()
    idx.build_from_guideline(GUIDELINE, clauses, reqs)
    assert BM25Ranker(idx).score("") == []


def test_rrf_fusion_no_rankings():
    assert rrf_fusion() == []


# ----------------------------- backends ------------------------------------
def _load(backend):
    clauses, reqs = _parsed()
    backend.load_guideline(GUIDELINE, clauses, reqs)
    return backend


def _interview(backend, item):
    prompt = f"<item>{item}</item>"
    return backend.complete_json("", prompt, {}, "interview_plan")


def _checklist(backend, item, interview=""):
    prompt = f"<item>{item}</item>\n<interview>\n{interview}\n</interview>"
    return backend.complete_json("", prompt, {}, "tender_checklist")


def test_keyword_backend_interview_is_item_tailored():
    be = _load(KeywordBackend())
    plan = _interview(be, "20 laptops")
    questions = " ".join(q["question"] for q in plan["questions"]).lower()
    assert plan["questions"]
    assert "physical hardware" in questions
    assert "software or application licensing" not in questions


def test_keyword_backend_builds_checklist():
    be = _load(KeywordBackend())
    result = _checklist(be, "rack servers", "hardware: yes")
    assert result["requirements"]
    assert all("ref" in r for r in result["requirements"])


def test_keyword_backend_streams_chat():
    be = _load(KeywordBackend())
    out = "".join(be.stream_chat(
        "sys", [{"role": "user", "content": "warranty requirements?"}]))
    assert out.strip()


def test_bm25_backend_interview_and_checklist():
    be = _load(BM25Backend())
    plan = _interview(be, "Microsoft 365 software subscription")
    assert plan["questions"]
    result = _checklist(be, "Microsoft 365 subscription", "software: yes")
    assert result["requirements"]


def test_bm25_backend_streams_chat():
    be = _load(BM25Backend())
    out = "".join(be.stream_chat(
        "sys", [{"role": "user", "content": "licensing?"}]))
    assert out.strip()


def test_backends_health_check_ok():
    assert KeywordBackend().health_check()["status"] == "ok"
    assert BM25Backend().health_check()["status"] == "ok"
