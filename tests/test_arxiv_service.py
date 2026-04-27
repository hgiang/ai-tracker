import pytest

from app.services.arxiv import arxiv_id_from_url, pdf_url_from_arxiv_url


@pytest.mark.unit
def test_arxiv_id_from_abs_url():
    assert arxiv_id_from_url("https://arxiv.org/abs/2501.12345") == "2501.12345"


@pytest.mark.unit
def test_arxiv_id_from_abs_url_with_version():
    assert arxiv_id_from_url("https://arxiv.org/abs/2501.12345v2") == "2501.12345v2"


@pytest.mark.unit
def test_arxiv_id_from_pdf_url():
    assert arxiv_id_from_url("https://arxiv.org/pdf/2501.12345") == "2501.12345"


@pytest.mark.unit
def test_arxiv_id_from_unknown_url_returns_none():
    assert arxiv_id_from_url("https://example.com/paper") is None


@pytest.mark.unit
def test_pdf_url_from_arxiv_url():
    assert pdf_url_from_arxiv_url("https://arxiv.org/abs/2501.12345") == "https://arxiv.org/pdf/2501.12345"


@pytest.mark.unit
def test_pdf_url_from_non_arxiv_returns_none():
    assert pdf_url_from_arxiv_url("https://example.com/paper") is None
