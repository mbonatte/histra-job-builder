from __future__ import annotations

import argparse
import json
from pathlib import Path

from .compiler import compile_job
from .importer import job_from_hrx
from .templates import TemplateRegistry


def _compile(args: argparse.Namespace) -> int:
    job = json.loads(Path(args.job).read_text(encoding="utf-8"))
    artifact = compile_job(job, TemplateRegistry(args.templates))
    output = Path(args.output or artifact.output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(artifact.hrx_bytes)
    print(json.dumps(artifact.provenance, indent=2, sort_keys=True))
    return 0


def _import(args: argparse.Namespace) -> int:
    data = Path(args.hrx).read_bytes()
    registry = TemplateRegistry(args.templates)
    job = job_from_hrx(
        data,
        job_id=args.job_id,
        template_id=args.template_id,
        output_path=args.output_path,
        registry=registry,
    )
    Path(args.job_output).write_text(
        json.dumps(job.model_dump(mode="json"), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="histra-builder")
    sub = parser.add_subparsers(dest="command", required=True)

    compile_parser = sub.add_parser("compile", help="compile a JOB into an HRX")
    compile_parser.add_argument("job")
    compile_parser.add_argument("--templates", required=True)
    compile_parser.add_argument("--output")
    compile_parser.set_defaults(func=_compile)

    import_parser = sub.add_parser("import", help="create a lossless JOB from an HRX")
    import_parser.add_argument("hrx")
    import_parser.add_argument("--templates", required=True)
    import_parser.add_argument("--job-id", required=True)
    import_parser.add_argument("--template-id", required=True)
    import_parser.add_argument("--output-path", default="model.hrx")
    import_parser.add_argument("--job-output", required=True)
    import_parser.set_defaults(func=_import)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
