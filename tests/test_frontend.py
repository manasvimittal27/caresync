"""Checks on the static front end: served correctly, accessible structure, CSP-safe code."""

import re
from pathlib import Path

import pytest

STATIC = Path(__file__).resolve().parent.parent / "static"
JS_FILES = sorted(STATIC.rglob("*.js"))


def test_index_is_served_with_security_headers(client):
    res = client.get("/")
    assert res.status_code == 200
    assert "text/html" in res.headers["content-type"]
    assert "script-src 'self'" in res.headers["Content-Security-Policy"]


def test_index_has_accessible_structure(client):
    html = client.get("/").text
    assert '<html lang="en">' in html
    assert 'class="skip-link" href="#main"' in html
    assert '<main id="main"' in html
    assert 'aria-label="Main"' in html  # Labelled navigation landmark.
    assert 'role="status" aria-live="polite"' in html  # Announcements for screen readers.
    assert 'name="viewport"' in html


def test_no_inline_scripts_or_handlers_in_html(client):
    html = client.get("/").text
    for tag in re.findall(r"<script[^>]*>", html):
        assert "src=" in tag, "Inline scripts would violate the Content-Security-Policy"
    assert not re.search(r"\son[a-z]+=", html), "Inline event handlers are not allowed"
    assert "style=" not in html


@pytest.mark.parametrize("path", JS_FILES, ids=lambda p: str(p.relative_to(STATIC)))
def test_javascript_avoids_unsafe_dom_apis(path):
    source = path.read_text()
    for unsafe in ("innerHTML", "outerHTML", "insertAdjacentHTML", "document.write", "eval("):
        assert unsafe not in source, f"{unsafe} found in {path.name}"


@pytest.mark.parametrize("path", JS_FILES, ids=lambda p: str(p.relative_to(STATIC)))
def test_every_module_is_served(client, path):
    res = client.get("/" + str(path.relative_to(STATIC)))
    assert res.status_code == 200
    assert "javascript" in res.headers["content-type"]


def test_relative_imports_resolve():
    for path in JS_FILES:
        for target in re.findall(r'from "(\.{1,2}/[^"]+)"', path.read_text()):
            assert (path.parent / target).resolve().exists(), f"{path.name} imports missing {target}"
