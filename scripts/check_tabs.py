"""Hand-test step 1: feed a menu JSON (as returned by the NestJS menu endpoint) and see
which tabs the user is allowed / not allowed.

    python scripts/check_tabs.py                              # admin fixture (all 54 tabs)
    python scripts/check_tabs.py tests/fixtures/menu_limited.json
    python scripts/check_tabs.py path/to/any_menu.json        # e.g. saved from Postman
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import get_settings  # noqa: E402
from app.models.menu import MenuResponse  # noqa: E402
from app.scope.tabs import MenuUnavailableError, TabCatalog, resolve_user_tabs  # noqa: E402


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("tests/fixtures/menu_admin.json")
    menu = MenuResponse.model_validate(json.loads(path.read_text(encoding="utf-8")))
    catalog = TabCatalog.from_settings(get_settings())
    try:
        user = resolve_user_tabs(menu, catalog)
    except MenuUnavailableError as exc:
        print(f"MENU UNAVAILABLE: {exc}")
        return

    print(f"menu file: {path}")
    print(f"\nALLOWED ({len(user.allowed)}):")
    for t in user.allowed:
        print(f"  {t.menu_en} > {t.name_en:40} | {t.menu_ar} > {t.name_ar}")
    print(f"\nNOT ALLOWED ({len(user.not_allowed)}):")
    for t in user.not_allowed:
        print(f"  {t.menu_en} > {t.name_en:40} | {t.menu_ar} > {t.name_ar}")
    if user.unknown_names:
        print(f"\nUNKNOWN (in the menu but not in the vector DB): {user.unknown_names}")


if __name__ == "__main__":
    main()
