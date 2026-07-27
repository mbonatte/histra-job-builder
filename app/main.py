from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path
from urllib.parse import quote

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from .contracts import BUILDER_VERSION, job_sha256
from .lossless_import import import_losslessly
from .schemas import GenerationRequest
from .service import GeneratorService
from .template import TemplateRepository
from .work_jobs import generated_work_job, generation_report, validate_requested_model_points

BASE_DIR = Path(__file__).resolve().parent
TEMPLATE_PATH = BASE_DIR / "templates" / "model.hrx"
STATIC_DIR = BASE_DIR / "static"

app = FastAPI(title="HiStrA HRX Work-Job Generator", version=BUILDER_VERSION)
service = GeneratorService(TEMPLATE_PATH)


def _generate_validated(request: GenerationRequest):
    try:
        result = service.generate(request)
    except (ValueError, KeyError, FileNotFoundError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    work_job_errors = validate_requested_model_points(request, result)
    if work_job_errors:
        raise HTTPException(status_code=422, detail={"message": "Invalid work-job outputs", "errors": work_job_errors})
    if not result.validation.valid:
        raise HTTPException(
            status_code=422,
            detail={
                "message": "Generated HRX failed validation",
                "validation": result.validation.model_dump(),
                "model_points": [point.as_dict() for point in result.model_points],
                "analyses": result.analyses,
            },
        )
    return result


def _template_metadata(request: GenerationRequest | None = None) -> tuple[str | None, str | None, str]:
    path = service.resolve_template(request) if request is not None else TEMPLATE_PATH
    tree = TemplateRepository(path).load()
    root = tree.getroot()
    return root.get("version"), root.get("WizardType"), path.name


def _download_headers(filename: str) -> dict[str, str]:
    return {"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"}


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "template": TEMPLATE_PATH.name, "schema_version": "1.0"}


@app.get("/api/template")
def template_info() -> dict:
    tree = service.repository.load()
    root = tree.getroot()
    materials = [
        {"key": item.get("Key"), "name": item.get("Name"), "type": item.get("TypeOf")}
        for item in root.findall("Template")
        if "Material" in item.get("TypeOf", "")
    ]
    return {
        "name": TEMPLATE_PATH.name,
        "version": root.get("version"),
        "wizardType": root.get("WizardType"),
        "workJobSchemaVersion": "1.0",
        "materials": materials,
    }


@app.get("/api/jobs/schema")
def work_job_schema() -> dict:
    schema = GenerationRequest.model_json_schema(by_alias=True)
    # Legacy compatibility inputs remain accepted by Pydantic but are not part
    # of the documented v1.0 work-job contract.
    properties = schema.get("properties", {})
    properties.pop("Analysis", None)
    properties.pop("OutputName", None)
    required = schema.get("required")
    if isinstance(required, list):
        schema["required"] = [item for item in required if item not in {"Analysis", "OutputName"}]
    return schema


@app.get("/api/jobs/example")
def work_job_example():
    return FileResponse(STATIC_DIR / "example_input.json", media_type="application/json")


# ---------------------------------------------------------------------------
# HRX import / round-trip API
# ---------------------------------------------------------------------------


@app.post("/api/jobs/import")
async def import_hrx_job(file: UploadFile = File(...), job_id: str | None = Form(default=None)):
    data = await file.read()
    if not data:
        raise HTTPException(status_code=422, detail="The uploaded HRX file is empty")
    try:
        imported = import_losslessly(
            data,
            file.filename or "imported-model.hrx",
            compiler=service,
            job_id=job_id,
        )
    except (ValueError, KeyError, FileNotFoundError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return JSONResponse(content=imported.job)


@app.post("/api/jobs/roundtrip/validate")
async def validate_hrx_roundtrip(file: UploadFile = File(...), job_id: str | None = Form(default=None)):
    source = await file.read()
    if not source:
        raise HTTPException(status_code=422, detail="The uploaded HRX file is empty")
    try:
        imported = import_losslessly(
            source,
            file.filename or "imported-model.hrx",
            compiler=service,
            job_id=job_id,
        )
    except (ValueError, KeyError, FileNotFoundError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {
        "job": imported.job,
        "roundtrip": imported.comparison,
        "hrx_validation": imported.validation,
    }


# ---------------------------------------------------------------------------
# Work-job API
# ---------------------------------------------------------------------------


@app.post("/api/jobs/preview")
def preview_job(request: GenerationRequest):
    try:
        return service.preview(request)
    except (ValueError, KeyError, FileNotFoundError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/api/jobs/generate/hrx")
def generate_job_hrx(request: GenerationRequest):
    result = _generate_validated(request)
    payload = request.model_dump(by_alias=True, exclude_none=True)
    headers = {
        **_download_headers(request.hrx_filename),
        "X-HRX-Validation": "valid",
        "X-HRX-Counts": json.dumps(result.validation.counts, separators=(",", ":")),
        "X-Job-Id": request.job_id,
        "X-Job-SHA256": job_sha256(payload),
        "X-Builder-Version": BUILDER_VERSION,
    }
    return Response(content=result.xml, media_type="application/xml", headers=headers)


@app.post("/api/jobs/generate/json")
def generate_job_json(request: GenerationRequest):
    result = _generate_validated(request)
    template_version, _, template_name = _template_metadata(request)
    payload = generated_work_job(
        request,
        result,
        template_name=template_name,
        template_version=template_version,
    )
    return Response(
        content=json.dumps(payload, indent=2, ensure_ascii=False).encode("utf-8"),
        media_type="application/json",
        headers=_download_headers(request.job_filename),
    )


@app.post("/api/jobs/generate/report")
def generate_job_report(request: GenerationRequest):
    result = _generate_validated(request)
    payload = generation_report(request, result)
    filename = f"{request.job_id}.report.json"
    return Response(
        content=json.dumps(payload, indent=2, ensure_ascii=False).encode("utf-8"),
        media_type="application/json",
        headers=_download_headers(filename),
    )


@app.post("/api/jobs/generate")
@app.post("/api/jobs/generate/bundle")
def generate_job_bundle(request: GenerationRequest):
    """Download the HRX, runner-ready work job, and validation report together."""

    result = _generate_validated(request)
    template_version, _, template_name = _template_metadata(request)
    work_job = generated_work_job(
        request,
        result,
        template_name=template_name,
        template_version=template_version,
    )
    report = generation_report(request, result)

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(request.hrx_filename, result.xml)
        archive.writestr(
            request.job_filename,
            json.dumps(work_job, indent=2, ensure_ascii=False).encode("utf-8"),
        )
        archive.writestr(
            f"{request.job_id}.report.json",
            json.dumps(report, indent=2, ensure_ascii=False).encode("utf-8"),
        )
    headers = {
        **_download_headers(f"{request.job_id}.zip"),
        "X-HRX-Validation": "valid",
        "X-Job-Id": request.job_id,
    }
    return Response(content=buffer.getvalue(), media_type="application/zip", headers=headers)


# ---------------------------------------------------------------------------
# Backward-compatible model endpoints. They accept the same work-job schema.
# ---------------------------------------------------------------------------


@app.post("/api/models/preview")
def preview_model(request: GenerationRequest):
    return preview_job(request)


@app.post("/api/models/generate")
def generate_model(request: GenerationRequest):
    return generate_job_hrx(request)


@app.post("/api/models/generate-report")
def generate_model_report(request: GenerationRequest):
    result = _generate_validated(request)
    return JSONResponse(content=generation_report(request, result))


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/", include_in_schema=False)
def index():
    return FileResponse(STATIC_DIR / "generator.html")


@app.get("/generator", include_in_schema=False)
def generator_page():
    return FileResponse(STATIC_DIR / "generator.html")


@app.get("/viewer", include_in_schema=False)
def viewer_page():
    return FileResponse(STATIC_DIR / "viewer.html")
