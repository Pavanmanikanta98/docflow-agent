"""Invoice document plugin — schema + prompt for invoice extraction."""

from typing import Optional, Type

from pydantic import BaseModel, Field

from backend.plugins.base import DocumentPlugin


class InvoiceFields(BaseModel):
    """Structured output schema for invoice documents."""
    vendor_name: Optional[str] = Field(None, description="Vendor name")
    invoice_number: Optional[str] = Field(None, description="Invoice or reference number")
    invoice_date: Optional[str] = Field(None, description="Date of the invoice (as string)")
    due_date: Optional[str] = Field(None, description="Due date of the invoice (as string)")
    total_amount: Optional[float] = Field(None, description="Total amount of the invoice")
    currency: Optional[str] = Field(None, description="Currency code e.g. USD, EUR, INR")
    line_items: Optional[list[str]] = Field(None, description="List of line item descriptions")
    confidence_score: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description=(
            "Your confidence in this extraction from 0.0 to 1.0. "
            "Lower if fields are missing or ambiguous."
        ),
    )


class InvoicePlugin(DocumentPlugin):
    """Plugin for processing invoice documents."""

    @property
    def document_type(self) -> str:
        return "invoice"

    @property
    def extraction_schema(self) -> Type[BaseModel]:
        return InvoiceFields

    @property
    def system_prompt(self) -> str:
        return (
            "You are a document extraction specialist. "
            "Extract structured invoice fields from the provided raw text. "
            "If a field is not present in the text, set it to null. "
            "Be honest about your confidence_score — set it lower if many fields are missing."
        )
