import sys, os, io, pytest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from app import create_app

@pytest.fixture
def client(tmp_path):
    app = create_app({"TESTING": True, "DB_PATH": str(tmp_path / "test.db")})
    with app.test_client() as c:
        yield c

def test_upload_txt_returns_note_id(client):
    content = b"BP: 120/80. HR: 72. Patient takes lisinopril 10 mg PO daily."
    data = {"file": (io.BytesIO(content), "note.txt", "text/plain")}
    resp = client.post("/api/upload", data=data, content_type="multipart/form-data")
    assert resp.status_code == 201
    assert "note_id" in resp.get_json()

def test_upload_returns_extracted_json(client):
    content = b"BP: 130/85. HR: 68."
    data = {"file": (io.BytesIO(content), "note.txt", "text/plain")}
    resp = client.post("/api/upload", data=data, content_type="multipart/form-data")
    body = resp.get_json()
    assert "extracted_json" in body
    assert "vitals" in body["extracted_json"]

def test_upload_no_file_returns_400(client):
    resp = client.post("/api/upload", data={}, content_type="multipart/form-data")
    assert resp.status_code == 400

def test_upload_unsupported_extension_returns_400(client):
    data = {"file": (io.BytesIO(b"hello"), "note.doc", "application/msword")}
    resp = client.post("/api/upload", data=data, content_type="multipart/form-data")
    assert resp.status_code == 400
    assert resp.get_json()["code"] == "UNSUPPORTED_FILE_TYPE"
