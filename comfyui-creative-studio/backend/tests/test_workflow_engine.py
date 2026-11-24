"""Unit tests for services/workflow.py (format detection, conversion, params, metadata)."""
import copy
import json
from pathlib import Path

import pytest

from app.services import workflow as wf
from tests.conftest import API_WORKFLOW, OBJECT_INFO

EXAMPLES = Path(__file__).resolve().parents[2] / "examples" / "workflows"


def ui_workflow():
    """UI-format graph: checkpoint → (reroute) → sampler, a PrimitiveNode driving steps, a bypassed node."""
    return {
        "nodes": [
            {"id": 4, "type": "CheckpointLoaderSimple", "mode": 0, "inputs": [],
             "outputs": [{"name": "MODEL", "type": "MODEL", "links": [20]}, {"name": "CLIP", "type": "CLIP", "links": [3, 5]},
                         {"name": "VAE", "type": "VAE", "links": [8]}], "widgets_values": ["model_a.safetensors"]},
            {"id": 20, "type": "Reroute", "mode": 0, "inputs": [{"name": "", "type": "*", "link": 20}],
             "outputs": [{"name": "", "type": "MODEL", "links": [1]}]},
            {"id": 6, "type": "CLIPTextEncode", "mode": 0, "title": "Pos", "inputs": [{"name": "clip", "type": "CLIP", "link": 3}],
             "outputs": [{"name": "CONDITIONING", "type": "CONDITIONING", "links": [4]}], "widgets_values": ["gold ring"]},
            {"id": 7, "type": "CLIPTextEncode", "mode": 0, "inputs": [{"name": "clip", "type": "CLIP", "link": 5}],
             "outputs": [{"name": "CONDITIONING", "type": "CONDITIONING", "links": [6]}], "widgets_values": ["blurry"]},
            {"id": 5, "type": "EmptyLatentImage", "mode": 0, "inputs": [],
             "outputs": [{"name": "LATENT", "type": "LATENT", "links": [2]}], "widgets_values": [768, 512, 1]},
            {"id": 3, "type": "KSampler", "mode": 0,
             "inputs": [{"name": "model", "type": "MODEL", "link": 1}, {"name": "positive", "type": "CONDITIONING", "link": 4},
                        {"name": "negative", "type": "CONDITIONING", "link": 6}, {"name": "latent_image", "type": "LATENT", "link": 2},
                        {"name": "steps", "type": "INT", "link": 30, "widget": {"name": "steps"}}],
             "outputs": [{"name": "LATENT", "type": "LATENT", "links": [7]}],
             "widgets_values": [99, "randomize", 20, 6.5, "dpmpp_2m", "karras", 1.0]},
            {"id": 30, "type": "PrimitiveNode", "mode": 0, "outputs": [{"name": "INT", "type": "INT", "links": [30]}],
             "widgets_values": [33, "fixed"]},
            {"id": 8, "type": "VAEDecode", "mode": 0, "inputs": [{"name": "samples", "type": "LATENT", "link": 7},
                                                                   {"name": "vae", "type": "VAE", "link": 8}],
             "outputs": [{"name": "IMAGE", "type": "IMAGE", "links": [9]}]},
            {"id": 9, "type": "SaveImage", "mode": 0, "inputs": [{"name": "images", "type": "IMAGE", "link": 9}],
             "widgets_values": ["out"]},
            {"id": 50, "type": "Note", "mode": 0, "widgets_values": ["hello"]},
            {"id": 51, "type": "SaveImage", "mode": 2, "inputs": [], "widgets_values": ["muted"]},
        ],
        "links": [[1, 20, 0, 3, 0, "MODEL"], [2, 5, 0, 3, 3, "LATENT"], [3, 4, 1, 6, 0, "CLIP"], [4, 6, 0, 3, 1, "CONDITIONING"],
                  [5, 4, 1, 7, 0, "CLIP"], [6, 7, 0, 3, 2, "CONDITIONING"], [7, 3, 0, 8, 0, "LATENT"], [8, 4, 2, 8, 1, "VAE"],
                  [9, 8, 0, 9, 0, "IMAGE"], [20, 4, 0, 20, 0, "MODEL"], [30, 30, 0, 3, 4, "INT"]],
        "version": 0.4,
    }


def test_detect_format():
    assert wf.detect_format(API_WORKFLOW) == "api"
    assert wf.detect_format({"prompt": API_WORKFLOW}) == "api"
    assert wf.detect_format(ui_workflow()) == "ui"
    for bad in ({}, [], {"a": 1}):
        with pytest.raises(wf.WorkflowFormatError):
            wf.detect_format(bad)


def test_convert_ui_to_api():
    api, warnings = wf.convert_ui_to_api(ui_workflow(), OBJECT_INFO)
    assert set(api) == {"4", "6", "7", "5", "3", "8", "9"}  # no Reroute/Primitive/Note/muted
    ks = api["3"]["inputs"]
    assert ks["model"] == ["4", 0]  # resolved through Reroute
    assert ks["seed"] == 99 and ks["cfg"] == 6.5 and ks["sampler_name"] == "dpmpp_2m"  # "randomize" skipped
    assert ks["steps"] == 33  # value from PrimitiveNode
    assert api["5"]["inputs"] == {"width": 768, "height": 512, "batch_size": 1}
    assert api["6"]["_meta"]["title"] == "Pos"
    assert warnings == []


def test_convert_bypass_and_missing_nodes():
    ui = ui_workflow()
    ui["nodes"].append({"id": 60, "type": "SomeCustomNode", "mode": 0, "inputs": [], "widgets_values": []})
    api, warnings = wf.convert_ui_to_api(ui, OBJECT_INFO)
    assert any("SomeCustomNode" in w for w in warnings)
    with pytest.raises(wf.WorkflowFormatError, match="subgraphs"):
        wf.convert_ui_to_api({**ui, "definitions": {"subgraphs": [{"id": "x"}]}}, OBJECT_INFO)


def test_discover_parameters_and_roles():
    params = {p["key"]: p for p in wf.discover_parameters(API_WORKFLOW, OBJECT_INFO)}
    assert params["6.text"]["label"] == "Positive prompt" and params["6.text"]["role"] == "positive"
    assert params["7.text"]["role"] == "negative"
    assert params["3.seed"]["type"] == "seed" and params["3.cfg"]["max"] == 100.0
    assert params["3.sampler_name"]["choices"] == ["euler", "dpmpp_2m"]
    assert params["10.image"]["type"] == "image"
    assert params["4.ckpt_name"]["type"] == "choice"


def test_build_prompt():
    params = wf.discover_parameters(API_WORKFLOW)
    out = wf.build_prompt(API_WORKFLOW, params, {"3.steps": "12", "6.text": "x", "3.cfg": ""},
                          {"10.image": "creative_studio/ref.png"})
    assert out["3"]["inputs"]["steps"] == 12 and out["3"]["inputs"]["cfg"] == 7.0
    assert out["10"]["inputs"]["image"] == "creative_studio/ref.png"
    assert API_WORKFLOW["3"]["inputs"]["steps"] == 20  # original untouched
    with pytest.raises(wf.PromptBuildError, match="does not match"):
        wf.build_prompt(API_WORKFLOW, params, {"99.x": 1})
    with pytest.raises(wf.PromptBuildError, match="connected"):
        wf.build_prompt(API_WORKFLOW, params, {"3.model": "x"})
    with pytest.raises(wf.PromptBuildError, match="convert"):
        wf.build_prompt(API_WORKFLOW, params, {"3.steps": "many"})


def test_dependencies_and_structure():
    api = copy.deepcopy(API_WORKFLOW)
    api["4"]["inputs"]["ckpt_name"] = "missing.safetensors"
    api["3"]["inputs"]["sampler_name"] = "nope"
    api["11"] = {"class_type": "MysteryNode", "inputs": {}}
    dep = wf.check_dependencies(api, wf.api_node_types(api), OBJECT_INFO)
    assert dep["missing_nodes"] == ["MysteryNode"]
    assert [m["value"] for m in dep["missing_models"]] == ["missing.safetensors"]
    assert [i["value"] for i in dep["invalid_values"]] == ["nope"]  # LoadImage 'image' is not flagged
    assert wf.check_dependencies(api, [], None)["checked"] is False
    api["8"]["inputs"]["vae"] = ["4", 1]  # CLIP into VAE
    api["8"]["inputs"]["bogus"] = 1
    del api["3"]["inputs"]["steps"]
    kinds = {(i["kind"], i["severity"]) for i in wf.validate_structure(api, OBJECT_INFO)}
    assert {("type_mismatch", "error"), ("unknown_input", "warning"), ("missing_input", "error"),
            ("unknown_node", "error")} <= kinds


def test_generation_metadata():
    md = wf.extract_generation_metadata(API_WORKFLOW)
    assert (md["prompt"], md["negative_prompt"], md["seed"], md["steps"], md["sampler"]) == \
        ("a gold ring", "blurry", 42, 20, "euler")
    assert md["dimensions"]["width"] == 512
    assert md["models"][0]["name"] == "model_a.safetensors" and md["models"][0]["kind"] == "checkpoint"


def test_example_workflows_are_api_format_and_roles_trace_through_inpaint():
    for f in EXAMPLES.glob("*.json"):
        assert wf.detect_format(json.loads(f.read_text())) == "api", f.name
    api = json.loads((EXAMPLES / "jewelry_product_preserve_sd15_api.json").read_text())
    assert wf.prompt_roles(api) == {"9": "positive", "10": "negative"}
    assert set(wf.detect_methods(wf.api_node_types(api))) == {"inpaint"}
