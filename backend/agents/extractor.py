"""Agent 2: pydantic-ai structured field extraction (amounts, dates, parties)."""

from typing import Optional
from pydantic import BaseModel, Field
from pydantic_ai import Agent
from backend.core.llm import llm_client
from backend.plugins.base import DocumentPlugin


async def extract_fields(raw_text: str, plugin: DocumentPlugin) -> BaseModel:
    """
    Dynamically creates an agent using the plugin's schema + prompt,
    runs it against the raw text, and returns structured output.
    """

    agent = Agent(
        model=llm_client.get_model(),
        output_type=plugin.extraction_schema,
        system_prompt=plugin.system_prompt,
    )

    result = await agent.run(raw_text)
    return result.output



# # --- Output Schema ---
# # This is what the AI MUST return. Pydantic-ai enforces this strictly.
# class InvoiceFields(BaseModel):
#     vendor_name: Optional[str] = Field(None, description="Vendor name")
#     invoice_number: Optional[str] = Field(None, description="Invoice or reference number")
#     invoice_date: Optional[str] = Field(None, description="Date of the invoice (as string)")
#     due_date: Optional[str] = Field(None, description="Due date of the invoice (as string)")
#     total_amount: Optional[float] = Field(None, description="Total amount of the invoice")
#     currency: Optional[str] = Field(None, description="Currency code e.g. USD, EUR, INR")
#     line_items: Optional[list[str]] = Field(None, description="List of line item descriptions")
#     confidence_score: float = Field(
#         ...,
#         ge=0.0,
#         le=1.0,
#         description=(
#             "Your confidence in this extraction from 0.0 to 1.0. "
#             "Lower if fields are missing or ambiguous."
#         ),
#     )



# # --- Standalone test ---
# if __name__ == "__main__":
#     import asyncio

#     SAMPLE_TEXT = """
#     INVOICE
#     Vendor: Acme Corp Ltd.
#     Invoice No: INV-2024-0042
#     Invoice Date: 2024-01-15
#     Due Date: 2024-02-15

#     Items:
#     - Software License (annual)   $1,200.00
#     - Support Package             $300.00

#     Subtotal: $1,500.00
#     Tax (10%): $150.00
#     TOTAL DUE: $1,650.00  USD
#     """

#     async def main():
#         print("\nSending to LLM... (this may take a few seconds)")
#         fields = await extract_invoice_fields(SAMPLE_TEXT)
#         print("\n--- EXTRACTED FIELDS ---")
#         print(fields.model_dump_json(indent=2))

#     asyncio.run(main())
