from __future__ import annotations

import argparse
import json
from pathlib import Path

from .compiler import compile_job
from .importer import job_from_hrx
from .inspector import inspect_hrx, preview_job
from .models import JobSpec
from .templates import TemplateRegistry
from .variants import generate_variants


def _json(path: str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _write_json(path: Path | None, value: object) -> None:
    text = json.dumps(value, indent=2, ensure_ascii=False) + "\n"
    if path is None:
        print(text, end="")
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(prog="histra-builder")
    sub = parser.add_subparsers(dest="command", required=True)

    compile_p = sub.add_parser("compile")
    compile_p.add_argument("job")
    compile_p.add_argument("--registry", required=True)
    compile_p.add_argument("--output")

    import_p = sub.add_parser("import")
    import_p.add_argument("hrx")
    import_p.add_argument("--job-id", required=True)
    import_p.add_argument("--template-id", required=True)
    import_p.add_argument("--registry", required=True)
    import_p.add_argument("--output")

    inspect_p = sub.add_parser("inspect")
    inspect_p.add_argument("hrx")
    inspect_p.add_argument("--without-geometry", action="store_true")
    inspect_p.add_argument("--output")

    preview_p = sub.add_parser("preview-job")
    preview_p.add_argument("job")
    preview_p.add_argument("--registry", required=True)
    preview_p.add_argument("--output")

    variants_p = sub.add_parser("variants")
    variants_p.add_argument("job")
    variants_p.add_argument("variants")
    variants_p.add_argument("--output-dir", required=True)

    args = parser.parse_args()
    if args.command == "compile":
        artifact = compile_job(_json(args.job), TemplateRegistry(args.registry))
        output = Path(args.output or artifact.output_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(artifact.hrx_bytes)
        print(json.dumps(artifact.provenance, indent=2))
    elif args.command == "import":
        job = job_from_hrx(
            Path(args.hrx).read_bytes(), job_id=args.job_id, template_id=args.template_id,
            registry=TemplateRegistry(args.registry),
        )
        _write_json(Path(args.output) if args.output else None, job.model_dump(mode="json"))
    elif args.command == "inspect":
        value = inspect_hrx(Path(args.hrx).read_bytes()).as_dict(include_geometry=not args.without_geometry)
        _write_json(Path(args.output) if args.output else None, value)
    elif args.command == "preview-job":
        value = preview_job(_json(args.job), TemplateRegistry(args.registry))
        _write_json(Path(args.output) if args.output else None, value)
    elif args.command == "variants":
        output_dir = Path(args.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        for job in generate_variants(_json(args.job), _json(args.variants)):
            _write_json(output_dir / f"{job.job_id}.json", job.model_dump(mode="json"))


if __name__ == "__main__":
    main()
