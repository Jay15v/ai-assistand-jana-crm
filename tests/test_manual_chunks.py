"""Manual parsing (part 2 of step 3): chunks, image stripping, AR twins, the permission filter."""

import pytest

from app.core.config import get_settings
from app.features.agent.repositories.manual import eligible, index_records, load_chunks
from app.features.agent.repositories.tabs import TabCatalog
from app.features.agent.services.answer import build_excerpts


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


# --- index records ----------------------------------------------------------------------------


@pytest.fixture(scope="module")
def catalog():
    return TabCatalog.from_settings(get_settings())


@pytest.fixture(scope="module")
def records(chunks, catalog):
    return index_records(chunks, catalog)


def test_every_chunk_has_a_title_and_a_full_record(chunks, records):
    for kind in ("title", "full"):
        assert {r.chunk_id for r in records if r.kind == kind} == {c.id for c in chunks}
    assert len({r.id for r in records}) == len(records)  # Chroma needs unique ids


def test_shared_chunk_gets_one_record_per_tab_with_both_names(chunks, catalog, records):
    c = by_q(chunks, "How do I add a new Definition item (e.g. a Department)?")
    tab_records = [r for r in records if r.chunk_id == c.id and r.kind == "tab"]
    assert [r.title for r in tab_records] == c.tabs
    names = {t.name_en: t.name_ar for t in catalog.tabs}
    for r in tab_records:
        assert r.text == f"{r.title} ({names[r.title]}): {c.title_text()}"


def test_single_tab_and_general_chunks_get_no_tab_record(chunks, records):
    with_tab_record = {r.chunk_id for r in records if r.kind == "tab"}
    assert with_tab_record == {c.id for c in chunks if c.is_shared()}
    for c in chunks:
        if c.general or len(c.tabs) <= 1:
            assert c.id not in with_tab_record


def test_tab_missing_from_the_catalog_is_skipped_not_fatal(chunks):
    c = by_q(chunks, "How do I add a new Definition item (e.g. a Department)?")
    records = index_records([c], TabCatalog([]))  # a catalog that knows no tabs
    assert [r.kind for r in records] == ["title", "full"]


# --- chapter intro -------------------------------------------------------------------------------


def test_chunk_carries_its_chapter_intro_in_both_languages(chunks):
    c = by_q(chunks, "How do I add a new Definition item (e.g. a Department)?")
    assert "Rental Companies" in c.intro_en and "Commercial Register" in c.intro_en
    assert "شركات التأجير" in c.intro_ar
    for intro in (c.intro_en, c.intro_ar):
        assert "![" not in intro and "<!--" not in intro and "###" not in intro


def test_every_question_of_a_chapter_shares_the_same_intro(chunks):
    by_section: dict[str, set[str]] = {}
    for c in chunks:
        by_section.setdefault(c.section_en, set()).add(c.intro_en)
    assert all(len(intros) == 1 for intros in by_section.values())


def test_intro_follows_the_language_of_the_section_text(chunks):
    c = by_q(chunks, "How do I add a new Definition item (e.g. a Department)?")
    assert c.intro("en") == c.intro_en and c.intro("ar") == c.intro_ar
    no_twin = by_q(chunks, "How do I edit or deactivate a Definition item?")  # answered from EN
    assert no_twin.intro("ar") == no_twin.intro_en


# --- what the generator reads --------------------------------------------------------------------


def test_excerpts_name_only_the_users_screens_for_a_shared_section(chunks, catalog):
    c = by_q(chunks, "How do I add a new Definition item (e.g. a Department)?")
    mine = [t for t in catalog.tabs if t.name_en in {"Rental Companies", "Search Tickets"}]
    text = build_excerpts([c], "en", mine)
    assert text.startswith(f"[Chapter overview: {c.section_en}]\n{c.intro_en}")
    assert "[Applies to each of these CRM screens: Definition > Rental Companies (شركات التأجير)]" in text
    assert "Definition > Department" not in text  # a screen this user lacks is not named
    assert "Search Tickets" not in text.split("[Applies to")[1]  # not one of this section's tabs


def test_excerpts_repeat_a_shared_chapter_overview_once(chunks, catalog):
    add = by_q(chunks, "How do I add a new Definition item (e.g. a Department)?")
    delete = by_q(chunks, "How do I delete a Definition item?")
    text = build_excerpts([add, delete], "en", catalog.tabs)
    assert text.count("[Chapter overview:") == 1
    assert add.text_en in text and delete.text_en in text


def test_excerpts_add_no_note_to_single_screen_or_all_required_sections(chunks, catalog):
    single = by_q(chunks, "How do I void an invoice directly?")
    both = by_q(chunks, "How do I create a ticket from a customer's page?")  # require = all
    assert "[Applies to" not in build_excerpts([single, both], "en", catalog.tabs)
