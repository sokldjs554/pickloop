from io import BytesIO

from fastapi.testclient import TestClient
from PIL import Image
from pickloop.server import create_app


def test_photo_upload_returns_same_readout_without_saving_upload(tmp_path, monkeypatch):
    from pickloop import grocery_catalogue
    def recognize(rgb, **options):
        assert rgb.shape == (16, 20, 3)
        assert options["require_gtin"]
        return dict(photo_name="Apple", prediction="UNKNOWN", confirmed_order_sku=None, printed_fruit_words=["apple"])
    monkeypatch.setattr(grocery_catalogue, "recognize_rgb", recognize)
    picture = BytesIO()
    Image.new("RGB", (20, 16), "navy").save(picture, "JPEG")
    with TestClient(create_app(tmp_path)) as client:
        assert client.get("/api/health").json()["photo_recognition"] is True
        response = client.post("/api/recognize?require_gtin=true", content=picture.getvalue(), headers={"Content-Type": "image/jpeg"})
    assert response.status_code == 200
    assert response.json()["photo_name"] == "Apple"
    assert not list(tmp_path.rglob("*.jpg"))


def test_invalid_and_oversize_uploads_rejected_before_inference(tmp_path):
    with TestClient(create_app(tmp_path)) as client:
        assert client.post("/api/recognize", content=b"this is not a photo", headers={"Content-Type": "image/jpeg"}).status_code == 400
        assert client.post("/api/recognize", content=b"{}", headers={"Content-Type": "application/json"}).status_code == 415
        assert client.post("/api/recognize", content=b"x" * (12 * 1024 * 1024 + 1), headers={"Content-Type": "image/jpeg"}).status_code == 413
