import json
import typing as tp
from dataclasses import dataclass, field

from httpx import AsyncClient, Response
from pydantic import BaseModel

from .event import Event
from .partial import Partial
from .proxy import LazyProxy
from .schemas import Collection
from .typedefs import CollectionType, JsonSchema, Request
from .utils import get_logger, handle

T = tp.TypeVar("T", bound=Collection)

logger = get_logger(__name__)

@dataclass
class QuipuBase(tp.Generic[T], LazyProxy[AsyncClient]):
    """
    Base class for interacting with the Quipu API.

    This class provides methods for sending requests to the API and handling
    responses. It uses the `httpx` library for making HTTP requests and
    supports both synchronous and asynchronous operations.
    """
    base_url: str = field(default="https://db.oscarbahamonde.cloud")
   
  
    def __load__(self):
        return AsyncClient(base_url=self.base_url)
    
    async def fetch(self, endpoint: str, method: tp.Literal["GET", "POST", "PUT", "DELETE"], headers:dict[str,str]={"Content-Type": "application/json", "Accept": "application/json"},
                   json: tp.Optional[tp.Union[JsonSchema, T, Partial[T]]] = None, 
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
        if isinstance(json, BaseModel):
            data = json.model_dump(exclude_none=True)
        else:
            data = json
        try:
            response = await self.__load__().request(
                method=method,
                url=endpoint,
                json=data,
                params=params,
                headers=headers
            )
            return response.raise_for_status()
        except Exception as e:
            logger.error("Error in API request: %s", e)
            raise
    @handle
    async def create_collection(self, schema: T) -> CollectionType:
        """
        Create a new collection.
        
        Args:
            schema: JSON schema definition for the collection
            
        Returns:
            Created collection information
        """
        response = await self.fetch("/v1/collections", "POST", json=schema)
        return CollectionType(**response.json())
    @handle
    async def list_collections(self, limit: int = 100, offset: int = 0) -> list[str]:
        """
        List all collections with pagination.
        
        Args:
            limit: Maximum number of collections to return
            offset: Pagination offset
            
        Returns:
            List of collection IDs
        """
        response = await self.fetch("/v1/collections", "GET", params={"limit": limit, "offset": offset})
        return response.json()
    @handle
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
    @handle
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
    
    @handle
    async def collection_action(self, col_id: str, action: Request[T]) -> dict[str, tp.Any]:
        """
        Perform a unified action on a collection.
        
        Args:
            collection_id: ID of the collection
            action: Action request with event type and data
            
        Returns:
            Action response
        """
        assert action.data is not None, "Data must be provided for the action"
        response = await self.fetch(f"/v1/collections/{col_id}", "PUT", json=action.data)
        if response.status_code == 200:
            return response.json()
        else:
            logger.error("Error in collection action: %s", response.text)
            raise Exception(f"Error in collection action: {response.status_code} - {response.text}")

    @handle
    async def pub(self, col_id:str, request: Request[T])->dict[str, tp.Any]:
        """
        Publish data to a collection.
        
        Args:
            collection_id: ID of the collection
            data: Data to publish
            
        Returns:
            Published data information
        """
        assert request.data is not None, "Data must be provided for publishing"
        response = await self.fetch(f"/v1/collections/{col_id}", "POST", json=request.data)
        return response.raise_for_status().json()


    async def sub(self, col_id:str):
        """
        Subscribe to a collection.
        
        Args:
            collection_id: ID of the collection
            
        Returns:
            Subscription information
        """
        async with self.__load__().stream(f"/v1/events/{col_id}", "GET") as response:
            async for chunk in response.raise_for_status().aiter_lines():
                if chunk:
                    chunk = chunk.replace("data: ", "")
                    try:
                        yield Event[T](**json.loads(chunk))
                    except json.JSONDecodeError as e:
                        logger.error("Error decoding JSON: %s", e)
                        continue