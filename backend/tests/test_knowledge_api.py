"""
知识库接口测试
POST   /api/kb/documents        (文件上传,含类型/大小校验)
GET    /api/kb/documents
DELETE /api/kb/documents/{id}
注:后台文档处理(process_document)已在 conftest 中 mock,避免触发真实 Embedding/Chroma。
"""
from tests.helpers import register_admin_and_login, auth_headers


def _login(client):
    # 知识库管理接口要求 admin 角色,故用 admin 账号登录。
    return register_admin_and_login(client, email="kb@example.com")


def test_upload_no_auth(client):
    files = {"file": ("a.txt", b"hello", "text/plain")}
    r = client.post("/api/kb/documents", files=files)
    assert r.status_code == 401


def test_upload_success_txt(client):
    creds = _login(client)
    h = auth_headers(creds["token"])
    files = {"file": ("doc.txt", b"hello world", "text/plain")}
    r = client.post("/api/kb/documents", files=files, headers=h)
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is True
    data = body["data"]
    assert isinstance(data["document_id"], int)
    assert data["status"] == "processing"


def test_upload_success_md(client):
    creds = _login(client)
    h = auth_headers(creds["token"])
    files = {"file": ("doc.md", b"# title\ncontent", "text/markdown")}
    r = client.post("/api/kb/documents", files=files, headers=h)
    assert r.status_code == 200


def test_upload_success_docx(client):
    """Word 文档需被接受并落库为 file_type=docx(依赖 ENUM 已含 docx)。"""
    import io

    from docx import Document as DocxDocument

    doc = DocxDocument()
    doc.add_paragraph("退换货政策")
    doc.add_paragraph("签收后 7 天内可申请无理由退货。")
    buf = io.BytesIO()
    doc.save(buf)

    creds = _login(client)
    h = auth_headers(creds["token"])
    files = {
        "file": (
            "policy.docx",
            buf.getvalue(),
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
    }
    r = client.post("/api/kb/documents", files=files, headers=h)
    assert r.status_code == 200
    assert r.json()["data"]["status"] == "processing"

    listed = client.get("/api/kb/documents", headers=h).json()["data"]
    assert any(d["name"] == "policy.docx" and d["file_type"] == "docx" for d in listed)


def test_upload_invalid_type(client):
    creds = _login(client)
    h = auth_headers(creds["token"])
    files = {"file": ("malware.exe", b"binary", "application/octet-stream")}
    r = client.post("/api/kb/documents", files=files, headers=h)
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "INVALID_FILE_TYPE"
    assert "docx" in r.json()["detail"]["message"]


def test_upload_oversize(client):
    creds = _login(client)
    h = auth_headers(creds["token"])
    # 等价类:略大于 10MB 上限
    big = b"x" * (10 * 1024 * 1024 + 1)
    files = {"file": ("big.txt", big, "text/plain")}
    r = client.post("/api/kb/documents", files=files, headers=h)
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "FILE_TOO_LARGE"


def test_get_documents(client):
    creds = _login(client)
    h = auth_headers(creds["token"])
    up = client.post(
        "/api/kb/documents", files={"file": ("doc.txt", b"hello", "text/plain")}, headers=h
    ).json()["data"]
    r = client.get("/api/kb/documents", headers=h)
    assert r.status_code == 200
    ids = [d["id"] for d in r.json()["data"]]
    assert up["document_id"] in ids


def test_get_documents_no_auth(client):
    r = client.get("/api/kb/documents")
    assert r.status_code == 401


def test_delete_document(client):
    creds = _login(client)
    h = auth_headers(creds["token"])
    up = client.post(
        "/api/kb/documents",
        files={"file": ("doc.txt", b"hi", "text/plain")},
        headers=h,
    ).json()["data"]
    r = client.delete(f"/api/kb/documents/{up['document_id']}", headers=h)
    assert r.status_code == 200
    lst = client.get("/api/kb/documents", headers=h).json()["data"]
    assert all(d["id"] != up["document_id"] for d in lst)


def test_delete_document_not_found(client):
    creds = _login(client)
    h = auth_headers(creds["token"])
    r = client.delete("/api/kb/documents/999999", headers=h)
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "NOT_FOUND"
