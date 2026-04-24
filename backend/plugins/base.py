"""DocumentPlugin interface — all document-type plugins implement this."""


from abc import ABC, abstractmethod
from typing import Type
from pydantic import BaseModel


class DocumentPlugin(ABC):

    @property
    @abstractmethod
    def document_type(self) -> str: ...

    @property
    @abstractmethod
    def extraction_schema(self) -> Type[BaseModel]: ...

    @property
    @abstractmethod
    def system_prompt(self) -> str: ...

    