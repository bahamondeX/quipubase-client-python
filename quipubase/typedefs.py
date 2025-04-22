# In typedefs.py
import uuid
from typing import Any, Dict, Literal, Optional, TypeAlias, Generic, TypeVar

from pydantic import BaseModel, Field
from typing_extensions import TypedDict, NotRequired
from .schemas import Collection
from .partial import Partial

T = TypeVar("T", bound=Collection, covariant=True)


# First define the JsonSchema as a regular Pydantic model (not TypedDict)
class JsonSchemaModel(BaseModel):
    """JSON Schema representation"""

    title: str = Field(...)
    description: Optional[str] = Field(default=None)
    type: Literal[
        "object", "array", "string", "number", "integer", "boolean", "null"
    ] = Field(default="object")
    properties: Dict[str, Any] = Field(..., alias="properties")
    required: Optional[list[str]] = Field(default=None, alias="required")
    enum: Optional[list[Any]] = Field(default=None, alias="enum")
    items: Optional[Any] = Field(default=None, alias="items")


# Keep TypedDict version if needed elsewhere
class JsonSchema(TypedDict):
    """JSON Schema representation"""

    title: str
    description: NotRequired[str]
    type: Literal["object", "array", "string", "number", "integer", "boolean", "null"]
    properties: Dict[str, Any]
    enum: NotRequired[list[Any]]
    items: NotRequired[Any]


# Define QuipuActions as a type alias for a set of string literals
QuipuActions: TypeAlias = Literal["create", "read", "update", "delete", "query", "stop"]
class CollectionType(TypedDict):
    id: str
    name:str
    schema: JsonSchema 
    
class CollectionMetadataType(TypedDict):
    id: str
    name: str

class Request(BaseModel, Generic[T]):
    model_config = {"arbitrary_types_allowed": True}
    event: QuipuActions = Field(default="query")
    id: Optional[uuid.UUID] = Field(default=None)
    data: Optional[T | Partial[T]] = Field(default=None)

class Response(BaseModel, Generic[T]):
    col_id:str
    data:T