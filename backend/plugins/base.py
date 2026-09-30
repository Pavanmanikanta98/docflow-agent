"""DocumentPlugin interface — all document-type plugins implement this."""


from abc import ABC, abstractmethod
from typing import Literal, Type

from pydantic import BaseModel

# ADR 006 — how to combine the same field's value across a chunked document's
# pieces. "first_non_null": the earliest chunk with a value wins (a header
# fact that should appear once). "last": the latest chunk's value wins (a
# running total that should reflect the final page). "concat": every
# non-null value is combined in chunk order (free text or a list that
# legitimately spans chunks).
MergePolicy = Literal["first_non_null", "last", "concat"]


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

    @property
    def merge_policy(self) -> dict[str, MergePolicy]:
        """Per-field merge policy for a chunked document (ADR 006).

        Any field not listed here defaults to "first_non_null" — the safe
        choice for a fact that should only appear on one page. Plugins
        override this only for fields that need "last" or "concat".
        """
        return {}

    def merge_policy_for(self, field: str) -> MergePolicy:
        return self.merge_policy.get(field, "first_non_null")

