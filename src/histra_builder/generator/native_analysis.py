"""Native C# load and analysis definitions.

The C# application seeds a new model with a fixed set of load conditions,
load combinations, load functions and analyses.  The values in this module are
transcribed from the supplied native bridge model
``histra-python/histra/model-live/model.hrx``; they are kept as data so the
generator does not depend on a native file at run time.

The pipeline only executes ``Vert``, ``scour_1`` and ``scour_2``.  The modal,
live-load and additional scour analyses are emitted as well so an exported model
matches the native analysis tree instead of silently dropping settings a C#
user would see.
"""
from __future__ import annotations

from typing import Any, Dict, Iterable, List, Sequence, Tuple

from lxml import etree

from .native_defaults import ANALYSIS_DEFAULTS

# Native insertion order: Vert, Modal_0, LiveLoad_1, scour_1 ... LiveLoad_4.
ANALYSIS_ORDER: Tuple[str, ...] = (
    "Vert",
    "Modal_0",
    "LiveLoad_1",
    "scour_1",
    "scour_2",
    "LiveLoad_2",
    "scour_3",
    "LiveLoad_3",
    "scour_4",
    "LiveLoad_0",
    "Modal_-1",
    "Modal_1",
    "LiveLoad_4",
)

# Differences from ``ANALYSIS_DEFAULTS`` only.  ``MasterPoint`` and the modal
# reference are resolved from the generated model at write time.
ANALYSIS_OVERRIDES: Dict[str, Dict[str, str]] = {
    "Vert": {
        "Key": "1",
        "Name": "Vert",
        "Description": "Base Analysis adopted for all analyzes derived from the seismic combination",
        "InitialAnalysisKey": "-100",
        "LoadCombinationKey": "6",
        "LoadFunctionKey": "1",
    },
    "Modal_0": {
        "Key": "21",
        "Name": "Modal_0",
        "AnalysisType": "5",
        "Description": "Modal analysis",
        "DirectionZenit": "0",
        "DirX": "1",
        "DirZ": "0",
        "DirZDisp": "0",
        "InitialAnalysisKey": "1",
        "IsSeismic": "true",
        "LoadCombinationKey": "6",
        "LoadFunctionKey": "13",
        "ConvergenceTolerance": "0.04",
        "MaxIterations": "10",
        "TypeLoadDistribution": "Force",
        "Method": "StandardNewtonRaphson",
        "NumberOfLanczosEigenVectors": "3",
        "NumberOfEigenModes": "10",
    },
    "LiveLoad_1": {
        "Key": "22",
        "Name": "LiveLoad_1",
        "Description": "NewAnalysis",
        "InitialAnalysisKey": "1",
        "LoadCombinationKey": "15",
        "LoadFunctionKey": "22",
        "ConvergenceTolerance": "0.000500000023748726",
        "MaxIterations": "10000",
        "ForceControl": "false",
        "TargetDisplacement": "0.0500000007450581",
        "Method": "StandardInitialInterpolatedLineSearch",
        "Dr2": "1",
        "DesiredIterations": "200",
        "CheckSecantStiffness": "false",
        "MaxArcLengthRay": "25",
        "ArcLengthProcedure": "OnlyModelPointsSelected",
        "IntegrationMethod": "ArcLength",
        "maxU": "1",
    },
    "scour_1": {
        "Key": "23",
        "Name": "scour_1",
        "Description": "Vert_Copy23",
        "InitialAnalysisKey": "1",
        "LoadCombinationKey": "6",
        "LoadFunctionKey": "23",
        "Mult": "0",
    },
    "scour_2": {
        "Key": "24",
        "Name": "scour_2",
        "Description": "scour_1_Copy24",
        "InitialAnalysisKey": "23",
        "LoadCombinationKey": "6",
        "LoadFunctionKey": "24",
        "Mult": "0",
    },
    "LiveLoad_2": {
        "Key": "25",
        "Name": "LiveLoad_2",
        "Description": "LiveLoad_1_Copy25",
        "InitialAnalysisKey": "24",
        "LoadCombinationKey": "15",
        "LoadFunctionKey": "25",
        "ConvergenceTolerance": "0.000500000023748726",
        "MaxIterations": "10000",
        "ForceControl": "false",
        "TargetDisplacement": "2",
        "Method": "StandardInitialInterpolatedLineSearch",
        "Dr2": "1",
        "DesiredIterations": "200",
        "CheckSecantStiffness": "false",
        "MaxArcLengthRay": "25",
        "ArcLengthProcedure": "OnlyModelPointsSelected",
        "IntegrationMethod": "ArcLength",
        "maxU": "10",
    },
    "scour_3": {
        "Key": "26",
        "Name": "scour_3",
        "Description": "scour_2_Copy26",
        "InitialAnalysisKey": "24",
        "LoadCombinationKey": "6",
        "LoadFunctionKey": "26",
        "Mult": "0",
    },
    "LiveLoad_3": {
        "Key": "27",
        "Name": "LiveLoad_3",
        "Description": "LiveLoad_2_Copy27",
        "InitialAnalysisKey": "26",
        "LoadCombinationKey": "15",
        "LoadFunctionKey": "27",
        "ConvergenceTolerance": "0.000500000023748726",
        "MaxIterations": "10000",
        "ForceControl": "false",
        "TargetDisplacement": "2",
        "Method": "StandardInitialInterpolatedLineSearch",
        "Dr2": "1",
        "DesiredIterations": "200",
        "CheckSecantStiffness": "false",
        "MaxArcLengthRay": "25",
        "ArcLengthProcedure": "OnlyModelPointsSelected",
        "IntegrationMethod": "ArcLength",
        "maxU": "10",
    },
    "scour_4": {
        "Key": "28",
        "Name": "scour_4",
        "Description": "scour_3_Copy28",
        "InitialAnalysisKey": "24",
        "LoadCombinationKey": "6",
        "LoadFunctionKey": "28",
        "Mult": "0",
    },
    "LiveLoad_0": {
        "Key": "29",
        "Name": "LiveLoad_0",
        "Description": "LiveLoad_1_Copy29",
        "InitialAnalysisKey": "1",
        "LoadCombinationKey": "15",
        "LoadFunctionKey": "29",
        "ConvergenceTolerance": "0.000500000023748726",
        "MaxIterations": "10000",
        "ForceControl": "false",
        "TargetDisplacement": "2",
        "Method": "StandardInitialInterpolatedLineSearch",
        "Dr2": "1",
        "DesiredIterations": "200",
        "CheckSecantStiffness": "false",
        "MaxArcLengthRay": "25",
        "ArcLengthProcedure": "OnlyModelPointsSelected",
        "IntegrationMethod": "ArcLength",
        "maxU": "10",
    },
    "Modal_-1": {
        "Key": "30",
        "Name": "Modal_-1",
        "AnalysisType": "5",
        "Description": "Modal_0_Copy30",
        "DirectionZenit": "0",
        "DirX": "1",
        "DirZ": "0",
        "DirZDisp": "0",
        "InitialAnalysisKey": "-100",
        "IsSeismic": "true",
        "LoadCombinationKey": "6",
        "LoadFunctionKey": "30",
        "ConvergenceTolerance": "0.04",
        "MaxIterations": "10",
        "TypeLoadDistribution": "Force",
        "Method": "StandardNewtonRaphson",
        "NumberOfLanczosEigenVectors": "3",
        "NumberOfEigenModes": "10",
    },
    "Modal_1": {
        "Key": "31",
        "Name": "Modal_1",
        "AnalysisType": "5",
        "Description": "Modal_0_Copy31",
        "DirectionZenit": "0",
        "DirX": "1",
        "DirZ": "0",
        "DirZDisp": "0",
        "InitialAnalysisKey": "23",
        "IsSeismic": "true",
        "LoadCombinationKey": "6",
        "LoadFunctionKey": "31",
        "ConvergenceTolerance": "0.04",
        "MaxIterations": "10",
        "TypeLoadDistribution": "Force",
        "Method": "StandardNewtonRaphson",
        "NumberOfLanczosEigenVectors": "3",
        "NumberOfEigenModes": "10",
    },
    "LiveLoad_4": {
        "Key": "32",
        "Name": "LiveLoad_4",
        "Description": "LiveLoad_3_Copy32",
        "InitialAnalysisKey": "28",
        "LoadCombinationKey": "15",
        "LoadFunctionKey": "32",
        "ConvergenceTolerance": "0.000500000023748726",
        "MaxIterations": "10000",
        "ForceControl": "false",
        "TargetDisplacement": "2",
        "Method": "StandardInitialInterpolatedLineSearch",
        "Dr2": "1",
        "DesiredIterations": "200",
        "CheckSecantStiffness": "false",
        "MaxArcLengthRay": "25",
        "ArcLengthProcedure": "OnlyModelPointsSelected",
        "IntegrationMethod": "ArcLength",
        "maxU": "10",
    },
}

# Analyses that must exist for every generated model.  Scour stages are added
# on top of this set by ``include_scour_analyses``.
BASE_ANALYSES: Tuple[str, ...] = ("Vert", "Modal_0", "LiveLoad_0", "Modal_-1")
SCOUR_ANALYSES: Tuple[str, ...] = (
    "LiveLoad_1",
    "scour_1",
    "scour_2",
    "LiveLoad_2",
    "scour_3",
    "LiveLoad_3",
    "scour_4",
    "Modal_1",
    "LiveLoad_4",
)
# The three stages executed by histra-job-runner.  They keep the strict
# ForceMoment equilibrium criterion required by the pipeline.
STRICT_EQUILIBRIUM_ANALYSES = frozenset({"Vert", "scour_1", "scour_2"})

# Native ``LoadCondition`` rows.
LOAD_CONDITIONS: Tuple[Dict[str, str], ...] = (
    {"Id": "1", "Name": "Gravity", "Description": "Self weight - G1", "MassInDirX": "1", "MassInDirY": "1", "MassInDirZ": "1", "isMainLoad": "false", "isFavourable": "false", "isUnFavourable": "true", "GammaFavEQU": "1", "GammaUnfavEQU": "1", "GammaFavSTR": "1", "GammaUnfavSTR": "1", "GammaFavGEO": "1", "GammaUnfavGEO": "1", "Action": "1"},
    {"Id": "2", "Name": "Structural Dead", "Description": "Structural dead load - G1", "MassInDirX": "1", "MassInDirY": "1", "MassInDirZ": "1", "isMainLoad": "false", "isFavourable": "false", "isUnFavourable": "true", "GammaFavEQU": "1", "GammaUnfavEQU": "1", "GammaFavSTR": "1", "GammaUnfavSTR": "1", "GammaFavGEO": "1", "GammaUnfavGEO": "1", "Action": "1"},
    {"Id": "3", "Name": "Not Structural dead", "Description": "Not structural dead loads - G2", "MassInDirX": "1", "MassInDirY": "1", "MassInDirZ": "1", "isMainLoad": "false", "isFavourable": "false", "isUnFavourable": "true", "GammaFavEQU": "0", "GammaUnfavEQU": "1.5", "GammaFavSTR": "0", "GammaUnfavSTR": "1.5", "GammaFavGEO": "0", "GammaUnfavGEO": "1.3", "Action": "2"},
    {"Id": "4", "Name": "Not Structural dead CD", "Description": "Not structural dead loads CD - G2", "MassInDirX": "1", "MassInDirY": "1", "MassInDirZ": "1", "isMainLoad": "false", "isFavourable": "false", "isUnFavourable": "true", "GammaFavEQU": "0", "GammaUnfavEQU": "1.5", "GammaFavSTR": "0", "GammaUnfavSTR": "1.5", "GammaFavGEO": "0", "GammaUnfavGEO": "1.3", "Action": "2"},
    {"Id": "5", "Name": "Variable", "Description": "Variable loads - Qk", "MassInDirX": "1", "MassInDirY": "1", "MassInDirZ": "1", "isMainLoad": "false", "isFavourable": "false", "isUnFavourable": "true", "GammaFavEQU": "0", "GammaUnfavEQU": "1", "GammaFavSTR": "0", "GammaUnfavSTR": "1", "GammaFavGEO": "0", "GammaUnfavGEO": "1", "Action": "3"},
    {"Id": "6", "Name": "Vehicle", "Description": "Vehicle loads - Qk", "MassInDirX": "0.2", "MassInDirY": "0.2", "MassInDirZ": "0.2", "isMainLoad": "true", "isFavourable": "false", "isUnFavourable": "true", "GammaFavEQU": "0", "GammaUnfavEQU": "1.45", "GammaFavSTR": "0", "GammaUnfavSTR": "1.45", "GammaFavGEO": "0", "GammaUnfavGEO": "1.25", "Action": "9"},
    {"Id": "7", "Name": "Lateral Earth Pressure", "Description": "Lateral Earth Pressure - G2", "MassInDirX": "1", "MassInDirY": "1", "MassInDirZ": "1", "isMainLoad": "false", "isFavourable": "false", "isUnFavourable": "true", "GammaFavEQU": "0", "GammaUnfavEQU": "1.5", "GammaFavSTR": "0", "GammaUnfavSTR": "1.5", "GammaFavGEO": "0", "GammaUnfavGEO": "1.3", "Action": "7"},
    {"Id": "8", "Name": "Ballast", "Description": "Ballast - G2", "MassInDirX": "1", "MassInDirY": "1", "MassInDirZ": "1", "isMainLoad": "false", "isFavourable": "false", "isUnFavourable": "true", "GammaFavEQU": "1", "GammaUnfavEQU": "1", "GammaFavSTR": "1", "GammaUnfavSTR": "1", "GammaFavGEO": "1", "GammaUnfavGEO": "1", "Action": "8"},
    {"Id": "9", "Name": "Swaying action", "Description": "Swaying action - Qk", "MassInDirX": "1", "MassInDirY": "1", "MassInDirZ": "1", "isMainLoad": "false", "isFavourable": "false", "isUnFavourable": "true", "GammaFavEQU": "0", "GammaUnfavEQU": "1.45", "GammaFavSTR": "0", "GammaUnfavSTR": "1.45", "GammaFavGEO": "0", "GammaUnfavGEO": "1.25", "Action": "10"},
    {"Id": "10", "Name": "Breaking action", "Description": "Breaking & starting action - Qk", "MassInDirX": "1", "MassInDirY": "1", "MassInDirZ": "1", "isMainLoad": "false", "isFavourable": "false", "isUnFavourable": "true", "GammaFavEQU": "0", "GammaUnfavEQU": "1.45", "GammaFavSTR": "0", "GammaUnfavSTR": "1.45", "GammaFavGEO": "0", "GammaUnfavGEO": "1.25", "Action": "11"},
    {"Id": "11", "Name": "User_condition", "Description": "User_condition", "MassInDirX": "1", "MassInDirY": "1", "MassInDirZ": "1", "isMainLoad": "true", "isFavourable": "false", "isUnFavourable": "true", "GammaFavEQU": "0", "GammaUnfavEQU": "1", "GammaFavSTR": "0", "GammaUnfavSTR": "1", "GammaFavGEO": "0", "GammaUnfavGEO": "1", "Action": "3"},
)

_NUMBER = ("Number", "0")
_NUMBER_ONE = ("Number", "1")
_GSTR = ("GammaUnfavSTR", "-1")
_GSTR_PSI0 = ("GammaUnfavSTR_Psi0", "-1")
_GGEO = ("GammaUnfavGEO", "-1")
_GGEO_PSI0 = ("GammaUnfavGEO_Psi0", "-1")
_PSI0 = ("Psi0", "-1")
_PSI1 = ("Psi1", "-1")
_PSI2 = ("Psi2", "-1")

# Each row lists the 11 combination columns in order.
_STR_ROW_1 = (_NUMBER, _NUMBER, _NUMBER, _NUMBER, _NUMBER, _GSTR, _NUMBER, _GSTR, _GSTR_PSI0, _GSTR_PSI0, _NUMBER)
_STR_ROW_2 = (_NUMBER, _NUMBER, _NUMBER, _NUMBER, _NUMBER, _GSTR_PSI0, _NUMBER, _GSTR, _GSTR_PSI0, _GSTR_PSI0, _NUMBER)
_GEO_ROW_1 = (_NUMBER, _NUMBER, _NUMBER, _NUMBER, _NUMBER, _GGEO, _NUMBER, _GGEO, _GGEO_PSI0, _GGEO_PSI0, _NUMBER)
_GEO_ROW_2 = (_NUMBER, _NUMBER, _NUMBER, _NUMBER, _NUMBER, _GGEO_PSI0, _NUMBER, _GGEO, _GGEO_PSI0, _GGEO_PSI0, _NUMBER)
_RARE_ROW = (_NUMBER, _NUMBER, _NUMBER, _NUMBER, _NUMBER, _PSI0, _NUMBER, _NUMBER_ONE, _PSI0, _PSI0, _NUMBER)
_FREQUENT_ROW_1 = (_NUMBER, _NUMBER, _NUMBER, _NUMBER, _NUMBER, _PSI1, _NUMBER, _NUMBER_ONE, _PSI2, _PSI2, _NUMBER)
_FREQUENT_ROW_2 = (_NUMBER, _NUMBER, _NUMBER, _NUMBER, _NUMBER, _PSI2, _NUMBER, _NUMBER_ONE, _PSI2, _PSI2, _NUMBER)
_SEISMIC_ROW = (_NUMBER_ONE, _NUMBER_ONE, _NUMBER_ONE, _NUMBER_ONE, _PSI2, _PSI2, _NUMBER_ONE, _NUMBER_ONE, _PSI2, _PSI2, _PSI2)
_STR_BASE_ROW = (_GSTR, _GSTR, _GSTR, _GSTR, _GSTR_PSI0, _NUMBER, _GSTR, _NUMBER, _NUMBER, _NUMBER, _GSTR_PSI0)
_GEO_BASE_ROW = (_GGEO, _GGEO, _GGEO, _GGEO, _GGEO_PSI0, _NUMBER, _GGEO, _NUMBER, _NUMBER, _NUMBER, _GGEO_PSI0)
_RARE_BASE_ROW = (_NUMBER_ONE, _NUMBER_ONE, _NUMBER_ONE, _NUMBER_ONE, _PSI0, _NUMBER, _NUMBER_ONE, _NUMBER, _NUMBER, _NUMBER, _PSI0)
_FREQUENT_BASE_ROW = (_NUMBER_ONE, _NUMBER_ONE, _NUMBER_ONE, _NUMBER_ONE, _PSI2, _NUMBER, _NUMBER_ONE, _NUMBER, _NUMBER, _NUMBER, _PSI2)
_USER_ROW = (_NUMBER, _NUMBER, _NUMBER, _NUMBER, _NUMBER, _NUMBER, _NUMBER, _NUMBER, _NUMBER, _NUMBER, _NUMBER_ONE)

# (key, name, limit state, rows)
LOAD_COMBINATIONS: Tuple[Tuple[str, str, str, Sequence[Sequence[Tuple[str, str]]]], ...] = (
    ("1", "SLU.STR", "SLU_STR", (_STR_ROW_1, _STR_ROW_2)),
    ("2", "SLU.GEO", "SLU_GEO", (_GEO_ROW_1, _GEO_ROW_2)),
    ("3", "SLE.Rare", "SLE_rara", (_RARE_ROW, _RARE_ROW)),
    ("4", "SLE.Frequent", "SLE_frequente", (_FREQUENT_ROW_1, _FREQUENT_ROW_2)),
    ("5", "SLE.Quasi-Static", "SLE_quasi_permanente", (_FREQUENT_ROW_2,)),
    ("6", "SEISMIC", "Seismic", (_SEISMIC_ROW,)),
    ("7", "SLU.STR.BASE", "SLU_STR_BASE", (_STR_BASE_ROW,)),
    ("8", "SLU.GEO.BASE", "SLU_GEO_BASE", (_GEO_BASE_ROW,)),
    ("9", "SLE.Rare.BASE", "SLU_STR", (_RARE_BASE_ROW,)),
    ("10", "SLE.Frequent.BASE", "SLU_STR", (_FREQUENT_BASE_ROW,)),
    ("11", "SLE.Quasi-Static.Base", "SLU_STR", (_FREQUENT_BASE_ROW,)),
    ("15", "User_combination", "Custom", (_USER_ROW,)),
)

# Native load functions 1..32: discretisation value and whether the second
# point ramps to 1.  Scour functions also ramp to 1; the scour analysis sets
# ``Mult=0`` so no gravity increment is applied.
_LOAD_FUNCTION_DISCRETISATION: Tuple[str, ...] = (
    "0.2", "0.2", "0.2", "0.2", "0.2", "0.2", "0.2", "0.2",
    "0.01", "0.01", "0.05", "0.05", "0.1", "0.2", "0.2", "0.2",
    "0.2", "0.01", "0.01", "0.05", "0.05", "0.2", "0.2", "0.2",
    "0.2", "0.2", "0.2", "0.2", "0.2", "0.1", "0.1", "0.2",
)


def _analysis_names(include_scour_analyses: bool) -> List[str]:
    names = set(BASE_ANALYSES)
    if include_scour_analyses:
        names.update(SCOUR_ANALYSES)
    return [name for name in ANALYSIS_ORDER if name in names]


def analysis_specs(
    include_scour_analyses: bool = True,
    *,
    model_point_keys: Iterable[int] = (),
) -> List[Dict[str, Any]]:
    """Return the native analysis attributes for the generated model."""
    points = [str(key) for key in model_point_keys]
    master = points[0] if points else "1"
    specs: List[Dict[str, Any]] = []
    names = _analysis_names(include_scour_analyses)
    modal_key = next(
        (ANALYSIS_OVERRIDES[name]["Key"] for name in names if name.startswith("Modal")),
        "0",
    )
    for name in names:
        attributes = dict(ANALYSIS_DEFAULTS)
        attributes.update(ANALYSIS_OVERRIDES[name])
        attributes["MasterPoint"] = master
        attributes["PushModal_ModalAnalysisKey"] = modal_key
        if name in STRICT_EQUILIBRIUM_ANALYSES:
            attributes["AdapticConvergenceCriteria"] = "ForceMoment"
        specs.append({"name": name, "attributes": attributes})
    return specs


def write_load_conditions(root: etree._Element) -> None:
    for attributes in LOAD_CONDITIONS:
        etree.SubElement(root, "LoadCondition", attrib=dict(attributes))


def write_load_combinations(root: etree._Element) -> None:
    for key, name, limit_state, rows in LOAD_COMBINATIONS:
        combination = etree.SubElement(
            root,
            "LoadCombination",
            attrib={"Key": key, "Name": name, "LimitState": limit_state},
        )
        for row_index, row in enumerate(rows, start=1):
            for column_index, (type_data, value) in enumerate(row, start=1):
                etree.SubElement(
                    combination,
                    "Item",
                    attrib={
                        "LoadCombinationKey": key,
                        "ColumnKey": str(column_index),
                        "RowKey": str(row_index),
                        "Name": str(row_index),
                        "Schema": "NoSchema",
                        "Position": "0",
                        "Combination": str(row_index),
                        "TypeData": type_data,
                        "SecondaryTypeData": "Number",
                        "Val": value,
                    },
                )


def write_load_functions(root: etree._Element) -> None:
    for index, discretisation in enumerate(_LOAD_FUNCTION_DISCRETISATION, start=1):
        etree.SubElement(
            root,
            "LoadFunction",
            attrib={"key": str(index), "typeDiscr": "false", "DiscrVal": discretisation},
        )
        etree.SubElement(
            root,
            "LoadFunctionItem",
            attrib={
                "key": str(2 * index - 1),
                "loadFunctionKey": str(index),
                "pseudoTime": "0",
                "multiplier": "0",
            },
        )
        etree.SubElement(
            root,
            "LoadFunctionItem",
            attrib={
                "key": str(2 * index),
                "loadFunctionKey": str(index),
                "pseudoTime": "1",
                "multiplier": "1",
            },
        )


def build_analysis(
    spec: Dict[str, Any], *, model_point_keys: Iterable[int] = ()
) -> etree._Element:
    """Build one analysis element with its native child containers."""
    points = [str(key) for key in model_point_keys]
    analysis = etree.Element("Analysis", attrib=dict(spec["attributes"]))
    key = analysis.get("Key", "0")

    states = etree.SubElement(analysis, "States")
    etree.SubElement(
        states,
        "State",
        Id="1",
        Key=key,
        Combination="1",
        Step="0",
        State="NotExecutedNotToBeExecuted",
        Fo="0",
        Exit="NotExecuted",
        ExitDescription="",
    )
    active = etree.SubElement(analysis, "ActiveModelPoints")
    for point in points:
        etree.SubElement(active, "ActiveModelPoint", Key=point, Value="true")
    displacement = etree.SubElement(analysis, "DisplModelPoints")
    for point in points:
        etree.SubElement(displacement, "DisplModelPoint", Key=point, Value="0")
    etree.SubElement(analysis, "DynamicLoads")
    etree.SubElement(analysis, "StageDefinitions")
    etree.SubElement(analysis, "StageItems")
    phases = etree.SubElement(analysis, "AdapticPhases")
    if spec["name"].startswith("LiveLoad") and points:
        etree.SubElement(
            phases,
            "AdapticPhase",
            Id="0",
            Key="0",
            ParentKey=key,
            Phase="Force",
            PhaseName="Force",
            ModelPointKey=points[0],
            ModelPointName="-",
            Direction="z",
            DirectionName="-",
            Increment="0.1",
            Path="Keep",
            PathName="Keep",
            Steps="10",
        )
    etree.SubElement(analysis, "PushModalSettings")
    return analysis


def write_analyses(
    root: etree._Element,
    *,
    model_point_keys: Iterable[int] = (),
    include_scour_analyses: bool = True,
) -> None:
    points = [str(key) for key in model_point_keys]
    for spec in analysis_specs(
        include_scour_analyses, model_point_keys=points
    ):
        root.append(build_analysis(spec, model_point_keys=points))
