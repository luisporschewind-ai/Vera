"""Versioned, JSON-serializable contracts shared by Vera clients and Runtime."""

from typing import Any

from pydantic import BaseModel, ConfigDict

# Pydantic validates the enclosing dict/list structure; recursive JSON typing
# here causes schema construction recursion on supported Pydantic versions.
type JsonValue = Any


class ContractModel(BaseModel):
    """Common immutability and extra-field policy for public contracts."""

    model_config = ConfigDict(frozen=True, extra="forbid")
