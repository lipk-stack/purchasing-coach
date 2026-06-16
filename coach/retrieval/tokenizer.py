"""Pure-Python text tokenizer for the Purchasing Coach retrieval engine.

Provides stopword filtering, a simplified Porter-style stemmer tuned for
procurement vocabulary, and n-gram generation.  Depends only on the Python
standard library so the retrieval engine can run as a portable zipapp.
"""

from __future__ import annotations

import re

# ---------------------------------------------------------------------------
# Stopwords
# ---------------------------------------------------------------------------

STOPWORDS: frozenset[str] = frozenset({
    # --- articles, demonstratives, quantifiers ---
    "a", "an", "the", "this", "that", "these", "those",
    "some", "any", "all", "each", "every", "no", "not", "none",
    "many", "much", "few", "several", "enough",
    # --- pronouns ---
    "i", "me", "my", "we", "us", "our", "you", "your",
    "he", "him", "his", "she", "her", "it", "its",
    "they", "them", "their", "who", "whom", "which", "what",
    "myself", "ourselves", "yourself", "yourselves", "himself",
    "herself", "itself", "themselves",
    # --- prepositions ---
    "in", "on", "at", "to", "for", "of", "with", "by", "from",
    "about", "into", "through", "during", "before", "after",
    "above", "below", "between", "under", "over", "up", "down",
    "out", "off", "against", "along", "among", "around",
    "as", "per", "via",
    # --- conjunctions ---
    "and", "but", "or", "nor", "so", "yet", "both", "either",
    "neither", "although", "though", "because", "since", "unless",
    "while", "whereas",
    # --- auxiliary / common verbs ---
    "is", "am", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "having", "do", "does", "did", "doing",
    "will", "would", "shall", "should", "may", "might", "must",
    "can", "could",
    # --- misc function words ---
    "if", "then", "else", "when", "where", "how", "why",
    "also", "just", "only", "very", "too", "than", "more",
    "such", "own", "same", "other", "another", "here", "there",
    "now", "once", "again", "further", "most", "least",
    "its", "let", "may", "let",
    # --- procurement noise words ---
    "etc", "ie", "eg", "via", "vs",
})

# Pre-compiled pattern: keep letters, digits, and intra-word hyphens.
_TOKEN_RE = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")

# ---------------------------------------------------------------------------
# Stemmer suffix rules (order matters — first match wins)
# ---------------------------------------------------------------------------

_SUFFIX_RULES: list[tuple[str, str | None]] = [
    # Each rule is (suffix, replacement).  ``None`` means "remove suffix".
    # Suffixes are written without a leading hyphen so that str.endswith()
    # matches directly against the word.
    ("tion",  None),
    ("sion",  None),
    ("ing",   None),
    ("ment",  None),
    ("ness",  None),
    ("able",  None),
    ("ible",  None),
    ("ful",   None),
    ("less",  None),
    ("ly",    None),
    ("ies",   "y"),
    ("es",    None),
    ("ed",    None),
    ("er",    None),
    ("ous",   None),
    ("al",    None),
    ("ive",   None),
    ("ize",   None),
]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def tokenize(text: str) -> list[str]:
    """Tokenize *text* into a list of lowercase, stemmed tokens.

    Processing steps:

    1. Lowercase the input.
    2. Extract tokens that consist of letters/digits possibly joined by
       hyphens (e.g. ``"cost-effective"`` stays as one token).
    3. Remove stopwords.
    4. Apply the simplified stemmer to each remaining token.
    5. Drop any tokens that are empty or a single character after stemming.

    Returns an empty list for blank or ``None`` input.
    """
    if not text:
        return []
    raw = _TOKEN_RE.findall(text.lower())
    out: list[str] = []
    for tok in raw:
        if tok in STOPWORDS:
            continue
        stemmed = stem(tok)
        if len(stemmed) > 1:
            out.append(stemmed)
    return out


def stem(word: str) -> str:
    """Return a simplified stem of *word* using procurement-tuned suffix rules.

    The stemmer applies rules in declaration order and stops at the first
    match.  Words of three characters or fewer are returned unchanged to avoid
    over-stemming short but meaningful tokens (e.g. ``"api"``, ``"sla"``).

    This is intentionally simpler than a full Porter stemmer — it is tuned
    for the kind of vocabulary found in procurement guidelines (contract
    terms, compliance language, technical requirements) rather than general
    English prose.
    """
    if len(word) <= 3:
        return word
    for suffix, replacement in _SUFFIX_RULES:
        if word.endswith(suffix) and len(word) > len(suffix) + 2:
            if replacement is None:
                return word[: -len(suffix)]
            return word[: -len(suffix)] + replacement
    return word


def ngrams(tokens: list[str], n: int = 2) -> list[tuple[str, ...]]:
    """Generate contiguous n-grams from a token list.

    >>> ngrams(["a", "b", "c", "d"], n=2)
    [('a', 'b'), ('b', 'c'), ('c', 'd')]
    >>> ngrams(["a", "b", "c"], n=3)
    [('a', 'b', 'c')]

    Returns an empty list when *tokens* has fewer than *n* elements.
    """
    if n < 1:
        raise ValueError(f"n must be >= 1, got {n}")
    if len(tokens) < n:
        return []
    return [tuple(tokens[i : i + n]) for i in range(len(tokens) - n + 1)]
