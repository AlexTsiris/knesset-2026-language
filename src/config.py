"""Загрузка конфигов и общие пути проекта."""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = ROOT / "config"
DATA_RAW = ROOT / "data" / "raw"
DATA_INTERIM = ROOT / "data" / "interim"
DATA_PROCESSED = ROOT / "data" / "processed"
OUTPUTS = ROOT / "outputs"

for _p in (DATA_RAW, DATA_INTERIM, DATA_PROCESSED, OUTPUTS):
    _p.mkdir(parents=True, exist_ok=True)


def _load(name: str) -> dict[str, Any]:
    with open(CONFIG_DIR / name, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


@dataclass
class Politician:
    id: str
    name_ru: str
    name_he: str
    party: str
    party_he: str
    bloc: str
    handle: str | None
    verified: bool = False
    aliases: list[str] = field(default_factory=list)


@dataclass
class Campaign:
    start: dt.date
    election_day: dt.date
    lists_deadline: dt.date
    end: dt.date

    @property
    def days(self) -> int:
        return (self.end - self.start).days + 1


class Config:
    def __init__(self) -> None:
        self.settings = _load("settings.yaml")
        self.topics_raw = _load("topics.yaml")
        self._politicians_raw = _load("politicians.yaml")["politicians"]

    @property
    def campaign(self) -> Campaign:
        c = self.settings["campaign"]
        end = c.get("end") or dt.date.today().isoformat()
        return Campaign(
            start=dt.date.fromisoformat(str(c["start"])),
            election_day=dt.date.fromisoformat(str(c["election_day"])),
            lists_deadline=dt.date.fromisoformat(str(c["lists_deadline"])),
            end=dt.date.fromisoformat(str(end)),
        )

    @property
    def politicians(self) -> list[Politician]:
        return [Politician(**p) for p in self._politicians_raw]

    @property
    def with_handles(self) -> list[Politician]:
        return [p for p in self.politicians if p.handle]

    def by_id(self, pid: str) -> Politician:
        for p in self.politicians:
            if p.id == pid:
                return p
        raise KeyError(pid)

    def by_handle(self, handle: str) -> Politician | None:
        h = handle.lstrip("@").lower()
        for p in self.politicians:
            if p.handle and p.handle.lower() == h:
                return p
        return None

    @property
    def topics(self) -> dict[str, dict]:
        return self.topics_raw["topics"]

    @property
    def rhetoric(self) -> dict[str, dict]:
        return self.topics_raw["rhetoric"]

    # ---- удобные ярлыки к settings ----
    @property
    def analysis(self) -> dict:
        return self.settings["analysis"]

    @property
    def collection(self) -> dict:
        return self.settings["collection"]


CFG = Config()
