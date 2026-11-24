"""Issue #55: a document looks the same wherever the API returns it.

The review page read `doc.id` from GET /documents/{id}, which returned
`document_id` instead, so the page asked for /documents/undefined/export.
"""

import io

from fastapi.testclient import TestClient

from backend.tests.integration.conftest import SESSION_A, session_headers


def _upload(client: TestClient) -> int:
    response = client.post(
        "/api/v1/documents/upload",
        files={"file": ("a.pdf", io.BytesIO(b"%PDF-1.4 x"), "application/pdf")},
        data={"document_type": "invoice"},
        headers=session_headers(SESSION_A),
    )
    assert response.status_code == 200, response.text
    return int(response.json()["document_id"])


def test_detail_and_list_item_have_the_same_keys(client: TestClient) -> None:
    document_id = _upload(client)
    headers = session_headers(SESSION_A)

    detail = client.get(f"/api/v1/documents/{document_id}", headers=headers).json()
    listed = client.get("/api/v1/documents", headers=headers).json()["documents"][0]

    assert set(detail) == set(listed)


def test_detail_id_is_the_integer_the_export_route_needs(
    client: TestClient,
) -> None:
    document_id = _upload(client)

    detail = client.get(
        f"/api/v1/documents/{document_id}", headers=session_headers(SESSION_A)
    ).json()

    assert detail["id"] == document_id
    assert isinstance(detail["id"], int)
    assert "document_id" not in detail
