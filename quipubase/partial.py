from __future__ import annotations

import copy
from typing import (Any, Dict, Generic, List, Type, TypeVar, cast, get_args,
                    get_origin, get_type_hints)

from pydantic import BaseModel

T = TypeVar("T")

class Partial(Generic[T]):
    """
    A utility class that allows for partial updates of a type T.
    Similar to TypeScript's Partial<T> type.
    
    Example:
        # Define a model
        class User(BaseModel):
            name: str
            email: str
            age: int
            
        # Create a partial update
        update = Partial[User](name="New Name")
        
        # Apply to an existing instance
        updated_user = update.value(original_user)
    """
    
    def __new__(cls, **kwargs: Any):
        """
        Factory method to validate fields before creating the instance.
        
        Args:
            **kwargs: The fields to update and their new values.
        
        Returns:
            A new Partial instance with validated fields.
        """
        # Get the type argument T from the class
        origin_type = None
        
        # Check if we're dealing with a subclass that has T specified
        for base in cls.__orig_bases__ if hasattr(cls, "__orig_bases__") else []: # type: ignore
            origin = get_origin(base) # type: ignore
            if origin is Partial:
                args = get_args(base)
                if args and args[0] is not Any:
                    origin_type = args[0]
                    break
        
        # Validate fields against the origin type if it's a BaseModel
        if origin_type and issubclass(origin_type, BaseModel):
            model_fields = get_type_hints(origin_type)
            invalid_fields = [field for field in kwargs if field not in model_fields]
            
            if invalid_fields:
                error_msg = f"Invalid fields for {origin_type.__name__}: {', '.join(invalid_fields)}"
                raise ValueError(error_msg)
        
        instance = super().__new__(cls)
        return instance
    
    def __init__(self, **kwargs: Any):
        """
        Initialize a partial update with the fields to be updated.
        
        Args:
            **kwargs: The fields to update and their new values.
        """
        self.data = kwargs

    def value(self, original: T) -> T:
        """
        Apply the partial data to the original data.
        Returns a new instance with the partial updates applied.
        
        Args:
            original: The original data to apply the partial updates to.
            
        Returns:
            A new instance with the partial updates applied.
        """
        if isinstance(original, BaseModel): # type: ignore
            return self._partial_base_model(original)
        elif isinstance(original, dict): # type: ignore
            return self._partial_dict(cast(Dict[Any, Any], original)) # type: ignore
        elif isinstance(original, list): # type: ignore
            return self._partial_list(cast(List[Any], original)) # type: ignore
        else:
            # For primitive types, just return the partial data if it exists
            return cast(T, self.data.get("value", original))

    def _partial_base_model(self, original: BaseModel) -> BaseModel:
        """
        Apply the partial data to a BaseModel.
        
        Args:
            original: The original BaseModel to apply the partial updates to.
            
        Returns:
            A new BaseModel with the partial updates applied.
        """
        # Deep copy to avoid modifying the original
        result = copy.deepcopy(original)        
        for key, value in self.data.items():
            if hasattr(result, key):
                original_value = getattr(result, key)
                # If the value is another Partial and we're updating a complex type
                if isinstance(value, Partial) and (isinstance(original_value, (dict, list, BaseModel))):
                    setattr(result, key, value.value(original_value)) # type: ignore
                # Handle lists
                elif isinstance(original_value, list) and isinstance(value, list):
                    setattr(result, key, self._merge_lists(original_value, value)) # type: ignore
                # Handle dictionaries
                elif isinstance(original_value, dict) and isinstance(value, dict):
                    setattr(result, key, self._merge_dicts(original_value, value)) # type: ignore
                # Handle nested BaseModel
                elif isinstance(original_value, BaseModel) and isinstance(value, dict):
                    # Validate and convert dict to Partial of the appropriate type
                    nested_class = original_value.__class__
                    # Create a typed Partial for the nested model
                    nested_partial = create_typed_partial(nested_class)(**value)
                    setattr(result, key, nested_partial.value(original_value))
                # Direct assignment for other types
                else:
                    setattr(result, key, value)
                    
        return cast(T, result) # type: ignore

    def _partial_dict(self, original: Dict[Any, Any]) -> Dict[str, Any]:
        """
        Apply the partial data to a dictionary.
        
        Args:
            original: The original dictionary to apply the partial updates to.
            
        Returns:
            A new dictionary with the partial updates applied.
        """
        # Deep copy to avoid modifying the original
        result = copy.deepcopy(original)
        
        for key, value in self.data.items():
            if key in result:
                original_value = result[key]
                
                # Recursive handling of nested partials
                if isinstance(value, Partial):
                    result[key] = value.value(original_value) # type: ignore
                # Handle nested lists
                elif isinstance(original_value, list) and isinstance(value, list):
                    result[key] = self._merge_lists(original_value, value) # type: ignore
                # Handle nested dictionaries
                elif isinstance(original_value, dict) and isinstance(value, dict):
                    result[key] = self._merge_dicts(original_value, value) # type: ignore
                # Direct assignment for other types
                else:
                    result[key] = value
            else:
                # Add new keys
                result[key] = value
                
        return cast(T, result) # type: ignore

    def _partial_list(self, original: List[Any]) -> List[Any]:
        """
        Apply the partial data to a list.
        
        Args:
            original: The original list to apply the partial updates to.
            
        Returns:
            A new list with the partial updates applied.
        """
        # For lists, we handle them based on the 'items' key in the partial data
        if 'items' not in self.data:
            return cast(T, original) # type: ignore
            
        # Deep copy to avoid modifying the original
        result = copy.deepcopy(original)
        partial_items = self.data['items']
        
        # Apply partial updates to list items if provided as a dictionary with indices
        if isinstance(partial_items, dict):
            for idx_str, value in partial_items.items(): # type: ignore
                try:
                    idx = int(idx_str) # type: ignore
                    if 0 <= idx < len(result):
                        original_value = result[idx]
                        
                        # Recursive handling of nested partials
                        if isinstance(value, Partial):
                            result[idx] = value.value(original_value) # type: ignore
                        # Handle nested structures
                        elif isinstance(original_value, list) and isinstance(value, list):
                            result[idx] = self._merge_lists(original_value, value) # type: ignore
                        elif isinstance(original_value, dict) and isinstance(value, dict):
                            result[idx] = self._merge_dicts(original_value, value) # type: ignore
                        # Direct assignment for other types
                        else:
                            result[idx] = value
                except (ValueError, IndexError):
                    continue
        # If items is a list, replace the whole list
        elif isinstance(partial_items, list):
            return cast(T, partial_items) # type: ignore
            
        return cast(T, result) # type: ignore

    def _merge_dicts(self, original: Dict[Any, Any], partial: Dict[Any, Any]) -> Dict[Any, Any]:
        """
        Merge two dictionaries recursively.
        
        Args:
            original: The original dictionary.
            partial: The partial dictionary to merge with the original.
            
        Returns:
            A new dictionary with the partial updates applied.
        """
        result = copy.deepcopy(original)
        
        for key, value in partial.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self._merge_dicts(result[key], value) # type: ignore
            else:
                result[key] = value
                
        return result

    def _merge_lists(self, original: List[Any], partial: List[Any]) -> List[Any]:
        """
        Merge two lists.
        
        Args:
            original: The original list.
            partial: The partial list to merge with the original.
            
        Returns:
            The partial list (replacing the original).
        """
        # For simplicity, we just replace the list
        return partial
        
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> Partial[T]:
        """
        Create a Partial from a dictionary.
        
        Args:
            data: The dictionary to create a partial from.
            
        Returns:
            A new Partial instance.
        """
        return cls(**data)
        
    @classmethod
    def from_orm(cls, instance: Any) -> Partial[T]:
        """
        Create a Partial from an ORM instance.
        
        Args:
            instance: The ORM instance to create a partial from.
            
        Returns:
            A new Partial instance.
        """
        if isinstance(instance, BaseModel):
            return cls(**instance.model_dump(exclude_unset=True))
        else:
            return cls(**instance)

def create_typed_partial(model_type: Type[T]) -> Type[Partial[T]]:
    """
    Factory function to create a Partial class with a specific type.
    
    Args:
        model_type: The type to create a Partial for.
        
    Returns:
        A Partial class with the specified type.
    """
    class TypedPartial(Partial[model_type]):
        __orig_bases__ = (Partial[model_type],)
    
    return TypedPartial