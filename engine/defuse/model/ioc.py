"""Indicator-of-compromise set: the structured form of a worm advisory."""

from __future__ import annotations

import re
from datetime import datetime
from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from semantic_version import NpmSpec, Version

_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class Ecosystem(StrEnum):
    NPM = "npm"


class HookKind(StrEnum):
    CLAUDE_SESSION_START = "claude_session_start"
    VSCODE_FOLDER_OPEN_TASK = "vscode_folder_open_task"
    AGENTS_MD_INSTRUCTION = "agents_md_instruction"


class AffectedPackage(BaseModel):
    """One package and the versions an advisory names as malicious."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: Annotated[str, Field(min_length=1, max_length=214)]
    versions: tuple[str, ...] = ()
    ranges: tuple[str, ...] = ()

    @model_validator(mode="after")
    def _has_selector(self) -> AffectedPackage:
        if not self.versions and not self.ranges:
            raise ValueError(f"package {self.name!r} names no versions and no ranges")
        for version in self.versions:
            Version(version)
        for spec in self.ranges:
            NpmSpec(spec)
        return self

    def matches(self, version: str) -> bool:
        try:
            parsed = Version(version)
        except ValueError:
            return False
        if version in self.versions:
            return True
        return any(NpmSpec(spec).match(parsed) for spec in self.ranges)


class HookSignature(BaseModel):
    """A substring that identifies a planted agent hook of a given kind."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: HookKind
    pattern: Annotated[str, Field(min_length=3)]


class IOCSet(BaseModel):
    """Everything an advisory tells us, in a form the engine can match against GitLab data."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: Annotated[str, Field(pattern=r"^[a-z0-9][a-z0-9-]{1,62}$")]
    title: Annotated[str, Field(min_length=3, max_length=200)]
    source_urls: tuple[str, ...] = ()
    ecosystem: Ecosystem = Ecosystem.NPM
    packages: Annotated[tuple[AffectedPackage, ...], Field(min_length=1)]
    file_hashes: tuple[str, ...] = ()
    persistence_paths: tuple[str, ...] = ()
    hook_signatures: tuple[HookSignature, ...] = ()
    exfil_indicators: tuple[str, ...] = ()
    window_start: datetime
    window_end: datetime | None = None

    @field_validator("file_hashes")
    @classmethod
    def _sha256(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        for digest in value:
            if not _SHA256.match(digest):
                raise ValueError(f"file hash {digest!r} is not a lowercase sha256 hex digest")
        return value

    @model_validator(mode="after")
    def _window(self) -> IOCSet:
        if self.window_start.tzinfo is None:
            raise ValueError("window_start must carry a timezone")
        if self.window_end is not None and self.window_end < self.window_start:
            raise ValueError("window_end is before window_start")
        return self

    def affected(self, name: str, version: str) -> bool:
        return any(p.name == name and p.matches(version) for p in self.packages)

    def in_window(self, moment: datetime) -> bool:
        if moment < self.window_start:
            return False
        return self.window_end is None or moment <= self.window_end
