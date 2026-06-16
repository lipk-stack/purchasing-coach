"""Comprehensive stress test for Purchasing Coach v2.0."""
import sys, traceback

failures = []

def check(name, fn):
    try:
        fn()
        print(f"  PASS  {name}")
    except Exception as e:
        failures.append((name, e))
        print(f"  FAIL  {name}: {e}")
        traceback.print_exc()

print("=" * 60)
print("STRESS TEST: Purchasing Coach v2.0")
print("=" * 60)

# ---- Retrieval engine ----
print("\n--- Retrieval Engine ---")

def test_tokenizer():
    from coach.retrieval.tokenizer import tokenize, stem, ngrams, STOPWORDS
    tokens = tokenize("The hardware must comply with security requirements")
    assert len(tokens) > 0, "tokenize returned nothing"
    assert "the" not in tokens, "stopword not removed"
    assert len(ngrams(["a", "b", "c"], 2)) == 2
    assert len(STOPWORDS) > 100
check("Tokenizer", test_tokenizer)

def test_inverted_index():
    from coach.retrieval import InvertedIndex
    from coach.documents import load_guideline
    from coach.guideline import parse_clauses, parse_clause_requirements
    guideline = load_guideline("samples/guideline_text.md")
    clauses = parse_clauses(guideline)
    clause_reqs = parse_clause_requirements(guideline)
    idx = InvertedIndex()
    idx.build_from_guideline(guideline, clauses, clause_reqs)
    assert idx.N > 0, "No documents indexed"
    assert idx.avgdl > 0, "avgdl is 0"
    assert len(idx.postings) > 50, f"Only {len(idx.postings)} terms indexed"
    idf = idx.idf("security")
    assert idf > 0, "IDF for security is 0"
check("InvertedIndex build + stats", test_inverted_index)

def test_bm25_ranker():
    from coach.retrieval import InvertedIndex, BM25Ranker
    from coach.documents import load_guideline
    from coach.guideline import parse_clauses, parse_clause_requirements
    guideline = load_guideline("samples/guideline_text.md")
    clauses = parse_clauses(guideline)
    clause_reqs = parse_clause_requirements(guideline)
    idx = InvertedIndex()
    idx.build_from_guideline(guideline, clauses, clause_reqs)
    ranker = BM25Ranker(idx)
    results = ranker.score("hardware warranty requirements", top_k=5)
    assert len(results) > 0, "BM25 returned no results"
    assert results[0][1] > 0, "Top score is 0"
    top_refs = [r[2].get("ref", "") for r in results[:3]]
    print(f"    Top refs for 'hardware warranty': {top_refs}")
check("BM25 Ranker", test_bm25_ranker)

def test_cosine_ranker():
    from coach.retrieval import InvertedIndex, CosineRanker
    from coach.documents import load_guideline
    from coach.guideline import parse_clauses, parse_clause_requirements
    guideline = load_guideline("samples/guideline_text.md")
    clauses = parse_clauses(guideline)
    clause_reqs = parse_clause_requirements(guideline)
    idx = InvertedIndex()
    idx.build_from_guideline(guideline, clauses, clause_reqs)
    ranker = CosineRanker(idx)
    results = ranker.score("cloud SaaS data protection", top_k=5)
    assert len(results) > 0, "Cosine returned no results"
    print(f"    Top refs for 'cloud SaaS': {[r[2].get('ref','') for r in results[:3]]}")
check("Cosine Ranker", test_cosine_ranker)

def test_rrf_fusion():
    from coach.retrieval import InvertedIndex, BM25Ranker, CosineRanker, rrf_fusion
    from coach.documents import load_guideline
    from coach.guideline import parse_clauses, parse_clause_requirements
    guideline = load_guideline("samples/guideline_text.md")
    clauses = parse_clauses(guideline)
    clause_reqs = parse_clause_requirements(guideline)
    idx = InvertedIndex()
    idx.build_from_guideline(guideline, clauses, clause_reqs)
    bm25 = BM25Ranker(idx).score("penetration test assessment", top_k=10)
    cosine = CosineRanker(idx).score("penetration test assessment", top_k=10)
    fused = rrf_fusion(bm25, cosine, top_k=5)
    assert len(fused) > 0, "RRF fusion returned nothing"
    assert len(fused) <= 5, "RRF returned more than top_k"
    print(f"    Fused refs: {[r[2].get('ref','') for r in fused[:3]]}")
check("RRF Fusion", test_rrf_fusion)

# ---- Backend stress tests ----
print("\n--- Backends ---")
from coach.documents import load_guideline
from coach.llm import Coach

guideline = load_guideline("samples/guideline_text.md")

def stress_backend(name):
    from coach.backends import get_backend
    b = get_backend(name)
    coach = Coach(guideline, b)
    # Chat
    reply = "".join(coach.answer([{"role": "user", "content": "What are the compliance requirements?"}]))
    assert len(reply) > 20, f"{name} chat reply too short: {len(reply)} chars"
    # Interview plan
    plan = coach.plan_interview("enterprise cloud email service")
    assert len(plan.questions) >= 5, f"{name} only {len(plan.questions)} questions"
    # Checklist
    answers = [(q.question, "Yes, it handles personal data and is cloud-hosted") for q in plan.questions]
    checklist = coach.build_checklist("enterprise cloud email service", answers)
    assert len(checklist.requirements) > 0, f"{name} produced 0 requirements"
    # Health check
    health = b.health_check()
    assert health["status"] == "ok", f"{name} health: {health}"
    return len(checklist.requirements)

for bname in ["keyword", "template", "bm25"]:
    def test(name=bname):
        n = stress_backend(name)
        print(f"    {name}: {n} requirements generated")
    check(f"{bname} backend full flow", test)

# ---- Edge cases ----
print("\n--- Edge Cases ---")

def test_empty_query():
    from coach.backends import get_backend
    b = get_backend("keyword")
    coach = Coach(guideline, b)
    reply = "".join(coach.answer([{"role": "user", "content": ""}]))
    assert isinstance(reply, str)
check("Empty query", test_empty_query)

def test_very_long_query():
    from coach.backends import get_backend
    b = get_backend("keyword")
    coach = Coach(guideline, b)
    long_q = " ".join(["security compliance requirement audit assessment"] * 50)
    reply = "".join(coach.answer([{"role": "user", "content": long_q}]))
    assert len(reply) > 0
check("Very long query (500+ words)", test_very_long_query)

def test_special_chars():
    from coach.backends import get_backend
    b = get_backend("bm25")
    coach = Coach(guideline, b)
    reply = "".join(coach.answer([{"role": "user", "content": '<script>alert(1)</script> & "quotes"'}]))
    assert isinstance(reply, str)
check("Special chars / XSS in query", test_special_chars)

def test_unicode():
    from coach.backends import get_backend
    b = get_backend("keyword")
    coach = Coach(guideline, b)
    reply = "".join(coach.answer([{"role": "user", "content": "What about Japanese and emojis?"}]))
    assert isinstance(reply, str)
check("Unicode content", test_unicode)

def test_multi_turn_chat():
    from coach.backends import get_backend
    b = get_backend("bm25")
    coach = Coach(guideline, b)
    history = [
        {"role": "user", "content": "What are the hardware requirements?"},
        {"role": "assistant", "content": "Section 8 covers hardware."},
        {"role": "user", "content": "And what about software licensing?"},
    ]
    reply = "".join(coach.answer(history))
    assert len(reply) > 0
check("Multi-turn conversation", test_multi_turn_chat)

def test_empty_guideline():
    from coach.backends import get_backend
    b = get_backend("keyword")
    coach = Coach("This is a plain text guideline with no numbered sections.", b)
    reply = "".join(coach.answer([{"role": "user", "content": "test"}]))
    assert isinstance(reply, str)
check("Unstructured guideline (no clauses)", test_empty_guideline)

# ---- Session persistence ----
print("\n--- Session Persistence ---")

def test_session_crud():
    import tempfile
    from coach.webui import WebUI
    from coach.backends import get_backend
    b = get_backend("keyword")
    coach = Coach(guideline, b)
    ui = WebUI(coach, b, "samples/guideline_text.md", None, tempfile.mkdtemp())
    # Create
    sid = ui.save_session({"title": "Test session", "messages": [{"role": "user", "content": "hello"}]})
    assert sid, "save returned no id"
    # List
    sessions = ui.list_sessions()
    assert any(s["id"] == sid for s in sessions), "Created session not in list"
    # Load
    loaded = ui.load_session(sid)
    assert loaded["title"] == "Test session"
    assert len(loaded["messages"]) == 1
    # Delete
    ok = ui.delete_session(sid)
    assert ok, "delete returned False"
    assert ui.load_session(sid) is None, "Session still exists after delete"
check("Session CRUD", test_session_crud)

# ---- Analytics ----
print("\n--- Analytics ---")

def test_analytics():
    from coach.models import AnalyticsSnapshot, RequirementRow
    rows = [
        RequirementRow("5.1", "Security", "Encrypt data", "M"),
        RequirementRow("5.2", "Security", "Access controls", "M"),
        RequirementRow("7.1", "Support", "24/7 SLA", "O"),
        RequirementRow("8.1", "Hardware", "Warranty terms", "M"),
    ]
    snap = AnalyticsSnapshot.from_checklist(rows, total_clauses=12)
    assert snap.total_requirements == 4
    assert snap.mandatory_count == 3
    assert snap.optional_count == 1
    assert snap.coverage_pct > 0
    assert len(snap.by_section) == 3
    assert len(snap.section_heatmap) == 3
check("AnalyticsSnapshot", test_analytics)

# ---- Model serialization ----
print("\n--- Model Serialization ---")

def test_session_model():
    from coach.models import Session, ChatMessage
    s = Session(id="abc", title="Test", messages=[
        ChatMessage(role="user", content="hi", timestamp="2026-01-01T00:00:00")
    ])
    d = s.to_dict()
    s2 = Session.from_dict(d)
    assert s2.id == "abc"
    assert len(s2.messages) == 1
    assert s2.messages[0].role == "user"
check("Session model round-trip", test_session_model)

def test_chat_message_model():
    from coach.models import ChatMessage
    m = ChatMessage(role="assistant", content="hello", reactions=["thumbsup"])
    d = m.to_dict()
    m2 = ChatMessage.from_dict(d)
    assert m2.content == "hello"
    assert m2.reactions == ["thumbsup"]
check("ChatMessage model round-trip", test_chat_message_model)

# ---- Backend registry ----
print("\n--- Backend Registry ---")

def test_list_backends():
    from coach.backends import list_backends
    backends = list_backends()
    assert "auto" in backends
    assert "keyword" in backends
    assert "template" in backends
    assert "bm25" in backends
    assert "claude" in backends
check("list_backends()", test_list_backends)

def test_detect_backend_compat():
    from coach.backends import detect_backend
    b = detect_backend("keyword")
    assert b.name == "keyword"
check("detect_backend() compat alias", test_detect_backend_compat)

def test_template_scenarios():
    from coach.templates.scenarios import SCENARIOS, KEYWORD_INDEX
    assert len(SCENARIOS) == 4
    assert "hardware" in SCENARIOS
    assert "software" in SCENARIOS
    assert "services" in SCENARIOS
    assert "cybersecurity" in SCENARIOS
    assert len(KEYWORD_INDEX) > 20
    assert KEYWORD_INDEX.get("server") == "hardware"
    assert KEYWORD_INDEX.get("saas") == "software"
check("Template scenarios data", test_template_scenarios)

# ---- Summary ----
print("\n" + "=" * 60)
if failures:
    print(f"FAILED: {len(failures)} test(s)")
    for name, e in failures:
        print(f"  - {name}: {e}")
    sys.exit(1)
else:
    print("ALL STRESS TESTS PASSED")
    print("=" * 60)
