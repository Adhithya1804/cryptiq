"""Repository schemas for the domain and API boundary."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class RepositoryCreate(BaseModel):
    """The identity of a repository to register or look up."""

    provider: str = Field(min_length=1, max_length=32)
    owner: str = Field(min_length=1, max_length=255)
    name: str = Field(min_length=1, max_length=255)
    canonical_url: str = Field(min_length=1, max_length=1024)


class RepositoryRead(BaseModel):
    """A stored repository."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    provider: str
    owner: str
    name: str
    canonical_url: str
    created_at: datetime
    updated_at: datetime
