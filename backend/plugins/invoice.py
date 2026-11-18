"""Invoice document plugin — schema + prompt for invoice extraction."""

from typing import Optional, Type

from pydantic import BaseModel, Field

from backend.plugins.base import DocumentPlugin, MergePolicy


class InvoiceFields(BaseModel):
    """Structured output schema for invoice documents."""
    vendor_name: Optional[str] = Field(None, description="Vendor name")
    invoice_number: Optional[str] = Field(
        None, description="Invoice or reference number"
    )
    invoice_date: Optional[str] = Field(
        None, description="Date of the invoice (as string)"
    )
    due_date: Optional[str] = Field(
        None, description="Due date of the invoice (as string)"
    )
    subtotal: Optional[float] = Field(
        None,
        description=(
            "Subtotal before tax, only if the document has a printed subtotal "
            "line (e.g. 'Subtotal', 'Net', 'Zwischensumme', 'Imponibile'); "
            "otherwise null. Never the total, never computed."
        ),
    )
    tax_amount: Optional[float] = Field(
        None,
        description=(
            "Tax amount, only if a tax line (e.g. 'Tax', 'VAT', 'GST', 'MwSt', "
            "'IVA') is printed in the document; otherwise null. Never computed."
        ),
    )
    total_amount: Optional[float] = Field(
        None, description="Total amount of the invoice"
    )
    currency: Optional[str] = Field(
        None, description="Currency code e.g. USD, EUR, INR"
    )
    line_items: Optional[list[str]] = Field(
        None, description="List of line item descriptions"
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


class InvoicePlugin(DocumentPlugin):
    """Plugin for processing invoice documents."""

    @property
    def document_type(self) -> str:
        return "invoice"

    @property
    def extraction_schema(self) -> Type[BaseModel]:
        return InvoiceFields

    @property
    def merge_policy(self) -> dict[str, MergePolicy]:
        # Totals should reflect the final page's numbers; line items span
        # every page they appear on. Header facts (vendor, invoice/date
        # fields, currency) default to "first_non_null".
        return {
            "subtotal": "last",
            "tax_amount": "last",
            "total_amount": "last",
            "line_items": "concat",
        }

    @property
    def system_prompt(self) -> str:
        return (
            "You are a document extraction specialist. "
            "Extract structured invoice fields from the provided raw text. "
            "If a field is not present in the text, set it to null. "
            "Only extract amounts that are printed in the document: never compute "
            "a value, and never copy the total into subtotal. An invoice that "
            "prints only a total has a null subtotal and a null tax_amount. "
            "Be honest about your confidence_score — set it lower if many fields "
            "are missing."
        )
