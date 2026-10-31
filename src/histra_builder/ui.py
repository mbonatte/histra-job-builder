"""Local web UI for interactive C#-parity bridge generation.

The UI is deliberately dependency-free: Python's standard-library HTTP server
serves static HTML/JS, and the browser renders the generated quad mesh on a
2D canvas with an orbitable 3D projection.
"""
from __future__ import annotations

import json
import threading
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, List
from urllib.parse import urlparse

from .generator.csharp_mesher import build_csharp_bridge_mesh
from .generator.csharp_model import (
    Abutment,
    BridgeDefinition,
    CSharpBridgeSpec,
    Corsia,
    Elevation,
    Elevations,
    Pier,
    Span,
)
from .generator.csharp_writer import generate_csharp_bridge_hrx
from .generator.materials import material_colors

WEB_ROOT = Path(__file__).with_name("web")
MAX_REQUEST_BYTES = 2 * 1024 * 1024
DEFAULT_SPRINGING_ANGLE = 36.8699


class UiPayloadError(ValueError):
    """Raised when the browser submits an invalid bridge description."""


def _number(value: Any, name: str, default: float = 0.0) -> float:
    if value is None or value == "":
        return default
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise UiPayloadError(f"{name} must be a number") from exc


def _integer(value: Any, name: str, default: int = 0) -> int:
    if value is None or value == "":
        return default
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise UiPayloadError(f"{name} must be an integer") from exc


def default_payload() -> Dict[str, Any]:
    """A valid starter bridge for the editor."""
    return {
        "name": "InteractiveBridge",
        "width": 300.0,
        "nl": 60.0,
        "strips": [
            {"width": 75.0, "height": 0.0, "material_key": 0},
            {"width": 75.0, "height": 0.0, "material_key": 0},
            {"width": 75.0, "height": 0.0, "material_key": 0},
            {"width": 75.0, "height": 0.0, "material_key": 0},
        ],
        "spans": [
            {
                "L": 400.0,
                "f": 100.0,
                "Tb": 30.0,
                "Tt": 25.0,
                "Asx": DEFAULT_SPRINGING_ANGLE,
                "Adx": DEFAULT_SPRINGING_ANGLE,
                "S1": 0.0,
                "S2": 0.0,
                "Dz": 0.0,
            },
            {
                "L": 400.0,
                "f": 100.0,
                "Tb": 30.0,
                "Tt": 25.0,
                "Asx": DEFAULT_SPRINGING_ANGLE,
                "Adx": DEFAULT_SPRINGING_ANGLE,
                "S1": 0.0,
                "S2": 0.0,
                "Dz": 0.0,
            },
        ],
        "piers": [
            {
                "H": 150.0,
                "Hf": 60.0,
                "b2": 70.0,
                "B1f": 30.0,
                "B3f": 30.0,
                "W1f": 20.0,
                "W3f": 20.0,
            }
        ],
        "left_abutment": {
            "H": 80.0,
            "Hf": 50.0,
            "b2": 90.0,
            "B1f": 0.0,
            "B3f": 0.0,
            "W1f": 0.0,
            "W3f": 0.0,
        },
        "right_abutment": {
            "H": 80.0,
            "Hf": 50.0,
            "b2": 90.0,
            "B1f": 0.0,
            "B3f": 0.0,
            "W1f": 0.0,
            "W3f": 0.0,
        },
        "elevation": {"H1": 175.0, "H2": 0.0, "H3": 0.0},
    }


def _abutment(raw: Dict[str, Any], kind: str) -> Abutment:
    return Abutment(
        b2=_number(raw.get("b2"), "abutment.b2", 90.0),
        H=_number(raw.get("H"), "abutment.H", 80.0),
        Hf=_number(raw.get("Hf"), "abutment.Hf", 50.0),
        B1f=_number(raw.get("B1f"), "abutment.B1f", 0.0),
        B3f=_number(raw.get("B3f"), "abutment.B3f", 0.0),
        W1f=_number(raw.get("W1f"), "abutment.W1f", 0.0),
        W3f=_number(raw.get("W3f"), "abutment.W3f", 0.0),
        w2=_number(raw.get("w2"), "abutment.w2", 0.0),
        material_key=18,
        material_foundation_key=141,
        kind=kind,
    )


def _pier(raw: Dict[str, Any], width: float) -> Pier:
    return Pier(
        b2=_number(raw.get("b2"), "pier.b2", 70.0),
        H=_number(raw.get("H"), "pier.H", 150.0),
        Hf=_number(raw.get("Hf"), "pier.Hf", 60.0),
        B1f=_number(raw.get("B1f"), "pier.B1f", 0.0),
        B3f=_number(raw.get("B3f"), "pier.B3f", 0.0),
        W1f=_number(raw.get("W1f"), "pier.W1f", 0.0),
        W3f=_number(raw.get("W3f"), "pier.W3f", 0.0),
        w2=width,
        material_key=18,
        material_foundation_key=141,
    )


def _span(raw: Dict[str, Any], width: float) -> Span:
    return Span(
        L=_number(raw.get("L"), "span.L", 400.0),
        W=width,
        f=_number(raw.get("f"), "span.f", 100.0),
        Tb=_number(raw.get("Tb"), "span.Tb", 30.0),
        Tt=_number(raw.get("Tt"), "span.Tt", 25.0),
        Asx=_number(raw.get("Asx"), "span.Asx", DEFAULT_SPRINGING_ANGLE),
        Adx=_number(raw.get("Adx"), "span.Adx", DEFAULT_SPRINGING_ANGLE),
        S1=_number(raw.get("S1"), "span.S1", 0.0),
        S2=_number(raw.get("S2"), "span.S2", 0.0),
        Dz=_number(raw.get("Dz"), "span.Dz", 0.0),
        material_key=18,
        material_pulvino_key=22,
        material_reinforcement_key=24,
    )


def build_spec(payload: Dict[str, Any]) -> CSharpBridgeSpec:
    """Convert the browser payload into a validated C# bridge spec."""
    if not isinstance(payload, dict):
        raise UiPayloadError("payload must be an object")
    raw_strips = payload.get("strips")
    if not isinstance(raw_strips, list) or not raw_strips:
        raise UiPayloadError("at least one strip is required")
    strips = [
        Corsia(
            width=_number(item.get("width"), "strip.width", 300.0),
            height=_number(item.get("height"), "strip.height", 0.0),
            material_key=_integer(item.get("material_key"), "strip.material_key", 0),
        )
        for item in raw_strips
        if isinstance(item, dict)
    ]
    if not strips:
        raise UiPayloadError("at least one valid strip is required")
    width = sum(strip.width for strip in strips)
    if width <= 0:
        raise UiPayloadError("total bridge width must be positive")

    raw_spans = payload.get("spans")
    if not isinstance(raw_spans, list) or not raw_spans:
        raise UiPayloadError("at least one span is required")
    spans = [_span(item, width) for item in raw_spans if isinstance(item, dict)]
    if not spans:
        raise UiPayloadError("at least one valid span is required")

    raw_piers = payload.get("piers")
    if not isinstance(raw_piers, list):
        raw_piers = []
    piers = [_pier(item, width) for item in raw_piers if isinstance(item, dict)]
    needed = max(0, len(spans) - 1)
    while len(piers) < needed:
        piers.append(_pier({}, width))
    piers = piers[:needed]

    left_raw = payload.get("left_abutment")
    right_raw = payload.get("right_abutment")
    left = _abutment(left_raw if isinstance(left_raw, dict) else {}, "Sinistra")
    right = _abutment(right_raw if isinstance(right_raw, dict) else {}, "Destra")
    left.w2 = width
    right.w2 = width
    elevation_raw = payload.get("elevation")
    if not isinstance(elevation_raw, dict):
        elevation_raw = {}
    elevation = Elevation(
        X=0.0,
        H1=_number(elevation_raw.get("H1"), "elevation.H1", 175.0),
        H2=_number(elevation_raw.get("H2"), "elevation.H2", 0.0),
        H3=_number(elevation_raw.get("H3"), "elevation.H3", 0.0),
    )

    elements: List[object] = [left]
    for index, span in enumerate(spans):
        elements.append(span)
        if index < len(piers):
            elements.append(piers[index])
    elements.append(right)

    definition = BridgeDefinition(
        width=width,
        width_top_pile=width,
        nl=_number(payload.get("nl"), "nl", 60.0),
        nt=20000.0,
        inclination_angle=0.0,
        slope=0.0,
        zlevel=500.0,
        thickness_ballast=0.0,
        thickness_riempimento=0.0,
        corsias=strips,
    )
    try:
        return CSharpBridgeSpec(
            definition=definition,
            elements=elements,
            elevations=Elevations([elevation]),
        )
    except Exception as exc:
        raise UiPayloadError(str(exc)) from exc


def _bounds(nodes: Dict[int, Any]) -> Dict[str, List[float]] | None:
    if not nodes:
        return None
    points = list(nodes.values())
    return {
        "min": [min(point.x for point in points), min(point.y for point in points), min(point.z for point in points)],
        "max": [max(point.x for point in points), max(point.y for point in points), max(point.z for point in points)],
    }


def build_preview(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Generate a serializable preview payload for the browser."""
    spec = build_spec(payload)
    try:
        mesh = build_csharp_bridge_mesh(spec)
    except Exception as exc:
        raise UiPayloadError(str(exc)) from exc
    return {
        "summary": {
            "width": spec.width,
            "spans": len(spec.spans),
            "piers": len(spec.piers),
            "nodes": len(mesh.nodes),
            "quads": len(mesh.quads),
            "geometry_line_restraints": len(mesh.geometry_line_restraints),
            "restraints": len(mesh.restraints),
            "bounds": _bounds(mesh.nodes),
        },
        "nodes": [
            [key, round(point.x, 6), round(point.y, 6), round(point.z, 6)]
            for key, point in sorted(mesh.nodes.items())
        ],
        "quads": [
            {
                "key": quad.key,
                "nodes": list(quad.node_keys),
                "material": quad.material_key,
                "group": quad.group,
            }
            for quad in mesh.quads.values()
        ],
        "glrs": [
            {
                "key": glr.key,
                "nodes": [glr.node_key1, glr.node_key2],
                "b": glr.b,
                "h": glr.h,
            }
            for glr in mesh.geometry_line_restraints
        ],
        "restraints": [
            {
                "key": restraint.key,
                "nodes": [restraint.node_key1, restraint.node_key2],
                "quad": restraint.computational_element_key,
            }
            for restraint in mesh.restraints
        ],
        "materials": material_colors(),
    }


def export_hrx(payload: Dict[str, Any]) -> bytes:
    spec = build_spec(payload)
    try:
        return generate_csharp_bridge_hrx(spec, include_scour_analyses=True)
    except Exception as exc:
        raise UiPayloadError(str(exc)) from exc


class UiRequestHandler(BaseHTTPRequestHandler):
    server_version = "HistraBuilderUI/1.0"

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A003
        # Keep the CLI clean unless debugging.
        return

    def _send_json(self, status: int, value: Any) -> None:
        data = json.dumps(value, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _send_bytes(self, status: int, data: bytes, content_type: str, filename: str | None = None) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        if filename:
            self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
        self.end_headers()
        self.wfile.write(data)

    def _read_json(self) -> Dict[str, Any]:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError as exc:
            raise UiPayloadError("invalid Content-Length") from exc
        if length <= 0:
            raise UiPayloadError("empty request body")
        if length > MAX_REQUEST_BYTES:
            raise UiPayloadError("request body is too large")
        try:
            payload = json.loads(self.rfile.read(length))
        except json.JSONDecodeError as exc:
            raise UiPayloadError(f"invalid JSON: {exc}") from exc
        if not isinstance(payload, dict):
            raise UiPayloadError("payload must be an object")
        return payload

    def do_GET(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        if path == "/api/health":
            self._send_json(HTTPStatus.OK, {"ok": True, "service": "histra-builder-ui"})
            return
        if path == "/api/default":
            self._send_json(HTTPStatus.OK, default_payload())
            return
        static = {
            "/": ("index.html", "text/html; charset=utf-8"),
            "/index.html": ("index.html", "text/html; charset=utf-8"),
            "/app.js": ("app.js", "text/javascript; charset=utf-8"),
            "/style.css": ("style.css", "text/css; charset=utf-8"),
        }
        entry = static.get(path)
        if entry is None:
            self._send_json(HTTPStatus.NOT_FOUND, {"error": "not found"})
            return
        file_path = WEB_ROOT / entry[0]
        try:
            data = file_path.read_bytes()
        except FileNotFoundError:
            self._send_json(HTTPStatus.NOT_FOUND, {"error": f"missing asset {entry[0]}"})
            return
        self._send_bytes(HTTPStatus.OK, data, entry[1])

    def do_POST(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        try:
            payload = self._read_json()
            if path == "/api/preview":
                self._send_json(HTTPStatus.OK, build_preview(payload))
            elif path == "/api/export":
                data = export_hrx(payload)
                self._send_bytes(
                    HTTPStatus.OK,
                    data,
                    "application/xml; charset=utf-8",
                    "bridge.hrx",
                )
            else:
                self._send_json(HTTPStatus.NOT_FOUND, {"error": "not found"})
        except UiPayloadError as exc:
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
        except Exception as exc:  # pragma: no cover - defensive
            self._send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(exc)})


def serve(
    host: str = "127.0.0.1",
    port: int = 8765,
    *,
    open_browser: bool = True,
    server: ThreadingHTTPServer | None = None,
) -> ThreadingHTTPServer:
    httpd = server or ThreadingHTTPServer((host, port), UiRequestHandler)
    bound_host, bound_port = httpd.server_address[:2]
    url = f"http://{bound_host}:{bound_port}/"
    print(f"HiStrA builder UI: {url}")
    if open_browser:
        threading.Timer(0.35, lambda: webbrowser.open(url)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
    return httpd
