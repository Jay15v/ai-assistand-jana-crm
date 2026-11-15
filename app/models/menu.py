"""Contract for the per-user menu JSON that the NestJS backend sends with every chat request.

Only `result[].menuitems[].name` drives the scope logic. `privileges`, `href` and the ids are
parsed but unused for now (privileges are a possible second-level check later). Unknown extra
fields are ignored so a backend change does not break parsing.
"""

from pydantic import BaseModel, ConfigDict


class MenuPrivilege(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: int
    name: str
    status: int


class MenuItem(BaseModel):
    """One sidebar tab the user is allowed to open."""

    model_config = ConfigDict(extra="ignore")

    id: int
    name: str
    href: str | None = None
    privileges: list[MenuPrivilege] = []


class MenuGroup(BaseModel):
    """One sidebar menu (e.g. 'Tickets') with its tabs."""

    model_config = ConfigDict(extra="ignore")

    menuName: str
    id: int
    menuitems: list[MenuItem] = []


class MenuResponse(BaseModel):
    """The full response of the NestJS menu endpoint."""

    model_config = ConfigDict(extra="ignore")

    result: list[MenuGroup] = []
    success: bool = True
    is_maintenance: bool = False

    def tab_names(self) -> list[str]:
        """All tab names in menu order, duplicates removed (first occurrence wins)."""
        seen: dict[str, None] = {}
        for group in self.result:
            for item in group.menuitems:
                if item.name not in seen:
                    seen[item.name] = None
        return list(seen)
