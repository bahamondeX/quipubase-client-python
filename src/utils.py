from __future__ import annotations

import asyncio
import json
import logging
import time
import typing as tp
from dataclasses import asdict, dataclass, field
from functools import partial, reduce, wraps
from hashlib import sha256
from typing import Any, Callable, Coroutine, Type, TypeVar, cast

from typing_extensions import ParamSpec

T = TypeVar("T")
P = ParamSpec("P")


@dataclass
class QuipubaseException(BaseException):
    """Base Tool Exception for handling errors on multiple backends"""

    detail: str
    status_code: int = field(default=500)

    def model_dump(self):
        return asdict(self)

    def model_dump_json(self):
        return json.dumps(asdict(self))

    def dict(self):
        return asdict(self)

    def json(self):
        return json.dumps(asdict(self))

    def __str__(self):
        return self.json()

    def __repr__(self):
        return self.__str__()


def encrypt(s: str):
    return sha256((s).encode()).hexdigest()


def get_key(*, object: dict[str, Any], key: str) -> None:
    try:
        return object[key]
    except KeyError:
        return None


def chunker(seq: str, size: int):
    return (seq[pos : pos + size] for pos in range(0, len(seq), size))


def get_logger(
    name: str | None = None,
    level: int = logging.DEBUG,
    format_string: str = json.dumps(
        {
            "timestamp": "%(asctime)s",
            "level": "%(levelname)s",
            "name": "%(name)s",
            "message": "%(message)s",
        }
    ),
) -> logging.Logger:
    """
    Configures and returns a logger with a specified name, level, and format.

    :param name: Name of the logger. If None, the root logger will be configured.
    :param level: Logging level, e.g., logging.INFO, logging.DEBUG.
    :param format_string: Format string for log messages.
    :return: Configured logger.
    """
    if name is None:
        name = "🚀 Trace >>"
    logger_ = logging.getLogger(name)
    logger_.setLevel(level)
    if not logger_.handlers:
        ch = logging.StreamHandler()
        formatter = logging.Formatter(format_string)
        ch.setFormatter(formatter)
        logger_.addHandler(ch)
    return logging.getLogger(name)


logger = get_logger()


def exception_handler(
    func: Callable[P, T],
) -> Callable[P, T]:
    """
    Decorator to handle exceptions in a function.

    :param func: Function to be decorated.
    :return: Decorated function.
    """

    @wraps(func)
    async def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
        try:
            if asyncio.iscoroutinefunction(func):
                return await func(*args, **kwargs)
            return func(*args, **kwargs)
        except Exception as e:
            logger.error("%s: %s", e.__class__.__name__, e)
            raise QuipubaseException(
                status_code=500,
                detail=f"Internal Server Error: {e.__class__.__name__} => {e}",
            ) from e

    wrapper.__name__ = func.__name__
    return tp.cast(Callable[P, T], wrapper)


def timing_handler(
    func: Callable[P, T],
) -> Callable[P, T]:
    """
    Decorator to measure the time taken by a function.

    :param func: Function to be decorated.
    :return: Decorated function.
    """

    @wraps(func)
    async def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
        start = time.time()
        if asyncio.iscoroutinefunction(func):
            result = await func(*args, **kwargs)
        result = func(*args, **kwargs)
        end = time.time()
        logger.info("%s took %s seconds", func.__name__, end - start)
        return tp.cast(T, result)  # type: ignore

    wrapper.__name__ = func.__name__
    return tp.cast(T, wrapper)  # type: ignore


def retry_handler(
    func: Callable[P, T], retries: int = 3, delay: int = 1
) -> Callable[P, T]:
    """
    Decorator to retry a function with exponential backoff.

    :param func: Function to be decorated.
    :param retries: Number of retries.
    :param delay: Delay between retries.
    :return: Decorated function.
    """

    @wraps(func)
    async def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
        nonlocal delay
        for _ in range(retries):
            try:
                if asyncio.iscoroutinefunction(func):
                    result = await func(*args, **kwargs)
                else:
                    result = func(*args, **kwargs)
                return tp.cast(T, result)  # type: ignore
            except QuipubaseException as e:
                logger.error("%s: %s", e.__class__.__name__, e)
                time.sleep(delay)
                delay *= 2
                continue
        raise QuipubaseException(
            status_code=500, detail=f"Exhausted retries after {retries} attempts"
        )

    wrapper.__name__ = func.__name__
    return tp.cast(T, wrapper)  # type: ignore


def handle(func: Callable[P, T], retries: int = 3, delay: int = 1) -> Callable[P, T]:
    """
    Decorator to retry a function with exponential backoff and handle exceptions.

    :param func: Function to be decorated.
    :param retries: Number of retries.
    :param delay: Delay between retries.
    :return: Decorated function.
    """
    eb = partial(retry_handler, retries=retries, delay=delay)
    return reduce(lambda f, g: g(f), [exception_handler, timing_handler, eb], func)  # type: ignore


def asyncify(func: Callable[P, T]) -> Callable[P, Coroutine[None, T, T]]:
    """
    Decorator to convert a synchronous function to an asynchronous function.

    :param func: Synchronous function to be decorated.
    :return: Asynchronous function.
    """

    @wraps(func)
    async def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
        wrapper.__name__ = func.__name__
        return await asyncio.to_thread(func, *args, **kwargs)

    return wrapper


def singleton(cls: Type[T]) -> Type[T]:
    """
    Decorator that converts a class into a singleton.

    Args:
                                                                                                                                                                                                                                                                    cls (Type[T]): The class to be converted into a singleton.

    Returns:
                                                                                                                                                                                                                                                                    Type[T]: The singleton instance of the class.
    """
    instances: dict[Type[T], T] = {}

    @wraps(cls)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
        if cls not in instances:
            instances[cls] = cls(*args, **kwargs)
        return instances[cls]

    return cast(Type[T], wrapper)


def coalesce(*args: T) -> T | None:
    """
    Returns the first non-None argument.

    :param args: Arguments to be coalesced.
    :return: First non-None argument.
    """
    for arg in args:
        if arg is not None:
            return arg
    raise ValueError("No arguments provided")


def merge_dicts(*dicts: dict[str, T]) -> dict[str, T]:
    """
    Merges multiple dictionaries into one.
    """
    return {k: v for d in dicts for k, v in d.items()}
