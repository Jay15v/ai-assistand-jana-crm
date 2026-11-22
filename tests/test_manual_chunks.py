"""Manual parsing (part 2 of step 3): chunks, image stripping, AR twins, the permission filter."""

import pytest

from app.features.agent.repositories.manual import eligible, load_chunks


@pytest.fixture(scope="module")
def chunks():
    return load_chunks()


def by_q(chunks, q):
    return next(c for c in chunks if c.question_en == q)


def test_all_101_questions_become_chunks(chunks):
    assert len(chunks) == 101
    assert len({c.id for c in chunks}) == 101  # unique ids


def test_96_have_arabic_twins_2_fall_back_to_english(chunks):
    no_ar = sorted(c.question_en for c in chunks if c.text_ar is None)
    assert no_ar == [
        "How do I create a ticket from a customer's page?",
        "How do I edit or deactivate a Definition item?",
    ]
    for c in chunks:
        assert c.text("en") == c.text_en
        assert c.text("ar") == (c.text_ar or c.text_en)  # EN fallback when no twin


def test_images_are_stripped_everywhere(chunks):
    for c in chunks:
        assert "![" not in c.text_en, c.id
        assert "![" not in (c.text_ar or ""), c.id


def test_known_chunk_content_and_tags(chunks):
    c = by_q(chunks, "How do I void an invoice directly?")
    assert c.tabs == ["Search Invoices"]
    assert "Void" in c.text_en
    assert c.question_ar == "إزاي ألغي فاتورة مباشرة؟"
    assert "### إزاي ألغي فاتورة مباشرة؟" in c.text_ar


def test_title_text_is_bilingual(chunks):
    c = by_q(chunks, "How do I change a ticket's status?")
    assert c.title_text() == "How do I change a ticket's status? | إزاي أغيّر حالة التذكرة؟"


def test_general_chunks_are_flagged_and_never_eligible(chunks):
    general = [c for c in chunks if c.general]
    assert len(general) == 9
    all_tabs = {t for c in chunks for t in c.tabs}
    assert all(not eligible(c, all_tabs) for c in general)


def test_eligible_any_rule(chunks):
    c = by_q(chunks, "How do I void an invoice directly?")
    assert eligible(c, {"Search Invoices", "Add Ticket"})
    assert not eligible(c, {"Search Tickets", "Search Complaint"})


def test_eligible_all_rule(chunks):
    c = by_q(chunks, "How do I create a ticket from a customer's page?")
    assert c.require == "all"
    assert eligible(c, {"Search Customer", "Add Ticket"})
    assert not eligible(c, {"Search Customer"})  # has the page but not Add Ticket
    assert not eligible(c, {"Add Ticket"})


def test_multi_tab_any_chunk(chunks):
    c = by_q(chunks, "How do I add a new Definition item (e.g. a Department)?")
    assert eligible(c, {"Department"})  # any one of the 9 definition tabs is enough
