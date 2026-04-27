from app.services.relevance import canonicalize_url, compute_relevance_score, normalize_title


def test_normalize_title_basic():
    assert normalize_title("  Hello, World!  ") == "hello world"


def test_normalize_title_collapses_whitespace():
    assert normalize_title("GPT-4   is   here") == "gpt4 is here"


def test_normalize_title_strips_accents():
    assert normalize_title("résumé") == "resume"


def test_canonicalize_url_removes_tracking():
    url = "https://example.com/article?id=1&utm_source=twitter&utm_medium=social"
    assert canonicalize_url(url) == "https://example.com/article?id=1"


def test_canonicalize_url_removes_fragment():
    url = "https://example.com/page#section"
    assert canonicalize_url(url) == "https://example.com/page"


def test_compute_relevance_score_high():
    score = compute_relevance_score("New LLM from OpenAI uses transformer architecture", "deep learning model")
    assert score > 0.0


def test_compute_relevance_score_low():
    score = compute_relevance_score("Recipe for chocolate cake", "Best baking tips")
    assert score == 0.0
