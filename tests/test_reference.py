from pathlib import Path

import pytest

from offer_agent.reference import (
    ReferenceGenerationError,
    ReferenceStore,
    generate_reference,
    generate_reference_with_retry,
    get_or_create_reference,
)


def test_generate_reference_is_two_digits():
    for _ in range(200):
        ref = generate_reference()
        assert len(ref) == 2
        assert ref.isdigit()
        assert 0 <= int(ref) <= 99


def test_reuses_reference_for_same_offer_id(tmp_path):
    store = ReferenceStore(tmp_path / "refs.json")
    ref1, created1 = get_or_create_reference(store, "offer-123")
    ref2, created2 = get_or_create_reference(store, "offer-123")
    assert ref1 == ref2
    assert created1 is True
    assert created2 is False


def test_different_offers_can_get_different_store_entries(tmp_path):
    store = ReferenceStore(tmp_path / "refs.json")
    ref_a, _ = get_or_create_reference(store, "offer-a")
    ref_b, _ = get_or_create_reference(store, "offer-b")
    assert store.get("offer-a") == ref_a
    assert store.get("offer-b") == ref_b


def test_retry_once_then_raises():
    calls = {"n": 0}

    class FailingRng:
        def randint(self, a, b):
            calls["n"] += 1
            raise RuntimeError("boom")

    with pytest.raises(ReferenceGenerationError):
        generate_reference_with_retry(FailingRng())
    assert calls["n"] == 2
