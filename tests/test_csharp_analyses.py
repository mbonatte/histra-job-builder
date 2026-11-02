"""Native parity for the generated load and analysis schema."""
from __future__ import annotations

import json
from pathlib import Path

from lxml import etree

from histra_builder.generator.csharp_writer import generate_csharp_bridge_hrx
from histra_builder.generator.native_analysis import (
    ANALYSIS_ORDER,
    LOAD_CONDITIONS,
    LOAD_COMBINATIONS,
    STRICT_EQUILIBRIUM_ANALYSES,
)
from histra_builder.ui import build_spec, default_payload

FIXTURE = Path(__file__).parent / "fixtures" / "csharp" / "analyses.json"


def _root(*, include_scour: bool = True) -> etree._Element:
    return etree.fromstring(
        generate_csharp_bridge_hrx(
            build_spec(default_payload()), include_scour_analyses=include_scour
        )
    )


def _native() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def _with_pipeline_equilibrium(attributes: dict[str, str]) -> dict[str, str]:
    if attributes.get("Name") in STRICT_EQUILIBRIUM_ANALYSES:
        return {**attributes, "AdapticConvergenceCriteria": "ForceMoment"}
    return attributes


def test_generated_analyses_match_native_attributes_and_order() -> None:
    root = _root()
    expected = {item["attributes"]["Name"]: item["attributes"] for item in _native()["analyses"]}
    analyses = root.findall("Analysis")
    assert [analysis.get("Name") for analysis in analyses] == list(ANALYSIS_ORDER)
    assert [analysis.get("Key") for analysis in analyses] == [
        expected[name]["Key"] for name in ANALYSIS_ORDER
    ]
    for analysis in analyses:
        name = analysis.get("Name")
        assert dict(analysis.attrib) == _with_pipeline_equilibrium(expected[name]), name


def test_analysis_states_and_model_point_links_are_native() -> None:
    root = _root()
    points = [point.get("Key") for point in root.findall("ModelPoint")]
    assert points
    for analysis in root.findall("Analysis"):
        state = analysis.find("States/State")
        assert state is not None
        assert state.get("Key") == analysis.get("Key")
        assert state.get("Step") == "0"
        assert state.get("State") == "NotExecutedNotToBeExecuted"
        assert state.get("Exit") == "NotExecuted"
        active = analysis.findall("ActiveModelPoints/ActiveModelPoint")
        displacement = analysis.findall("DisplModelPoints/DisplModelPoint")
        assert [item.get("Key") for item in active] == points
        assert [item.get("Key") for item in displacement] == points
        assert [item.get("Value") for item in active] == ["true"] * len(points)
        assert [item.get("Value") for item in displacement] == ["0"] * len(points)
        assert analysis.get("MasterPoint") == points[0]
        assert analysis.find("DynamicLoads") is not None
        assert analysis.find("StageDefinitions") is not None
        assert analysis.find("StageItems") is not None
        assert analysis.find("PushModalSettings") is not None


def test_live_load_analyses_carry_the_native_default_phase() -> None:
    root = _root()
    for analysis in root.findall("Analysis"):
        phases = analysis.findall("AdapticPhases/AdapticPhase")
        if analysis.get("Name", "").startswith("LiveLoad"):
            assert len(phases) == 1
            assert phases[0].get("ParentKey") == analysis.get("Key")
            assert phases[0].get("ModelPointKey") == root.find("ModelPoint").get("Key")
            assert phases[0].get("Direction") == "z"
        else:
            assert phases == []


def test_load_conditions_combinations_and_functions_match_native() -> None:
    root = _root()
    native = _native()

    assert [dict(element.attrib) for element in root.findall("LoadCondition")] == native[
        "load_conditions"
    ]
    assert [dict(element.attrib) for element in root.findall("LoadCombination")] == [
        item["attributes"] for item in native["load_combinations"]
    ]
    assert [dict(element.attrib) for element in root.findall("LoadFunction")] == native[
        "load_functions"
    ]
    assert [dict(element.attrib) for element in root.findall("LoadFunctionItem")] == native[
        "load_function_items"
    ]
    for combination in root.findall("LoadCombination"):
        expected = next(
            item for item in native["load_combinations"]
            if item["attributes"]["Key"] == combination.get("Key")
        )
        assert [dict(element.attrib) for element in combination] == expected["items"]


def test_native_load_schema_constants_stay_in_sync_with_fixture() -> None:
    native = _native()
    assert [condition["Id"] for condition in LOAD_CONDITIONS] == [
        element["Id"] for element in native["load_conditions"]
    ]
    assert [combination[0] for combination in LOAD_COMBINATIONS] == [
        item["attributes"]["Key"] for item in native["load_combinations"]
    ]
    assert len(_root().findall("LoadFunction")) == 32


def test_scour_functions_ramp_like_native_and_use_zero_multiplier() -> None:
    root = _root()
    for key in ("23", "24"):
        items = [
            item
            for item in root.findall("LoadFunctionItem")
            if item.get("loadFunctionKey") == key
        ]
        assert [item.get("multiplier") for item in items] == ["0", "1"]
    for name in ("scour_1", "scour_2", "scour_3", "scour_4"):
        assert root.xpath(f"/HiStrA/Analysis[@Name='{name}']")[0].get("Mult") == "0"
    assert root.xpath("/HiStrA/Analysis[@Name='Vert']")[0].get("Mult") == "1"


def test_without_scour_analyses_references_stay_resolvable() -> None:
    root = _root(include_scour=False)
    present = {analysis.get("Key") for analysis in root.findall("Analysis")}
    assert present == {"1", "21", "29", "30"}
    for analysis in root.findall("Analysis"):
        initial = analysis.get("InitialAnalysisKey")
        assert initial in present or initial == "-100"
        assert analysis.get("PushModal_ModalAnalysisKey") in present
