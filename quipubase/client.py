import json
import asyncio
import typing as tp
import uuid
from dataclasses import dataclass, field

from httpx import AsyncClient, Response
from pydantic import BaseModel

from .event import Event
from .partial import Partial
from .proxy import LazyProxy
from .typedefs import CollectionMetadataType, CollectionType, JsonSchema, Request, Collection, Response as QResponse
from .utils import get_logger

T = tp.TypeVar("T", bound=Collection)

logger = get_logger(__name__)

class UUIDEncoder(json.JSONEncoder):
    """
    Custom JSON encoder for UUID objects.
    
    This encoder converts UUID objects to their string representation when
    serializing to JSON.
    """
    def default(self, o: tp.Any) -> tp.Any:
        if isinstance(o, uuid.UUID):
            return str(o)
        return super().default(o)

@dataclass
class QuipuBase(tp.Generic[T], LazyProxy[AsyncClient]):
    """
    Base class for interacting with the Quipu API.

    This class provides methods for sending requests to the API and handling
    responses. It uses the `httpx` library for making HTTP requests and
    supports both synchronous and asynchronous operations.
    """
    base_url: str = field(default="https://quipubase.online")
   
  
    def __load__(self):
        return AsyncClient(base_url=self.base_url)

    @classmethod
    def __class_getitem__(cls, item: tp.Type[T]):
        """
        Allows for dynamic typing of the class based on the provided item.
        
        Args:
            item: The item to use for dynamic typing
            
        Returns:
            The class itself
        """
        cls._model = item
        return cls
    
    async def fetch(self, endpoint: str, method: tp.Literal["GET", "POST", "PUT", "DELETE"], headers:dict[str,str]={"Content-Type": "application/json", "Accept": "application/json"},
                   data: tp.Optional[tp.Union[JsonSchema, T, Partial[T], Request[T]]] = None, 
                   params: tp.Optional[dict[str,tp.Any]] = None) -> Response:
        """
        Base request method for API calls.
        
        Args:
            endpoint: API endpoint path
            method: HTTP method to use
            json: Request body data
            params: Query parameters
            
        Returns:
            Parsed JSON response as dict
        """
        if isinstance(data, BaseModel):
            d = data.model_dump(exclude_none=True)
        elif isinstance(data, Partial):
            d = data.data
        else:
            d = data
        try:
            response = await self.__load__().request(
                method=method,
                url=endpoint,
                json=json.loads(json.dumps(d, cls=UUIDEncoder)) if d else None,
                params=params,
                headers=headers
            )
            return response.raise_for_status()
        except Exception as e:
            logger.error("Error in API request: %s", e)
            raise

    async def create_collection(self, schema: T) -> CollectionType:
        """
        Create a new collection.
        
        Args:
            schema: JSON schema definition for the collection
            
        Returns:
            Created collection information
        """
        response = await self.fetch("/v1/collections", "POST", data=schema)
        return CollectionType(**response.json())

    async def list_collections(self):
        """
        List all collections with pagination.
        
        Args:
            limit: Maximum number of collections to return
            offset: Pagination offset
            
        Returns:
            List of collection IDs
        """
        response = await self.fetch("/v1/collections", "GET")
        return [CollectionMetadataType(d) for d in response.json()]

    async def get_collection(self, collection_id: str) -> CollectionType:
        """
        Get a specific collection by ID.
        
        Args:
            collection_id: ID of the collection to retrieve
            
        Returns:
            Collection information
        """
        response = await self.fetch(f"/v1/collections/{collection_id}", "GET")
        return CollectionType(**response.json())

    async def delete_collection(self, collection_id: str) -> dict[str, bool]:
        """
        Delete a collection by ID.
        
        Args:
            collection_id: ID of the collection to delete
            
        Returns:
            Deletion status
        """
        response = await self.fetch(f"/v1/collections/{collection_id}", "DELETE")
        return response.json()


    async def pub(self, col_id: str, request: Request[T]) -> QResponse[T]:
        """
        Publish data to a collection.
        
        Args:
            col_id: ID of the collection
            request: Request with data and event
            
        Returns:
            Published data information
        """
        assert request.data is not None, "Data must be provided for publishing"
        
        # Structure the action request according to the API's expectations
        action_request:dict[str,tp.Any] = {
            "event": request.event,  # create, read, update, delete, query, stop
            "data": request.data.model_dump(exclude_unset=True,exclude_none=True) if isinstance(request.data, BaseModel) else request.data
        }
        
        response = await self.fetch(f"/v1/events/{col_id}", "POST", data=action_request) # type: ignore
        data = self._model.model_validate(response.json()["data"])
        return QResponse[T](col_id=col_id, data=data)

    async def sub(self, col_id: str):
        """
        Subscribe to a collection with infinite retry.
        
        Args:
            col_id: ID of the collection
            
        Yields:
            Event objects from the stream
        """
        logger.info("Subscribing to events for collection %s", col_id)
        client = AsyncClient(
                    base_url=self.base_url,
                    timeout=None  # No timeout
                )
        while True:
            try:
                async with client.stream("GET", f"/v1/events/{col_id}", 
                                        headers={"Accept":"application/json"}) as response:
                    response.raise_for_status()
                    async for chunk in response.aiter_lines():
                        if chunk:
                            try:
                                yield Event[T](**json.loads(chunk.strip()))
                            except json.JSONDecodeError as e:
                                logger.error("Error decoding JSON: %s", e)
                                continue
            except Exception as e:
                logger.error("Subscription error: %s", e)
                await asyncio.sleep(1)
                continue
            finally:
                await client.aclose()