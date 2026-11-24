"""Pure-logic tests (no torch needed)."""
import json

import pytest


def test_parse_variables_lines_and_json(core):
    assert core.parse_variables("a: 1\n# c\nb.c = two words\n") == {"a": "1", "b.c": "two words"}
    assert core.parse_variables('{"x": "y", "n": 3}') == {"x": "y", "n": "3"}
    with pytest.raises(core.NodeInputError):
        core.parse_variables("not a pair")
    with pytest.raises(core.NodeInputError):
        core.parse_variables("[1,2]")


def test_render_template_defaults_strict_and_escapes(core):
    out, info = core.render_template("ring of {metal|gold} on {surface}, {{literal}}", {"surface": "marble"})
    assert out == "ring of gold on marble, {literal}"
    assert info["missing"] == []
    with pytest.raises(core.NodeInputError, match="surface"):
        core.render_template("on {surface}", {}, strict=True)
    out, info = core.render_template("a, {missing}, b", {}, strict=False)
    assert out == "a, b" and info["missing"] == ["missing"]


def test_profile_fragment_is_deterministic(core):
    p = core.parse_profile(json.dumps({"name": "Aurora Ring", "kind": "product", "description": "Solitaire ring.",
                                       "attributes": {"material": "18k gold", "stones": ["diamond", "sapphire"]},
                                       "preserve_details": ["six-prong setting", " "]}), "product")
    frag = core.profile_fragment(p)
    assert frag["positive"] == ("Solitaire ring, material: 18k gold, stones: diamond, sapphire, "
                                "preserve exactly: six-prong setting")
    assert "extra stones" in frag["negative"]
    v = core.profile_variables(p)
    assert v["profile.name"] == "Aurora Ring" and v["profile.attributes.material"] == "18k gold"


def test_parse_profile_errors(core):
    with pytest.raises(core.NodeInputError, match="empty"):
        core.parse_profile("", "product")
    with pytest.raises(core.NodeInputError, match="expected a product"):
        core.parse_profile('{"name": "x", "kind": "character"}', "product")


def test_safe_input_path_blocks_traversal(core, tmp_path):
    (tmp_path / "a.png").write_bytes(b"x")
    assert core.safe_input_path(str(tmp_path), "a.png").endswith("a.png")
    with pytest.raises(core.NodeInputError, match="escapes"):
        core.safe_input_path(str(tmp_path), "../etc/passwd")
    with pytest.raises(core.NodeInputError, match="not found"):
        core.safe_input_path(str(tmp_path), "missing.png")


def test_variants_and_seeds(core):
    vs = core.parse_variants("warm | golden light\ncool | daylight\nplain line")
    assert [v["label"] for v in vs] == ["warm", "cool", "v3"]
    sel = core.select_variant(vs, 4, 100, "increment")
    assert sel["label"] == "cool" and sel["seed"] == 104 and sel["wrapped"] is True
    h1 = core.select_variant(vs, 0, 7, "hash")["seed"]
    assert h1 == core.select_variant(vs, 0, 7, "hash")["seed"] != core.select_variant(vs, 1, 7, "hash")["seed"]
    assert core.parse_variants('["a", {"label": "b", "text": "t", "metal": "gold"}]')[1]["metal"] == "gold"
    with pytest.raises(core.NodeInputError):
        core.select_variant(vs, -1, 0, "increment")


def test_project_prefix(core):
    rec = core.project_record("7", "Luxury Jewelry Campaign", "Winter Collection 2026", "42", "gold, ring ,")
    assert rec["tags"] == ["gold", "ring"]
    assert core.filename_prefix(rec) == "creative_studio/luxury-jewelry-campaign/winter-collection-2026/job42"


def test_hash_cache(core, tmp_path):
    f = tmp_path / "m.safetensors"
    f.write_bytes(b"model-bytes")
    cache = core.HashCache(str(tmp_path / "cache.json"))
    import hashlib
    assert cache.sha256(str(f)) == hashlib.sha256(b"model-bytes").hexdigest()
    assert json.loads((tmp_path / "cache.json").read_text())  # persisted
    prompt = {"1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "m.safetensors"}},
              "2": {"class_type": "KSampler", "inputs": {"seed": 5, "steps": 20, "cfg": 7, "sampler_name": "euler",
                                                         "scheduler": "normal", "denoise": 1, "model": ["1", 0]}}}
    assert core.model_refs(prompt) == [("ckpt_name", "checkpoints", "m.safetensors")]
    assert core.sampler_summary(prompt)[0]["seed"] == 5
