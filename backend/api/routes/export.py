"""Routes: GET /export/{job_id}?format=json|csv."""


import csv
import io
import json

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from backend.api.deps import get_db
from backend.models.db import Document, DocumentStatus

router = APIRouter(prefix="/documents", tags=["export"])

@router.get("/{document_id}/export")
async def export_document(
    document_id: int,
    format: str = Query("json", enum=["json", "csv"]),
    db: Session = Depends(get_db),
):
    doc = db.get(Document, document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
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
    filename = f"document_{document_id}_export.csv"
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={
            "Content-Disposition": f"attachment; filename={filename}"
        }
    )
    
    