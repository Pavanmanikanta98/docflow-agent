"""Contract document plugin — schema + prompt for contract extraction."""

from typing import Optional, Type

from pydantic import BaseModel, Field

from backend.plugins.base import DocumentPlugin


class ContractFields(BaseModel):
    """Structured output schema for contract documents."""
    parties: Optional[list[str]] = Field(None, description="List of parties named in the contract")
    effective_date: Optional[str] = Field(None, description="Contract effective/start date")
    expiry_date: Optional[str] = Field(None, description="Contract expiry or end date")
    contract_value: Optional[float] = Field(None, description="Total monetary value of the contract")
    currency: Optional[str] = Field(None, description="Currency code e.g. USD, EUR, INR")
    jurisdiction: Optional[str] = Field(None, description="Governing law / jurisdiction clause")
    key_obligations: Optional[list[str]] = Field(
        None, description="Top 3-5 key obligations of the main party"
    )
    termination_clause: Optional[str] = Field(
        None, description="Summary of the termination or exit clause"
    )
    confidence_score: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description=(
            "Your confidence in this extraction from 0.0 to 1.0. "
            "Lower if fields are missing or ambiguous."
        ),
    )


class ContractPlugin(DocumentPlugin):
    """Plugin for processing contract documents."""

    @property
    def document_type(self) -> str:
        return "contract"

    @property
    def extraction_schema(self) -> Type[BaseModel]:
        return ContractFields

    @property
    def system_prompt(self) -> str:
        return (
            "You are a legal document extraction specialist. "
            "Extract structured fields from the provided contract text. "
            "Identify all named parties, key dates, monetary values, and obligations. "
            "Summarise the termination clause in plain English. "
            "If a field is not present in the text, set it to null. "
            "Be honest about your confidence_score — set it lower if the contract is incomplete or ambiguous."
        )
