"""Node execution tests. Require torch (as inside ComfyUI); skipped otherwise."""
import json

import pytest

torch = pytest.importorskip("torch")
from PIL import Image  # noqa: E402


def _img(w, h, color=(255, 0, 0)):
    import numpy as np
    a = torch.zeros((1, h, w, 3))
    a[..., 0] = color[0] / 255
    a[..., 1] = color[1] / 255
    a[..., 2] = color[2] / 255
    return a


def test_interfaces_follow_comfy_conventions(pkg):
    for name, cls in pkg.NODE_CLASS_MAPPINGS.items():
        spec = cls.INPUT_TYPES()
        assert "required" in spec, name
        assert isinstance(cls.RETURN_TYPES, tuple), name
        assert hasattr(cls, cls.FUNCTION), name
        assert cls.CATEGORY == "Creative Studio"
        if hasattr(cls, "RETURN_NAMES"):
            assert len(cls.RETURN_NAMES) == len(cls.RETURN_TYPES), name
        assert name in pkg.NODE_DISPLAY_NAME_MAPPINGS


def test_reference_collector_batches_different_sizes(pkg):
    node = pkg.NODE_CLASS_MAPPINGS["CS_ReferenceCollector"]()
    images, mask, refs, count = node.collect("pad", 64, 64, "product, light",
                                             image_1=_img(100, 50), image_3=_img(20, 40, (0, 255, 0)))
    assert images.shape == (2, 64, 64, 3) and mask.shape == (2, 64, 64) and count == 2
    assert [i["label"] for i in refs["items"]] == ["product", "light"]
    assert refs["items"][0]["original_size"] == [100, 50]
    assert mask[0, 0, 32].item() == 1.0 and mask[0, 32, 32].item() == 0.0  # padded top, content centre
    with pytest.raises(ValueError):
        node.collect("pad", 0, 0, "")


def _profile(comfy_dirs, kind="product", roles=("primary",)):
    files = {}
    for i, role in enumerate(roles):
        im = Image.new("RGBA", (80 + i * 10, 60), (200, 180, 40, 255))
        im.putpixel((0, 0), (0, 0, 0, 0))
        (comfy_dirs.input / "creative_studio").mkdir(exist_ok=True)
        rel = f"creative_studio/{role}{i}.png"
        im.save(comfy_dirs.input / rel)
        files.setdefault(role, []).append(rel)
    return json.dumps({"id": 1, "kind": kind, "name": "Aurora Ring", "description": "Solitaire ring",
                       "attributes": {"material": "gold"}, "preserve_details": ["prongs"], "image_files": files})


def test_product_profile_loader(pkg, comfy_dirs):
    cls = pkg.NODE_CLASS_MAPPINGS["CS_ProductProfileLoader"]
    pj = _profile(comfy_dirs, roles=("primary", "detail"))
    assert cls.VALIDATE_INPUTS(profile_json=pj) is True
    assert "empty" in cls.VALIDATE_INPUTS(profile_json="")
    img, mask, detail, pos, neg, info = cls().load(pj, 1024, "pad")
    assert img.shape == (1, 60, 80, 3) and detail.shape == (1, 60, 90, 3)
    assert mask[0, 0, 0].item() == 1.0 and mask[0, 10, 10].item() == 0.0  # LoadImage convention
    assert "material: gold" in pos and "missing stones" in neg and info["name"] == "Aurora Ring"
    first = cls.IS_CHANGED(pj, 1024, "pad")
    assert first == cls.IS_CHANGED(pj, 1024, "pad")


def test_product_profile_missing_file(pkg, comfy_dirs):
    pj = json.dumps({"name": "x", "kind": "product", "image_files": {"primary": ["nope.png"]}})
    with pytest.raises(ValueError, match="not found"):
        pkg.NODE_CLASS_MAPPINGS["CS_ProductProfileLoader"]().load(pj, 0, "pad")


def test_character_loader_falls_back_to_primary(pkg, comfy_dirs):
    node = pkg.NODE_CLASS_MAPPINGS["CS_CharacterProfileLoader"]()
    pj = _profile(comfy_dirs, kind="character", roles=("primary",))
    face, refs, pos, neg, info = node.load(pj, 0, "pad")
    assert face.shape[0] == 1 and "different person" in neg
    pj2 = _profile(comfy_dirs, kind="character", roles=("face", "primary"))
    face2, refs2, *_ = node.load(pj2, 0, "pad")
    assert face2.shape[2] == 80 and refs2.shape[2] == 90  # face role used once present


def test_prompt_template_with_profile_variant_project(pkg, core):
    t = pkg.NODE_CLASS_MAPPINGS["CS_PromptTemplate"]()
    profile = core.parse_profile('{"name": "Aurora", "kind": "product", "attributes": {"material": "gold"}}')
    variant = core.select_variant(core.parse_variants("warm | candle light"), 0, 1, "increment")
    text, res = t.render("{profile.name} in {profile.attributes.material}, {variant.text}, {project.campaign}, {x}",
                         "x: macro", True, profile=profile, variant=variant,
                         project=core.project_record("1", "P", "Winter", "", ""))
    assert text == "Aurora in gold, candle light, Winter, macro"
    assert json.loads(res)["missing"] == []
    with pytest.raises(ValueError):
        t.render("{nope}", "", True)


def test_variant_manager_and_project(pkg):
    seed, text, label, v = pkg.NODE_CLASS_MAPPINGS["CS_BatchVariantManager"]().select("a | one\nb | two", 1, 10,
                                                                                    "increment")
    assert (seed, text, label) == (11, "two", "b")
    project, prefix = pkg.NODE_CLASS_MAPPINGS["CS_ProjectMetadata"]().build("3", "Jewelry", "Winter", "9", "")
    assert prefix.endswith("jewelry/winter/job9") and project["project_id"] == "3"


def test_metadata_saver_writes_png_sidecar_and_hashes(pkg, comfy_dirs):
    (comfy_dirs.models / "checkpoints" / "tiny.safetensors").write_bytes(b"weights")
    prompt = {"4": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "tiny.safetensors"}},
              "5": {"class_type": "KSampler", "inputs": {"seed": 99, "steps": 4, "cfg": 2.0, "sampler_name": "euler",
                                                         "scheduler": "normal", "denoise": 1.0}}}
    node = pkg.NODE_CLASS_MAPPINGS["CS_GenerationMetadataSaver"]()
    res = node.save(_img(16, 8).repeat(2, 1, 1, 1), "creative_studio/test", True, "note", positive="a ring",
                    seed=99, prompt=prompt, extra_pnginfo={"workflow": {"nodes": []}}, unique_id="7")
    imgs, meta = res["ui"]["images"], res["ui"]["cs_metadata"][0]
    assert len(imgs) == 2 and imgs[0]["filename"] != imgs[1]["filename"]
    import hashlib
    assert meta["model_hashes"] == {"tiny.safetensors": hashlib.sha256(b"weights").hexdigest()}
    assert meta["samplers"][0]["seed"] == 99 and meta["prompt"] == "a ring"
    png = comfy_dirs.output / "creative_studio" / imgs[0]["filename"]
    side = json.loads((png.parent / (png.name + ".json")).read_text())
    assert side["file"]["filename"] == imgs[0]["filename"]
    text = Image.open(png).text
    assert json.loads(text["creative_studio"])["seed"] == 99 and "prompt" in text and "workflow" in text
