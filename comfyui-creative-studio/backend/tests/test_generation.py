"""Generation, tracking and production-board tests against the fake ComfyUI."""
import io
import json
import zipfile


def _gen(client, workflow, **kw):
    r = client.post("/api/generate", json={"workflow_id": workflow["id"], **kw})
    assert r.status_code == 201, r.text
    return r.json()


def test_full_success_flow_with_variations_and_metadata(client, workflow, ref, project):
    fake = client.fake
    out = _gen(client, workflow, variations=3, seed_mode="increment", base_seed=100,
               values={"6.text": "a ring on marble"}, image_bindings={"10.image": ref["id"]})
    jobs = out["jobs"]
    assert [j["status"] for j in jobs] == ["submitted"] * 3
    assert [j["parameter_values"]["3.seed"] for j in jobs] == [100, 101, 102]
    assert len(fake.uploads) == 1 and fake.uploads[0]["subfolder"] == "creative_studio"  # cached per batch
    sent = list(fake.prompts.values())[0]
    assert sent["prompt"]["10"]["inputs"]["image"].startswith("creative_studio/ref-")
    assert sent["prompt"]["6"]["inputs"]["text"] == "a ring on marble"
    assert sent["extra"]["creative_studio"]["job_id"] == jobs[0]["id"]

    client.poll()  # running: never reported completed before history says so
    assert {j["status"] for j in client.get("/api/jobs").json()} == {"running"}
    assert client.get("/api/outputs").json() == []

    fake.finish_all()
    client.poll()
    done = client.get("/api/jobs").json()
    assert {j["status"] for j in done} == {"completed"}
    outs = client.get(f"/api/outputs?project_id={project['id']}").json()
    assert len(outs) == 3  # temp previews are ignored
    meta = outs[-1]["meta"]
    assert meta["generation"]["prompt"] == "a ring on marble" and meta["generation"]["seed"] == 100
    assert meta["generation"]["steps"] == 20 and meta["generation"]["sampler"] == "euler"
    assert meta["reference_images"][0]["sha256"] == ref["sha256"]
    assert meta["generation"]["models"][0]["sha256"] == "0xabc"  # from /view_metadata
    assert meta["comfy"]["execution_seconds"] == 2.5
    full = client.get(f"/api/jobs/{jobs[0]['id']}").json()
    assert full["submitted_prompt"]["3"]["inputs"]["seed"] == 100
    dash = client.get("/api/dashboard").json()
    assert dash["stats"]["outputs"] == 3 and dash["active_jobs"] == []


def test_failed_and_interrupted_and_rejected(client, workflow):
    fake = client.fake
    fake.scenario = "error"
    j1 = _gen(client, workflow)["jobs"][0]
    fake.scenario = "interrupt"
    j2 = _gen(client, workflow)["jobs"][0]
    fake.finish_all()
    client.poll()
    a, b = client.get(f"/api/jobs/{j1['id']}").json(), client.get(f"/api/jobs/{j2['id']}").json()
    assert a["status"] == "failed" and a["error"]["message"] == "out of memory" and a["error"]["node_id"] == "3"
    assert b["status"] == "interrupted" and a["outputs"] == []
    fake.reject_next = {"error": {"type": "prompt_outputs_failed_validation", "message": "Prompt outputs failed"},
                        "node_errors": {"4": {"errors": [{"message": "Value not in list"}]}}}
    j3 = _gen(client, workflow)["jobs"][0]
    assert j3["status"] == "failed" and "4" in j3["error"]["node_errors"]


def test_unreachable_comfy_never_changes_state_and_lost_detection(client, workflow):
    fake = client.fake
    j = _gen(client, workflow)["jobs"][0]
    fake.up = False
    client.poll()
    job = client.get(f"/api/jobs/{j['id']}").json()
    assert job["status"] == "submitted" and job["progress"]["connection"] == "unreachable"
    assert client.post("/api/generate", json={"workflow_id": workflow["id"]}).status_code == 503
    fake.up = True
    fake.scenario = "lost"
    j2 = _gen(client, workflow)["jobs"][0]
    client.poll()  # first absence starts the grace timer
    client.poll()
    assert client.get(f"/api/jobs/{j2['id']}").json()["status"] == "lost"


def test_cancel_pending_and_interrupt_running(client, workflow):
    fake = client.fake
    fake.scenario = "pending"
    j = _gen(client, workflow)["jobs"][0]
    r = client.post(f"/api/jobs/{j['id']}/cancel").json()
    assert r["status"] == "cancelled" and fake.deleted == [j["comfy_prompt_id"]]
    fake.scenario = "interrupt"
    j2 = _gen(client, workflow)["jobs"][0]
    client.post(f"/api/jobs/{j2['id']}/cancel")
    assert fake.interrupted == [j2["comfy_prompt_id"]]
    client.poll()
    assert client.get(f"/api/jobs/{j2['id']}").json()["status"] == "interrupted"
    assert client.post(f"/api/jobs/{j2['id']}/cancel").status_code == 409


def test_consistency_config_profile_prompt_and_reproduce(client, workflow, ref, project):
    prof = client.post("/api/profiles", json={"kind": "product", "name": "Aurora", "description": "gold ring",
                                              "preserve_details": ["prongs"]}).json()
    client.post(f"/api/profiles/{prof['id']}/images", json={"reference_id": ref["id"], "role": "primary"})
    plan = client.get(f"/api/consistency/plan/{workflow['id']}?profile_id={prof['id']}").json()
    assert plan["suggested_bindings"] == {"10.image": ref["id"]}
    assert client.post("/api/consistency", json={"name": "x", "workflow_id": workflow["id"],
                                                 "image_bindings": {"6.text": ref["id"]}}).status_code == 422
    cfg = client.post("/api/consistency", json={
        "name": "Aurora packshot", "workflow_id": workflow["id"], "profile_id": prof["id"],
        "project_id": project["id"], "image_bindings": plan["suggested_bindings"], "values": {"3.steps": 8}}).json()
    job = client.post("/api/generate", json={"consistency_config_id": cfg["id"], "seed_mode": "fixed"}).json()["jobs"][0]
    sent = client.fake.prompts[job["comfy_prompt_id"]]["prompt"]
    assert sent["3"]["inputs"]["steps"] == 8
    assert sent["6"]["inputs"]["text"] == "a gold ring, gold ring, preserve exactly: prongs"
    assert "missing stones" in sent["7"]["inputs"]["text"]
    assert job["project_id"] == project["id"] and job["consistency_config_id"] == cfg["id"]
    client.fake.finish_all()
    client.poll()
    rep = client.post(f"/api/jobs/{job['id']}/reproduce").json()
    assert client.fake.prompts[rep["comfy_prompt_id"]]["prompt"] == sent  # identical prompt, same seed


def test_output_curation_export_and_compare(client, workflow, ref):
    _gen(client, workflow, variations=2)
    client.fake.finish_all()
    client.poll()
    outs = client.get("/api/outputs").json()
    o = client.patch(f"/api/outputs/{outs[0]['id']}", json={"favorite": True, "selected": True, "rating": 5}).json()
    assert o["selected"] and o["rating"] == 5
    assert len(client.get("/api/outputs?selected=true").json()) == 1
    assert client.patch(f"/api/outputs/{outs[0]['id']}", json={"rating": 9}).status_code == 422
    z = zipfile.ZipFile(io.BytesIO(client.post("/api/outputs/export", json={"output_ids": [o["id"]]}).content))
    names = set(z.namelist())
    assert "manifest.json" in names and any(n.endswith(".workflow_api.json") for n in names)
    assert json.loads(z.read("manifest.json"))["outputs"][0]["selected"] is True
    cmp = client.post(f"/api/outputs/{outs[0]['id']}/compare",
                      json={"reference_ids": [ref["id"]], "output_ids": [outs[1]["id"]]}).json()
    same = cmp["results"][1]
    assert same["structural_similarity"] > 0.99 and same["perceptual_hash_distance"] == 0
    assert -1 <= cmp["results"][0]["color_histogram_correlation"] <= 1
    md = client.get(f"/api/outputs/{o['id']}/metadata").json()
    assert md["api_prompt"]["3"]["class_type"] == "KSampler"


def test_comfy_status_settings_and_custom_nodes(client):
    st = client.get("/api/comfy/status").json()
    assert st["reachable"] and st["version"] == "0.46.0"
    diag = client.get("/api/comfy/diagnostics").json()
    names = {c["name"]: c["ok"] for c in diag["checks"]}
    assert names["HTTP reachable"] and names["Creative Studio nodes"] is False
    nodes = client.get("/api/custom-nodes").json()
    assert len(nodes["nodes"]) == 7 and all(n["installed"] is False for n in nodes["nodes"])
    assert client.get("/api/comfy/nodes?search=ksampler").json()[0]["name"] == "KSampler"
    assert client.put("/api/settings", json={"comfy_url": "ftp://x"}).status_code == 422
    client.fake.up = False
    assert client.get("/api/comfy/status").json()["reachable"] is False


def test_demo_seed(client):
    p = client.post("/api/demo/jewelry").json()
    again = client.post("/api/demo/jewelry").json()
    assert p["id"] == again["id"]  # idempotent
    detail = client.get(f"/api/projects/{p['id']}").json()
    assert detail["counts"]["references"] == 3 and len(detail["workflows"]) == 3
    assert detail["profiles"][0]["preserve_details"]
    assert len(client.get(f"/api/consistency?project_id={p['id']}").json()) == 3
