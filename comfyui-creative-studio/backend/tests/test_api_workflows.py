"""Workflow manager API tests."""
from tests.conftest import API_WORKFLOW
from tests.test_workflow_engine import ui_workflow


def test_import_api_workflow(client, workflow):
    assert workflow["source_format"] == "api" and workflow["executable"] is True
    assert workflow["original_json"] == API_WORKFLOW
    keys = {p["key"] for p in workflow["parameters"]}
    assert {"6.text", "7.text", "3.seed", "10.image"} <= keys
    dep = client.get(f"/api/workflows/{workflow['id']}/dependencies").json()
    assert dep["checked"] and dep["ready"] and dep["missing_models"] == []
    assert client.get(f"/api/workflows/{workflow['id']}/download?which=api").json() == API_WORKFLOW


def test_import_ui_workflow_converts_when_comfy_reachable(client):
    w = client.post("/api/workflows", json={"name": "ui", "data": ui_workflow()}).json()
    assert w["source_format"] == "ui" and w["executable"] and w["api_source"] == "converted"
    assert w["original_json"]["nodes"]  # original preserved


def test_import_ui_workflow_offline_then_convert(client, fake):
    fake.up = False
    w = client.post("/api/workflows", json={"name": "ui", "data": ui_workflow()}).json()
    assert w["executable"] is False and "not reachable" in w["conversion_warnings"][0]
    assert client.post(f"/api/workflows/{w['id']}/convert").status_code == 503
    fake.up = True
    w2 = client.post(f"/api/workflows/{w['id']}/convert").json()
    assert w2["executable"] is True and w2["parameters"]
    # attach an explicit API export instead
    w3 = client.post(f"/api/workflows/{w['id']}/api-json", json={"data": API_WORKFLOW}).json()
    assert w3["api_source"] == "imported"
    assert client.post(f"/api/workflows/{w['id']}/api-json", json={"data": ui_workflow()}).status_code == 422


def test_invalid_import_and_parameter_editing(client, workflow):
    assert client.post("/api/workflows", json={"name": "x", "data": {"foo": 1}}).status_code == 422
    assert client.post("/api/workflows", json={"name": "x", "data": API_WORKFLOW, "category": "nope"}).status_code == 422
    params = workflow["parameters"] + [{"node_id": "9", "input": "filename_prefix", "label": "Prefix"}]
    w = client.patch(f"/api/workflows/{workflow['id']}", json={"parameters": params}).json()
    assert any(p["key"] == "9.filename_prefix" for p in w["parameters"])
    bad = client.patch(f"/api/workflows/{workflow['id']}", json={"parameters": [{"node_id": "3", "input": "model"}]})
    assert bad.status_code == 422  # linked input
    assert len(client.get(f"/api/workflows/{workflow['id']}/inputs").json()) > 10
    dup = client.post(f"/api/workflows/{workflow['id']}/duplicate").json()
    assert dup["name"].endswith("(copy)") and dup["executable"]


def test_dependencies_report_missing(client):
    api = {**API_WORKFLOW, "4": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "gone.safetensors"}},
           "11": {"class_type": "IPAdapterAdvanced", "inputs": {}}}
    w = client.post("/api/workflows", json={"name": "x", "data": api}).json()
    dep = client.get(f"/api/workflows/{w['id']}/dependencies").json()
    assert dep["missing_nodes"] == ["IPAdapterAdvanced"] and dep["missing_models"][0]["value"] == "gone.safetensors"
    assert dep["ready"] is False and "ipadapter" in dep["methods"]
