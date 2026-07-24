from __future__ import annotations

import copy
from typing import Any

from lxml import etree

from .model_points import ModelPointSelection
from .schemas import GenerationRequest
from .xml_utils import clear_children, direct_children, ensure_child


RUN_STATE = "NotExecutedToBeExecute"


def _choose_archetype(
    existing: list[etree._Element],
    requested_name: str,
) -> etree._Element:
    """Choose the closest analysis already present in model.hrx.

    Exact names are preferred (Vert, scour_1, Modal_1, ...). New modal names use
    AnalysisType=5; all other custom names use the first non-modal analysis,
    normally Vert/AnalysisType=2.
    """

    for analysis in existing:
        if analysis.get("Name") == requested_name:
            return copy.deepcopy(analysis)

    wants_modal = requested_name.lower().startswith("modal")
    desired_type = "5" if wants_modal else "2"
    for analysis in existing:
        if analysis.get("AnalysisType") == desired_type:
            return copy.deepcopy(analysis)

    if not existing:
        raise ValueError("model.hrx contains no Analysis archetype")
    return copy.deepcopy(existing[0])


def _patch_model_point_lists(analysis: etree._Element, selections: list[ModelPointSelection]) -> None:
    active = ensure_child(analysis, "ActiveModelPoints")
    clear_children(active)
    displacement = ensure_child(analysis, "DisplModelPoints")
    clear_children(displacement)
    for index, _selection in enumerate(selections, start=1):
        etree.SubElement(active, "ActiveModelPoint", Key=str(index), Value="true")
        etree.SubElement(displacement, "DisplModelPoint", Key=str(index), Value="0")


def rebuild_analyses(
    root: etree._Element,
    request: GenerationRequest,
    selections: list[ModelPointSelection],
) -> list[dict[str, Any]]:
    existing = direct_children(root, "Analysis")
    insertion_index = root.index(existing[0]) if existing else len(root)
    archetypes = [copy.deepcopy(analysis) for analysis in existing]
    for analysis in existing:
        root.remove(analysis)

    defaults = request.AnalysisParameters.Defaults.model_dump(exclude_none=True)
    generated: list[dict[str, Any]] = []
    for index, job_analysis in enumerate(request.analyses, start=1):
        name = job_analysis.name
        scenario = job_analysis.interfaces
        analysis = _choose_archetype(archetypes, name)
        source_name = analysis.get("Name")
        analysis.set("Key", str(index))
        analysis.set("Name", name)
        analysis.set("Description", f"Generated analysis {name}")
        if analysis.get("PushModal_ModalAnalysisKey") is not None:
            analysis.set("PushModal_ModalAnalysisKey", str(index))

        for attr, value in defaults.items():
            analysis.set(attr, str(value))
        by_name = request.AnalysisParameters.ByName.get(name)
        if by_name is not None:
            for attr, value in by_name.model_dump(exclude_none=True).items():
                analysis.set(attr, str(value))

        states = ensure_child(analysis, "States")
        if not direct_children(states, "State"):
            etree.SubElement(states, "State", Id="1", Combination="1", Step="0", Fo="0", Exit="NotExecuted")
        for state in direct_children(states, "State"):
            state.set("Key", str(index))
            state.set("State", RUN_STATE)
            state.set("Exit", "NotExecuted")
            state.attrib.pop("ExitDescription", None)
        _patch_model_point_lists(analysis, selections)
        root.insert(insertion_index + index - 1, analysis)
        generated.append(
            {
                "key": index,
                "name": name,
                "sourceArchetype": source_name,
                "analysisType": analysis.get("AnalysisType"),
                "convergenceTolerance": analysis.get("ConvergenceTolerance"),
                "numberOfEigenModes": analysis.get("NumberOfEigenModes"),
                "state": RUN_STATE,
                "scenario": scenario,
                "scenarioEncodedInHrx": False,
                "timeoutSeconds": job_analysis.timeout_seconds,
                "outputs": job_analysis.outputs.model_dump(exclude_none=True),
            }
        )
    return generated


def summarize_existing_analyses(root: etree._Element) -> list[dict[str, Any]]:
    return [
        {
            "key": int(analysis.get("Key", str(index))),
            "name": analysis.get("Name", f"Analysis_{index}"),
            "sourceArchetype": analysis.get("Name"),
            "analysisType": analysis.get("AnalysisType"),
            "convergenceTolerance": analysis.get("ConvergenceTolerance"),
            "numberOfEigenModes": analysis.get("NumberOfEigenModes"),
            "state": "Preserved",
            "scenario": {},
            "scenarioEncodedInHrx": False,
            "timeoutSeconds": None,
            "outputs": {},
        }
        for index, analysis in enumerate(direct_children(root, "Analysis"), start=1)
    ]
