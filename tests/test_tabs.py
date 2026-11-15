"""Step 1 (scope): per-user allowed / not-allowed tabs from the NestJS menu JSON."""

import json
from pathlib import Path

import pytest

from app.config import get_settings
from app.models.menu import MenuResponse
from app.scope.tabs import MenuUnavailableError, TabCatalog, resolve_user_tabs

FIXTURES = Path(__file__).parent / "fixtures"


def load_menu(name: str) -> MenuResponse:
    return MenuResponse.model_validate(json.loads((FIXTURES / name).read_text(encoding="utf-8")))


@pytest.fixture(scope="module")
def catalog() -> TabCatalog:
    return TabCatalog.from_settings(get_settings())


def test_catalog_has_the_54_tabs(catalog):
    assert len(catalog.tabs) == 54


def test_admin_matches_every_tab(catalog):
    user = resolve_user_tabs(load_menu("menu_admin.json"), catalog)
    assert len(user.allowed) == 54
    assert user.not_allowed == []
    assert user.unknown_names == []


def test_aliases_map_the_4_renamed_tabs(catalog):
    for endpoint_name, db_name in [
        ("Search Unit", "Unit"),
        ("Document Library", "DocumentLibrary"),
        ("System Settings", "Settings"),
        ("Send Notifications", "Notifications"),
    ]:
        tab = catalog.find(endpoint_name)
        assert tab is not None, endpoint_name
        assert tab.name_en == db_name


def test_limited_user_gets_only_their_tabs(catalog):
    user = resolve_user_tabs(load_menu("menu_limited.json"), catalog)
    assert sorted(t.name_en for t in user.allowed) == [
        "Add CTS", "Add Complaint", "Add Ticket", "Search CTS", "Search Complaint", "Search Tickets",
    ]
    assert len(user.not_allowed) == 48
    # A tab the user does not have is in the not-allowed list.
    assert "Search Invoices" in {t.name_en for t in user.not_allowed}


def test_real_readonly_role(catalog):
    """A real restricted-role response captured from the live backend (2026-11-15)."""
    user = resolve_user_tabs(load_menu("menu_readonly_role.json"), catalog)
    assert sorted(t.name_en for t in user.allowed) == [
        "Complaints", "Search Complaint", "Search Tickets", "Statistics", "Tickets",
    ]
    assert len(user.not_allowed) == 49
    assert user.unknown_names == []
    # Per-tab precision: Search Tickets allowed while Add Ticket (same menu) is not.
    not_allowed = {t.name_en for t in user.not_allowed}
    assert "Add Ticket" in not_allowed


def test_unknown_tab_is_skipped_not_fatal(catalog):
    menu = load_menu("menu_limited.json")
    menu.result[0].menuitems[0].name = "Brand New Tab"
    user = resolve_user_tabs(menu, catalog)
    assert user.unknown_names == ["Brand New Tab"]
    assert len(user.allowed) == 5  # the other 5 still match


def test_failed_or_maintenance_menu_is_refused(catalog):
    menu = load_menu("menu_limited.json")
    menu.success = False
    with pytest.raises(MenuUnavailableError):
        resolve_user_tabs(menu, catalog)
    menu.success = True
    menu.is_maintenance = True
    with pytest.raises(MenuUnavailableError):
        resolve_user_tabs(menu, catalog)


def test_empty_menu_allows_nothing(catalog):
    user = resolve_user_tabs(MenuResponse(result=[]), catalog)
    assert user.allowed == []
    assert len(user.not_allowed) == 54


def test_matching_ignores_case_and_spacing(catalog):
    assert catalog.find("add  TICKET") is catalog.find("Add Ticket")
    assert catalog.find("no such tab") is None


def test_duplicate_tab_counted_once(catalog):
    menu = load_menu("menu_limited.json")
    menu.result[0].menuitems.append(menu.result[0].menuitems[0].model_copy())
    user = resolve_user_tabs(menu, catalog)
    assert len(user.allowed) == 6


def test_arabic_names_come_from_the_vector_db(catalog):
    tab = catalog.find("Add Ticket")
    assert tab.name_ar == "إضافة تذكرة"
    assert tab.menu_ar == "التذاكر"
