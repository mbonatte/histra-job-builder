"""Material-template parity against the native C# reference model."""
from __future__ import annotations

import json
from pathlib import Path

from histra_builder.generator.materials import DEFAULT_TEMPLATES

FIXTURE = Path(__file__).parent / "fixtures" / "csharp" / "templates.json"


def test_default_templates_match_native_reference_exactly() -> None:
    expected = json.loads(FIXTURE.read_text(encoding="utf-8"))
    actual = {str(template["Key"]): template for template in DEFAULT_TEMPLATES}
    assert set(actual) == set(expected) == {"18", "19", "22", "141", "146", "147"}
    for key, native in expected.items():
        assert actual[key] == native, f"template {key} differs from native reference"


def test_material_template_order_is_stable() -> None:
    assert [template["Key"] for template in DEFAULT_TEMPLATES] == [
        "18",
        "19",
        "22",
        "141",
        "146",
        "147",
    ]
