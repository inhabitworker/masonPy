"""Local stdlib HTTP adapter and command-line launcher."""

from __future__ import annotations

import argparse
import json
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.resources import files
from typing import Any
from urllib.parse import urlparse

from masonpy.analysis import WallAnalysis, report_vertical_seams
from masonpy.models import Wall
from masonpy.records import MAX_RECORD_BYTES

from .workbench import WorkbenchSession


class MasonPyRequestHandler(BaseHTTPRequestHandler):
    """Translate local JSON/resource requests into operations on the shared workbench session."""

    session: WorkbenchSession
    # Explicit resource inventory: local ES modules, no build tool or path traversal.
    static_files = {
        "/": "index.html",
        "/style.css": "style.css",
        **{
            f"/{name}.js": f"{name}.js"
            for name in (
                "startup",
                "stages",
                "live",
                "pipeline",
                "library",
                "app",
                "api",
                "parameters",
                "tabs",
                "viewer2d",
                "viewer3d",
                "projection",
                "details",
                "diagnostics",
                "playback",
            )
        },
    }
    content_types = {".html": "text/html", ".js": "text/javascript", ".css": "text/css"}

    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        """Serve current state or an explicitly listed packaged static resource."""
        path = urlparse(self.path).path
        if path == "/api/state":
            self._send_json(self.session.to_dict())
            return
        if path == "/api/geometry":
            self._send_json(self.session.geometry_snapshot())
            return
        if path in self.static_files:
            name = self.static_files[path]
            content = files("masonpy.app").joinpath("static", name).read_bytes()
            suffix = "." + name.rsplit(".", 1)[-1]
            self._send_bytes(content, self.content_types[suffix])
            return
        self.send_error(HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        """Dispatch a session mutation or read-only query; invalid input returns HTTP 400."""
        path = urlparse(self.path).path
        try:
            if path == "/api/save":
                data = self._read_json()
                content, filename = self.session.save_record(
                    revision=data.get("revision")
                )
                self._send_bytes(content, "application/json", filename=filename)
                return
            if path == "/api/export":
                data = self._read_json()
                content, mime, filename = self.session.export_stage(
                    data["stage"],
                    scale=data.get("scale", 1),
                    revision=data.get("revision"),
                )
                self._send_bytes(content, mime, filename=filename)
                return
            if path == "/api/info":
                data = self._read_json()
                self._send_json(
                    self.session.inspect(
                        stone_id=data.get("stone_id"),
                        visible_count=data.get("visible_count"),
                    )
                )
                return
            if path == "/api/diagnostics":
                data = self._read_json()
                with self.session._lock:
                    wall = Wall(
                        self.session.wall.width,
                        self.session.wall.height,
                        wrap_x=self.session.wall.wrap_x,
                    )
                    count = data.get("visible_count", len(self.session.wall.stones))
                    for stone in self.session.wall.stones[:count]:
                        wall.add_stone(stone)
                    wrap_x = data.get("wrap_x", False)
                    analysis = WallAnalysis(wall, wrap_x=wrap_x).to_dict()
                    statistics = (
                        analysis["statistics"]
                        if wrap_x == wall.wrap_x
                        else WallAnalysis(wall).statistics()
                    )
                    message = (
                        report_vertical_seams(wall, wrap_x=wrap_x)
                        if data.get("report")
                        else None
                    )
                    limit = (
                        self.session.generator_parameters.get("max_joint_stack")
                        if self.session.generator_parameters.get("enforce_stack")
                        else None
                    )
                self._send_json(
                    {
                        "seams": analysis["vertical_seams"],
                        "message": message,
                        "horizontal_joints": analysis["horizontal_joints"],
                        "statistics": statistics,
                        "max_stack": analysis["statistics"]["max_vertical_stack"],
                        "stack_limit": limit,
                    }
                )
                return
            data = self._read_json()
            # The response and mutation describe one atomic session state, even
            # when another browser submits work at the same time.
            with self.session._lock:
                if path == "/api/reset":
                    self.session.reset(
                        width=int(data["width"]),
                        height=int(data["height"]),
                        generator_id=str(data.get("generator", "running_bond")),
                        generator_parameters=data.get("parameters"),
                    )
                elif path == "/api/load":
                    self.session.load_record(
                        data.get("record"), source_revision=data.get("source_revision")
                    )
                elif path == "/api/history":
                    self.session.select_record(
                        data.get("record_id"),
                        source_revision=data.get("source_revision"),
                    )
                elif path == "/api/shape":
                    self.session.apply_shape(
                        joint_width=data.get("joint_width", 0),
                        distortion=data.get("distortion", 0),
                        seed=data.get("seed", 1),
                        variation_scale=data.get("variation_scale", 6),
                        source_revision=data.get("source_revision"),
                    )
                elif path == "/api/build":
                    settings = dict(data)
                    revision = settings.pop("source_revision", None)
                    self.session.build_3d(settings, source_revision=revision)
                elif path == "/api/step":
                    self.session.step()
                elif path == "/api/generate":
                    self.session.generate_all()
                elif path == "/api/undo":
                    self.session.undo()
                else:
                    self.send_error(HTTPStatus.NOT_FOUND)
                    return
                state = self.session.to_dict()
        except (KeyError, TypeError, ValueError) as error:
            self._send_json({"error": str(error)}, status=HTTPStatus.BAD_REQUEST)
            return
        self._send_json(state)

    def _read_json(self) -> dict[str, Any]:
        """Decode a request body; an empty body is treated as an empty object."""
        length = int(self.headers.get("Content-Length", "0"))
        if not 0 <= length <= MAX_RECORD_BYTES:
            raise ValueError("JSON request exceeds the 32 MiB limit")
        try:
            data = json.loads(self.rfile.read(length) or b"{}")
        except RecursionError as error:
            raise ValueError("JSON nesting is too deep") from error
        if not isinstance(data, dict):
            raise ValueError("JSON request must be an object")
        return data

    def _send_json(self, value: Any, *, status: HTTPStatus = HTTPStatus.OK) -> None:
        """Encode a JSON response using the common byte-response writer."""
        self._send_bytes(json.dumps(value).encode(), "application/json", status=status)

    def _send_bytes(
        self,
        content: bytes,
        content_type: str,
        *,
        status: HTTPStatus = HTTPStatus.OK,
        filename: str | None = None,
    ) -> None:
        """Write status, content metadata and a UTF-8-compatible response body."""
        self.send_response(status)
        # Both session snapshots and local ES modules change during workbench use.
        self.send_header("Cache-Control", "no-store")
        self.send_header(
            "Content-Type",
            content_type
            if content_type == "model/stl"
            else f"{content_type}; charset=utf-8",
        )
        if filename:
            self.send_header(
                "Content-Disposition", f'attachment; filename="{filename}"'
            )
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def log_message(self, format: str, *args: object) -> None:
        """Suppress routine stdlib access logs; construction/diagnostic logs remain explicit."""
        pass


def make_server(host: str = "127.0.0.1", port: int = 8000) -> ThreadingHTTPServer:
    """Bind a local HTTP server with one independent session; the caller owns its lifetime."""
    handler = type("ConfiguredMasonPyHandler", (MasonPyRequestHandler,), {})
    handler.session = WorkbenchSession()
    return ThreadingHTTPServer((host, port), handler)


def main() -> None:
    """Parse launcher arguments, optionally open a browser, and serve until interrupted."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=8000, type=int)
    parser.add_argument("--open", action="store_true", help="open a browser tab")
    args = parser.parse_args()

    server = make_server(args.host, args.port)
    url = f"http://{args.host}:{server.server_port}"
    print(f"MasonPy web app: {url}")
    if args.open:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping MasonPy.")
    finally:
        server.server_close()
