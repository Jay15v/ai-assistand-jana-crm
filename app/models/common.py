from typing import Literal

from pydantic import BaseModel, field_validator

Lang = Literal["en", "ar"]


class LocalizedText(BaseModel):
    """One user-facing string in both languages. Both are required and non-empty."""

    en: str
    ar: str

    @field_validator("en", "ar")
    @classmethod
    def _not_blank(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("localized text must not be empty")
        return v

    def get(self, lang: Lang) -> str:
        return self.ar if lang == "ar" else self.en


class LocalizedList(BaseModel):
    en: list[str] = []
    ar: list[str] = []

    def get(self, lang: Lang) -> list[str]:
        return self.ar if lang == "ar" else self.en
