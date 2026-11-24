"""Projects, references, collections and profiles API tests."""
import sys
from pathlib import Path

from tests.conftest import png_bytes


def test_project_lifecycle(client):
    tpls = {t["key"] for t in client.get("/api/project-templates").json()}
    assert "jewelry_campaign" in tpls
    p = client.post("/api/projects", json={"name": "Winter", "template_key": "jewelry_campaign", "client": "Acme"}).json()
    assert [c["name"] for c in p["campaigns"]] == ["Packshots", "Editorial", "Close-up details"]
    assert client.post("/api/projects", json={"name": "x", "template_key": "nope"}).status_code == 422
    c = client.post(f"/api/projects/{p['id']}/campaigns", json={"name": "Winter Collection 2026"}).json()
    assert client.patch(f"/api/campaigns/{c['id']}", json={"status": "archived"}).json()["status"] == "archived"
    assert client.patch(f"/api/projects/{p['id']}", json={"description": "new"}).json()["description"] == "new"
    assert client.delete(f"/api/projects/{p['id']}").status_code == 409  # must archive first
    assert client.post(f"/api/projects/{p['id']}/archive").json()["status"] == "archived"
    assert client.get("/api/projects").json() == []
    assert len(client.get("/api/projects?status=archived").json()) == 1
    assert client.post(f"/api/projects/{p['id']}/restore").json()["status"] == "active"
    kinds = [a["kind"] for a in client.get(f"/api/projects/{p['id']}/activity").json()]
    assert {"project_created", "campaign_created", "project_archived", "project_restored"} <= set(kinds)
    client.post(f"/api/projects/{p['id']}/archive")
    assert client.delete(f"/api/projects/{p['id']}").status_code == 204


def test_reference_upload_filter_and_reuse(client, project, ref):
    assert ref["tags"] == ["gold", "ring"] and ref["width"] == 64 and ref["project_ids"] == [project["id"]]
    assert len(ref["palette"]) >= 1 and len(ref["sha256"]) == 64
    bad = client.post("/api/references", files=[("files", ("x.png", b"notanimage", "image/png"))],
                      data={"category": "style"})
    assert bad.status_code == 422
    assert client.post("/api/references", files=[("files", ("x.png", png_bytes(), "image/png"))],
                       data={"category": "weird"}).status_code == 422
    client.post("/api/references", files=[("files", ("light.png", png_bytes((250, 240, 200)), "image/png"))],
                data={"category": "lighting", "tags": "warm"})
    assert [r["category"] for r in client.get("/api/references?category=lighting").json()] == ["lighting"]
    assert len(client.get("/api/references?tag=gold").json()) == 1
    assert len(client.get("/api/references?q=ring").json()) == 1
    assert len(client.get(f"/api/references?project_id={project['id']}").json()) == 1
    upd = client.patch(f"/api/references/{ref['id']}", json={"favorite": True, "tags": ["A", "a", " b "]}).json()
    assert upd["favorite"] is True and upd["tags"] == ["a", "b"]
    assert client.get(f"/api/references/{ref['id']}/file").content[:4] == b"\x89PNG"
    assert client.get(f"/api/references/{ref['id']}/thumb").headers["content-type"] == "image/webp"
    # reuse in a second project
    p2 = client.post("/api/projects", json={"name": "Other"}).json()
    assert client.post(f"/api/projects/{p2['id']}/references", json={"ids": [ref["id"]]}).json()["attached"] == 1
    assert sorted(client.get(f"/api/references/{ref['id']}").json()["project_ids"]) == [project["id"], p2["id"]]
    assert {t["tag"] for t in client.get("/api/references/tags").json()} == {"a", "b", "warm"}


def test_collections(client, ref):
    r2 = client.post("/api/references", files=[("files", ("b.png", png_bytes(), "image/png"))],
                     data={"category": "style"}).json()[0]
    c = client.post("/api/collections", json={"name": "Board", "reference_ids": [ref["id"]]}).json()
    c = client.post(f"/api/collections/{c['id']}/items", json={"ids": [r2["id"], ref["id"]]}).json()
    assert c["reference_ids"] == [ref["id"], r2["id"]]
    c = client.patch(f"/api/collections/{c['id']}", json={"reference_ids": [r2["id"], ref["id"]]}).json()
    assert [r["id"] for r in client.get(f"/api/references?collection_id={c['id']}").json()] == [r2["id"], ref["id"]]
    c = client.delete(f"/api/collections/{c['id']}/items/{r2['id']}").json()
    assert c["reference_ids"] == [ref["id"]]
    client.delete(f"/api/references/{ref['id']}")
    assert client.get("/api/collections").json()[-1]["count"] == 0


def test_profiles_and_fragment_parity(client, project, ref):
    p = client.post("/api/profiles", json={
        "kind": "product", "name": "Aurora Ring", "description": "Solitaire ring.", "category": "ring",
        "attributes": {"material": "18k gold", "stones": ["diamond"]}, "preserve_details": ["six prongs"],
        "project_ids": [project["id"]]}).json()
    p = client.post(f"/api/profiles/{p['id']}/images", json={"reference_id": ref["id"], "role": "primary"}).json()
    assert p["images"][0]["reference"]["id"] == ref["id"]
    assert client.post(f"/api/profiles/{p['id']}/images", json={"reference_id": ref["id"], "role": "primary"}).status_code == 409
    assert client.post(f"/api/profiles/{p['id']}/images", json={"reference_id": ref["id"], "role": "bad"}).status_code == 422
    frag = p["prompt_fragment"]
    assert frag["positive"] == "Solitaire ring, material: 18k gold, stones: diamond, preserve exactly: six prongs"
    # The custom node package must produce the identical fragment.
    pkg = Path(__file__).resolve().parents[2] / "custom_nodes" / "comfyui-creative-studio-nodes" / "cs_nodes"
    sys.path.insert(0, str(pkg))
    try:
        import core as node_core  # type: ignore
    finally:
        sys.path.pop(0)
    exported = client.get(f"/api/profiles/{p['id']}/export").json()
    assert node_core.profile_fragment(exported) == frag
    assert [x["id"] for x in client.get("/api/profiles?kind=product").json()] == [p["id"]]
    assert client.get("/api/profiles?kind=character").json() == []
    assert client.get(f"/api/projects/{project['id']}").json()["profiles"][0]["name"] == "Aurora Ring"
    ch = client.post("/api/profiles", json={"kind": "character", "name": "Mila"}).json()
    assert "different person" in client.get(f"/api/profiles/{ch['id']}").json()["prompt_fragment"]["negative"]
