import json
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app

ROOT = Path(__file__).resolve().parents[1]
REQUEST = json.loads((ROOT / "example_input.json").read_text())
client = TestClient(app)


def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["template"] == "model.hrx"


def test_preview_and_download():
    preview = client.post("/api/jobs/preview", json=REQUEST)
    assert preview.status_code == 200, preview.text
    payload = preview.json()
    assert len(payload["mesh"]["quads"]) > 0
    assert len(payload["model_points"]) == 27

    generated = client.post("/api/jobs/generate/hrx", json=REQUEST)
    assert generated.status_code == 200, generated.text
    assert generated.headers["x-hrx-validation"] == "valid"
    assert generated.content.startswith(b"<?xml")
    assert "first-bridge.hrx" in generated.headers["content-disposition"]

    work_job = client.post("/api/jobs/generate/json", json=REQUEST)
    assert work_job.status_code == 200, work_job.text
    payload = work_job.json()
    assert payload["job_id"] == "first-bridge"
    assert payload["model"]["path"] == "first-bridge.hrx"
    assert payload["generated"]["hrx_validation"]["valid"] is True
    assert len(payload["generated"]["model_points"]) == 27
    displacement_ids = payload["analyses"][0]["outputs"]["displacements"]["model_point_ids"]
    assert len(displacement_ids) == 27
    assert "Pier_1_center_top" in displacement_ids

    # The generated JSON remains valid input for regeneration/re-preview.
    replay = client.post("/api/jobs/preview", json=payload)
    assert replay.status_code == 200, replay.text

    bundle = client.post("/api/jobs/generate/bundle", json=REQUEST)
    assert bundle.status_code == 200, bundle.text
    assert bundle.headers["content-type"].startswith("application/zip")


def test_schema_and_invalid_model_point_output():
    schema = client.get("/api/jobs/schema")
    assert schema.status_code == 200
    assert "job_id" in schema.json()["properties"]

    invalid = json.loads(json.dumps(REQUEST))
    invalid["analyses"][0]["outputs"]["displacements"]["model_point_ids"] = ["missing-point"]
    response = client.post("/api/jobs/generate/json", json=invalid)
    assert response.status_code == 422
    assert "unknown model_point_ids" in response.text


def test_ui_pages():
    generator = client.get("/generator")
    assert generator.status_code == 200
    assert "Model Builder" in generator.text
    assert "/static/generator.js" in generator.text

    viewer = client.get("/viewer")
    assert viewer.status_code == 200
    assert "HiStrA Model Viewer" in viewer.text
    assert "/static/viewer-core.js" in viewer.text

    shared = client.get("/static/viewer-core.js")
    assert shared.status_code == 200
    assert "class QuadViewer" in shared.text


def test_import_and_roundtrip_model1():
    model1 = ROOT / "app" / "templates" / "imported" / "c2736ca1b816be3e0f1fc8989ad5a4b497fac4fc5399a0c09736058fc82575c6.hrx"
    with model1.open("rb") as handle:
        imported = client.post(
            "/api/jobs/import",
            files={"file": ("Model1.hrx", handle, "application/xml")},
        )
    assert imported.status_code == 200, imported.text
    job = imported.json()
    assert job["job_id"] == "Model1"
    assert job["model"]["template_path"].startswith("imported/")
    assert job["Geometry"]["Spans"][0]["Tb"] == 70.0
    assert job["Geometry"]["Spans"][0]["Tt"] == 40.0

    generated = client.post("/api/jobs/generate/hrx", json=job)
    assert generated.status_code == 200, generated.text
    assert generated.content == model1.read_bytes()

    with model1.open("rb") as handle:
        report = client.post(
            "/api/jobs/roundtrip/validate",
            files={"file": ("Model1.hrx", handle, "application/xml")},
        )
    assert report.status_code == 200, report.text
    assert report.json()["roundtrip"]["exact_match"] is True
