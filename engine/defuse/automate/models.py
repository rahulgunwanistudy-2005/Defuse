"""Untrusted flow drafts and metadata-only credential receipts."""

from __future__ import annotations

from pathlib import PurePosixPath
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)


class FileEdit(StrictModel):
    action: Literal["create", "update", "delete"]
    file_path: str
    content: str | None = Field(default=None, max_length=2_000_000)

    @field_validator("file_path")
    @classmethod
    def safe_path(cls, path: str) -> str:
        parsed = PurePosixPath(path)
        if (
            not path
            or parsed.is_absolute()
            or ".." in parsed.parts
            or "\\" in path
            or str(parsed) != path
            or path.startswith(".git/")
        ):
            raise ValueError("file path must be canonical and repository-relative")
        return path

    @model_validator(mode="after")
    def content_matches_action(self) -> FileEdit:
        if (self.action == "delete") != (self.content is None):
            raise ValueError("only delete actions omit content")
        return self


class FlowDraft(StrictModel):
    flow: Literal["advisory-intake", "incident-commander", "hook-sweeper", "postmortem-policy"]
    incident_id: str
    project_id: int = Field(gt=0)
    title: str = Field(min_length=3, max_length=200)
    description: str = Field(min_length=1, max_length=100_000)
    edits: tuple[FileEdit, ...] = ()
    refused_fields: tuple[str, ...] = ()

    @model_validator(mode="after")
    def no_writes_when_refusing(self) -> FlowDraft:
        if self.refused_fields and self.edits:
            raise ValueError("a refusal cannot include edits")
        paths = [e.file_path for e in self.edits]
        if len(paths) != len(set(paths)):
            raise ValueError("duplicate edit paths")
        return self


class CredentialConsumer(StrictModel):
    owner: str
    key: str
    environment_scope: str
    protected: bool

    @property
    def ref(self) -> str:
        return f"{self.owner}:{self.key}@{self.environment_scope}"


class CredentialRequest(StrictModel):
    incident_id: str
    action_id: str
    target: str
    namespace: str
    operation: Literal["replace", "tighten_scopes"] = "replace"
    projects: tuple[str, ...]
    carriers: tuple[str, ...] = ()
    scopes: tuple[str, ...] = ()
    consumers: tuple[CredentialConsumer, ...] = ()
    retire_old: bool = False


class CredentialReceipt(StrictModel):
    receipt_id: str = Field(min_length=1)
    incident_id: str
    action_id: str
    target: str
    namespace: str
    installed: Literal[True]
    old_revoked: bool
    replacement_id: str | None = None
    evidence_url: str | None = None
    consumer_refs: tuple[str, ...] = ()
