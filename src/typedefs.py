# In typedefs.py
import uuid
from typing import Any, Dict, Generic, Literal, Optional, TypeAlias, TypeVar

from pydantic import BaseModel, Field
from typing_extensions import TypedDict

from .partial import Partial

T = TypeVar("T", covariant=True, bound=BaseModel)

class JsonSchema(TypedDict):
    """JSON Schema representation"""

    title: str
    description: Optional[str]
    type: Literal["object", "array", "string", "number", "integer", "boolean", "null"]
    properties: Dict[str, Any]
    enum: Optional[list[Any]]
    items: Optional[Any]


QuipuActions: TypeAlias = Literal["create", "read", "update", "delete", "query", "stop"]


class CollectionType(BaseModel):
    id: str
    definition: JsonSchema


class Request(BaseModel,Generic[T]):
    event: QuipuActions = Field(default="query")
    id: Optional[uuid.UUID] = Field(default=None)
    data: Optional[T | Partial[T]] = Field(default=None)