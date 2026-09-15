"""Routes: GET /export/{job_id}?format=json|csv."""


import csv
import io

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse

from backend.api.deps import get_owned_document
from backend.models.db import Document, DocumentStatus

router = APIRouter(prefix="/documents", tags=["export"])

@router.get("/{document_id}/export")
async def export_document(
    format: str = Query("json", enum=["json", "csv"]),
    doc: Document = Depends(get_owned_document),
):
    if doc.status != DocumentStatus.completed:
        raise HTTPException(
            status_code=400,
            detail=f"Document is not completed. Current status: {doc.status.value}"
        )
    if not doc.extraction_results:
        raise HTTPException(
            status_code=404,
            detail="No extraction results found for this document."
        )


    if format == "json":
        return doc.extraction_results # FastAPI serializes dict to JSON automatically

    # CSV export
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["key","value"]) # Header row
    for key, value in doc.extraction_results.items():
        writer.writerow([key, value])

    output.seek(0)
    filename = f"document_{doc.id}_export.csv"
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={
            "Content-Disposition": f"attachment; filename={filename}"
        }
    )

