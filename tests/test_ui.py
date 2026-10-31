"""Tests for the interactive browser UI and its local HTTP server."""
from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

import pytest
from lxml import etree

from histra_builder.ui import (
    UiPayloadError,
    UiRequestHandler,
    build_preview,
    build_spec,
    default_payload,
    export_hrx,
)


def _post(base: str, path: str, payload: dict, timeout: float = 20.0):
    request = urllib.request.Request(
        base + path,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    return urllib.request.urlopen(request, timeout=timeout)


def _server():
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), UiRequestHandler)
    httpd.daemon_threads = True
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    host, port = httpd.server_address[:2]
    return httpd, thread, f"http://{host}:{port}"


def test_default_preview_has_bridge_geometry() -> None:
    preview = build_preview(default_payload())
    summary = preview["summary"]
    assert summary["width"] == pytest.approx(300.0)
    assert summary["spans"] == 2
    assert summary["piers"] == 1
    assert summary["nodes"] > 100
    assert summary["quads"] > 50
    assert summary["geometry_line_restraints"] > 0
    assert summary["restraints"] == summary["geometry_line_restraints"]
    assert all(len(quad["nodes"]) == 4 for quad in preview["quads"])
    assert preview["materials"]["18"]["name"] == "Masonry"
    assert summary["bounds"]["max"][2] > summary["bounds"]["min"][2]


def test_default_editor_starts_with_a_visible_multi_strip_deck() -> None:
    payload = default_payload()
    assert len(payload["strips"]) == 4
    assert sum(strip["width"] for strip in payload["strips"]) == pytest.approx(300.0)


def test_single_span_payload_has_no_implicit_piers() -> None:
    payload = default_payload()
    payload["spans"] = payload["spans"][:1]
    payload["piers"] = []
    preview = build_preview(payload)
    assert preview["summary"]["spans"] == 1
    assert preview["summary"]["piers"] == 0
    assert preview["summary"]["quads"] > 0


def test_missing_piers_are_filled_from_the_span_count() -> None:
    payload = default_payload()
    payload["spans"].append(dict(payload["spans"][0]))
    payload["piers"] = []
    spec = build_spec(payload)
    assert len(spec.spans) == 3
    assert len(spec.piers) == 2


def test_strip_widths_drive_the_deck_geometry() -> None:
    payload = default_payload()
    payload["strips"] = [
        {"width": 120.0, "height": 0.0, "material_key": 0},
        {"width": 180.0, "height": 20.0, "material_key": 0},
    ]
    spec = build_spec(payload)
    assert spec.width == pytest.approx(300.0)
    assert spec.definition.corsias[0].width == pytest.approx(120.0)
    assert all(span.W == pytest.approx(300.0) for span in spec.spans)
    preview = build_preview(payload)
    assert preview["summary"]["width"] == pytest.approx(300.0)
    assert any(quad["material"] == 21 for quad in preview["quads"])


def test_multi_layer_elevations_reach_the_preview() -> None:
    payload = default_payload()
    payload["elevation"] = {"H1": 140.0, "H2": 70.0, "H3": 45.0}
    preview = build_preview(payload)
    materials = {quad["material"] for quad in preview["quads"]}
    assert {20, 21}.issubset(materials)


def test_export_round_trips_through_the_native_writer() -> None:
    payload = default_payload()
    preview = build_preview(payload)
    data = export_hrx(payload)
    root = etree.fromstring(data)
    assert root.tag == "HiStrA"
    assert root.find("Bridge") is not None
    assert root.find("WizardData") is not None
    assert len(root.findall("Quad")) >= preview["summary"]["quads"]
    assert len(root.findall("GeometryLineRestraint")) == preview["summary"][
        "geometry_line_restraints"
    ]


@pytest.mark.parametrize(
    "mutate, message",
    [
        (lambda payload: payload.update(strips=[]), "at least one strip"),
        (lambda payload: payload.update(spans=[]), "at least one span"),
        (
            lambda payload: payload["strips"].__setitem__(0, {"width": "wide"}),
            "strip.width must be a number",
        ),
    ],
)
def test_invalid_payloads_are_reported(mutate, message) -> None:
    payload = default_payload()
    mutate(payload)
    with pytest.raises(UiPayloadError, match=message):
        build_preview(payload)


def test_http_server_serves_assets_and_api() -> None:
    httpd, thread, base = _server()
    try:
        with urllib.request.urlopen(base + "/api/health", timeout=10) as response:
            assert response.status == 200
            assert json.loads(response.read())["ok"] is True

        with urllib.request.urlopen(base + "/", timeout=10) as response:
            assert response.status == 200
            assert b"HiStrA Bridge Builder" in response.read()

        with urllib.request.urlopen(base + "/app.js", timeout=10) as response:
            assert response.status == 200
            assert b"/api/preview" in response.read()

        with urllib.request.urlopen(base + "/style.css", timeout=10) as response:
            assert response.status == 200
            assert b"--accent" in response.read()

        with _post(base, "/api/preview", default_payload()) as response:
            preview = json.loads(response.read())
            assert response.status == 200
            assert preview["summary"]["quads"] > 0

        with _post(base, "/api/export", default_payload()) as response:
            data = response.read()
            assert response.status == 200
            assert response.headers["Content-Type"].startswith("application/xml")
            assert etree.fromstring(data).find("Quad") is not None

        with pytest.raises(urllib.error.HTTPError) as exc_info:
            _post(base, "/api/preview", {"strips": []})
        assert exc_info.value.code == 400
        assert "at least one strip" in json.loads(exc_info.value.read())["error"]

        with pytest.raises(urllib.error.HTTPError) as exc_info:
            urllib.request.urlopen(base + "/missing", timeout=10)
        assert exc_info.value.code == 404
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=5)
