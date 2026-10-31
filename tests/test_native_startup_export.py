from lxml import etree
import pytest
from histra_builder.generator import BridgeSpec,SpanSpec,Point3D,generate_bridge_hrx,compute_quad_kinematics,build_bridge_mesh
from histra_builder.generator.hrx_writer import serialize_mesh_to_hrx


def test_generated_model_has_native_startup_metadata():
    root=etree.fromstring(generate_bridge_hrx(BridgeSpec(spans=[SpanSpec(length=400.)]),include_scour_analyses=False))
    assert root.get('IsLocked')=='false' and root.get('GDL')=='0'
    assert not root.findall('Interface')
    assert root.find("Layer[@Name='Node']") is not None
    options=root.find('AdvancedOptionsDefault')
    assert float(options.get('ToleranceNode'))>0 and float(options.get('TolerancePlane'))>0
    for nc in root.findall('NodeC'):
        assert nc.find('MasterElements/MasterElement').get('Key')==nc.get('NodeKey')
        assert nc.find('MasterElements/MasterElement').get('Value')=='Node'
        assert nc.findall('SlaveElements/SlaveElement')
    for r in root.findall('Restraint'):
        assert r.get('MaterialKey')=='0'
        assert r.get('ParentTypeElement')=='None' and r.get('ParentKey')=='0'
        assert r.get('Type')=='Line' and float(r.get('H'))>0
        assert r.find('ReferenceSystem') is not None
        assert all(r.get(x+'mechBehaviourType')=='Fixed' for x in ['U1','U2','U3','R1','R2','R3'])
    for a in root.findall('Analysis'):
        assert a.get('Mult')=='1' and a.get('ForceImposed')=='true'
        assert int(a.get('ConvergenceToleranceForce'))>0
        assert int(a.get('ConvergenceToleranceMoment'))>0
        assert a.get('AdapticConvergenceCriteria')=='ForceMoment'
        assert a.find('States/State').get('State')=='NotExecutedNotToBeExecuted'
        assert len(a.findall('DisplModelPoints/DisplModelPoint'))==len(root.findall('ModelPoint'))


def test_distorted_quad_centroid_and_extrusion_winding():
    k=compute_quad_kinematics([Point3D(0,0,0),Point3D(10,0,0),Point3D(6,0,10),Point3D(0,0,10)],thickness=2)
    assert k.centroid.x==pytest.approx(49/12)
    assert k.centroid.z==pytest.approx(55/12)
    assert all(n.y==-1 for n in k.normals)


def test_point_xml_retains_authored_precision():
    p=Point3D(1.123456789012345,0.000000123456789,2.)
    assert [float(v) for v in p.to_xml_str().split(';')]==[p.x,p.y,p.z]


def test_masonry_soil_support_assignment_is_rejected():
    mesh=build_bridge_mesh(BridgeSpec(spans=[SpanSpec(length=400.)]))
    mesh.restraints[0].material_key=146
    with pytest.raises(ValueError,match='MasonryMaterial cannot define a foundation restraint law'):
        serialize_mesh_to_hrx(mesh)
