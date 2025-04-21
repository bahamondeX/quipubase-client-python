import typing as tp

from pydantic import BaseModel

from .schemas import Collection
from .typedefs import QuipuActions

T = tp.TypeVar("T", bound=Collection, covariant=True)


class Event(BaseModel, tp.Generic[T]):
    """Event model"""

    event: QuipuActions
    data: T
