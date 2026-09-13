"""The manual-entry form must never block submission via HTML5 `required`
attributes — incompleteness is reported (and approval withheld) by our own
validate_offer/preview logic, which gives a specific "Missing fields" list
instead of a vague browser tooltip, and lets an upload-then-partially-filled
form still reach the preview for review.
"""

from pathlib import Path

INDEX_TEMPLATE = Path(__file__).resolve().parent.parent / "webapp" / "templates" / "index.html"


def test_index_template_has_no_required_attributes():
    html = INDEX_TEMPLATE.read_text()
    assert " required" not in html, "index.html must not use HTML5 required= attributes"


def test_preview_accepts_a_completely_empty_submission():
    from webapp.app import app

    client = app.test_client()
    resp = client.post("/preview", data={})

    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert '<button type="submit">Approve and create</button>' not in html
    assert "Missing fields" in html


def test_preview_accepts_a_partial_submission():
    from webapp.app import app

    client = app.test_client()
    resp = client.post(
        "/preview",
        data={"business_unit": "PureHealth", "candidate_full_name": "Jane Doe"},
    )

    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert '<button type="submit">Approve and create</button>' not in html
    assert "Missing fields" in html
