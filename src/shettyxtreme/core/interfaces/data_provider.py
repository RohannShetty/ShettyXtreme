from typing import Protocol, runtime_checkable, Generic, TypeVar, Any
Q = TypeVar("Q"); D = TypeVar("D")

@runtime_checkable
class DataProvider(Protocol):
    name: str; description: str
    async def is_available(self) -> bool: ...

@runtime_checkable
class DataFetcher(Protocol, Generic[Q, D]):
    @staticmethod
    def transform_query(params: dict[str, Any]) -> Q: ...
    @staticmethod
    async def extract_data(query: Q, credentials: dict|None) -> Any: ...
    @staticmethod
    def transform_data(query: Q, data: Any) -> D: ...
