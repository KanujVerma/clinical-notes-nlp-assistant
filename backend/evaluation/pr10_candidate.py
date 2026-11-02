"""PR #10 candidate transforms. One conceptual change from the parent spec."""
from __future__ import annotations

import io
import math

from PIL import Image, ImageEnhance, ImageFilter, ImageOps

from evaluation.public_amr_benchmark import infer_image

CANDIDATES = ("jpeg_baseline", "png_lossless", "contrast_autocontrast", "jpeg_ctx8192")
CONTEXT = {"jpeg_ctx8192": 8192}
GLM_OCR_SYSTEM = (
    "You are an accurate visual OCR document transcription model (GLM-OCR). "
    "Transcribe all text from the image accurately into JSON format with keys: "
    "'text' (full transcribed text string of all lines), "
    "'boxes' (list of {text, bbox: [x0, y0, x1, y1]}), and "
    "'confidence' (number between 0 and 1). "
    "Ensure all document lines are included in the 'text' field."
)
GLM_OCR_USER = "Transcribe all visible text from page {page_number} into JSON now."
PROMPTS = {
    "frozen": (GLM_OCR_SYSTEM, GLM_OCR_USER),
    "verbatim": (
        "Transcribe the handwriting verbatim. Preserve line breaks, spelling, "
        "digits, decimals, units and symbols as seen. Do not correct medical terms. "
        "Return one JSON object with a string field 'text'.",
        GLM_OCR_USER,
    ),
    "layout": (
        "Transcribe the page in reading order and preserve line breaks. "
        "Do not add headings or interpretation. "
        "Return one JSON object with a string field 'text'.",
        GLM_OCR_USER,
    ),
    "no_infer": (
        "Transcribe only handwriting you can see. Do not infer or complete "
        "illegible medication names, doses, decimals or units. Leave illegible "
        "spots as [illegible]. Return one JSON object with a string field 'text'.",
        GLM_OCR_USER,
    ),
}


def base_spec(**overrides) -> dict:
    spec = {
        "name": "jpeg_baseline",
        "parent": None,
        "family": "baseline",
        "hypothesis": "Unchanged PR #9 JPEG adapter and default context.",
        "encode": "jpeg",
        "contrast": None,
        "grayscale": False,
        "gamma": None,
        "sharpen": False,
        "denoise": False,
        "trim": False,
        "longest": 3000,
        "num_ctx": None,
        "prompt": "frozen",
        "dedupe_lines": False,
        "collapse_spaces": False,
        "second_pass": False,
        "segment": "page",
    }
    spec.update(overrides)
    return spec


def historical_specs() -> dict[str, dict]:
    return {
        "jpeg_baseline": base_spec(),
        "png_lossless": base_spec(
            name="png_lossless", parent="jpeg_baseline", family="A",
            hypothesis="Lossless PNG instead of JPEG, same geometry and prompt.",
            encode="png",
        ),
        "contrast_autocontrast": base_spec(
            name="contrast_autocontrast", parent="jpeg_baseline", family="A",
            hypothesis="Stroke-preserving autocontrast, then the baseline JPEG.",
            contrast="autocontrast",
        ),
        "jpeg_ctx8192": base_spec(
            name="jpeg_ctx8192", parent="jpeg_baseline", family="D",
            hypothesis="Same JPEG and prompt with an 8192-token context so full pages are not truncated.",
            num_ctx=8192,
        ),
    }


TRACKED = (
    "encode", "contrast", "grayscale", "gamma", "sharpen", "denoise", "trim",
    "longest", "num_ctx", "prompt", "dedupe_lines", "collapse_spaces",
    "second_pass", "segment", "jpeg_quality",
)


def resolve_spec(name: str) -> dict:
    """Rebuild a historical or one-variable child spec. Does not read checkpoints."""
    found: dict[str, dict] = {}

    def walk(spec: dict, depth: int) -> None:
        if spec["name"] in found or depth > 3:
            return
        found[spec["name"]] = spec
        for child in mutation_queue(spec):
            walk(child, depth + 1)

    for spec in historical_specs().values():
        walk(spec, 0)
    if name not in found:
        raise KeyError(name)
    return found[name]


def changed_fields(parent: dict, child: dict) -> list[str]:
    return [key for key in TRACKED if child.get(key) != parent.get(key)]


def mutation_queue(parent: dict) -> list[dict]:
    """One-variable children of the incumbent, in priority order."""
    name = parent["name"]
    shared = {"parent": name, "num_ctx": parent["num_ctx"], "prompt": parent["prompt"],
              "encode": parent["encode"], "segment": parent["segment"]}
    planned = [
        ("C", "no_infer", "Ask the model not to invent illegible medication values.",
         {"prompt": "no_infer"}),
        ("C", "verbatim", "Ask for a verbatim transcription without medical correction.",
         {"prompt": "verbatim"}),
        ("C", "layout", "Ask for reading-order transcription that preserves line breaks.",
         {"prompt": "layout"}),
        ("A", "png", "Encode the same scaled page as PNG.", {"encode": "png"}),
        ("A", "contrast", "Apply autocontrast before the same encode.",
         {"contrast": "autocontrast"}),
        ("A", "grayscale", "Convert to grayscale before encode.", {"grayscale": True}),
        ("A", "gamma13", "Raise midtones with gamma 1.3.", {"gamma": 1.3}),
        ("A", "gamma085", "Darken midtones with gamma 0.85.", {"gamma": 0.85}),
        ("A", "sharpen", "Mild sharpening that keeps thin strokes.", {"sharpen": True}),
        ("A", "denoise", "3x3 median denoise before encode.", {"denoise": True}),
        ("A", "trim", "Trim the near-white margin and pad it back.", {"trim": True}),
        ("A", "side2400", "Cap the long side at 2400 pixels.", {"longest": 2400}),
        ("A", "side1800", "Cap the long side at 1800 pixels.", {"longest": 1800}),
        ("D", "ctx16384", "Raise context from 8192 to 16384 tokens.", {"num_ctx": 16384}),
        ("B", "lines", "Recognize deterministic line crops and join them in order.",
         {"segment": "lines"}),
        ("B", "blocks", "Recognize deterministic text-block crops and join them in order.",
         {"segment": "blocks"}),
        ("D", "dedupe", "Drop consecutive duplicate lines without changing tokens.",
         {"dedupe_lines": True}),
        ("D", "spaces", "Collapse repeated spaces while preserving line breaks.",
         {"collapse_spaces": True}),
        ("E", "second", "One extra OCR pass only when the first text is under 12 characters.",
         {"second_pass": True}),
        ("A", "q95", "JPEG quality 95 instead of 85.", {"jpeg_quality": 95}),
    ]
    children = []
    for family, slug, hypothesis, change in planned:
        spec = base_spec(**{**parent, **shared, **change})
        spec["name"] = f"{name}__{slug}"
        spec["parent"] = name
        spec["family"] = family
        spec["hypothesis"] = hypothesis
        if changed_fields(parent, spec) != [next(iter(change))]:
            continue
        children.append(spec)
    return children


def _scaled_rgb(original: bytes, longest: int) -> Image.Image:
    with Image.open(io.BytesIO(original)) as image:
        rgb = ImageOps.exif_transpose(image).convert("RGB")
        scale = min(1.0, longest / max(rgb.size),
                    math.sqrt(14_000_000 / (rgb.width * rgb.height)))
        if scale < 1:
            rgb = rgb.resize((max(1, int(rgb.width * scale)),
                              max(1, int(rgb.height * scale))), Image.Resampling.LANCZOS)
        return rgb.copy()


def _gamma(rgb: Image.Image, gamma: float) -> Image.Image:
    exponent = 1.0 / gamma
    table = [min(255, int(((index / 255) ** exponent) * 255 + 0.5)) for index in range(256)]
    return rgb.point(table * 3)


def _trim(rgb: Image.Image) -> Image.Image:
    gray = rgb.convert("L")
    mask = gray.point(lambda value: 255 if value < 235 else 0)
    box = mask.getbbox()
    if box is None:
        return rgb
    cropped = rgb.crop(box)
    padded = Image.new("RGB", (cropped.width + 16, cropped.height + 16), "white")
    padded.paste(cropped, (8, 8))
    return padded


def _row_ink(rgb: Image.Image) -> list[bool]:
    column = rgb.convert("L").resize((1, rgb.height), Image.Resampling.BOX)
    return [column.getpixel((0, y)) < 200 for y in range(rgb.height)]


def _runs(flags: list[bool], minimum: int) -> list[tuple[int, int]]:
    runs = []
    start = None
    for index, flag in enumerate(flags):
        if flag and start is None:
            start = index
        elif not flag and start is not None:
            if index - start >= minimum:
                runs.append((start, index))
            start = None
    if start is not None and len(flags) - start >= minimum:
        runs.append((start, len(flags)))
    return runs


def _crops(rgb: Image.Image, runs: list[tuple[int, int]]) -> list[Image.Image]:
    if len(runs) < 2 or len(runs) > 16:
        return [rgb]
    crops = []
    for top, bottom in runs:
        crops.append(rgb.crop((0, max(0, top - 4), rgb.width, min(rgb.height, bottom + 4))))
    return crops


def _regions(rgb: Image.Image, segment: str) -> list[Image.Image]:
    if segment == "page" or rgb.height < 120:
        return [rgb]
    ink = _row_ink(rgb)
    if segment == "lines":
        return _crops(rgb, _runs(ink, 8))
    gaps = []
    start = None
    for index, flag in enumerate(ink):
        if not flag and start is None:
            start = index
        elif flag and start is not None:
            if index - start >= 36:
                gaps.append(index)
            start = None
    if len(gaps) < 1:
        return [rgb]
    bounds = [0, *gaps, rgb.height]
    runs = [(bounds[index], bounds[index + 1]) for index in range(len(bounds) - 1)]
    return _crops(rgb, runs)


def _encode(rgb: Image.Image, spec: dict) -> bytes:
    out = io.BytesIO()
    if spec["encode"] == "png":
        rgb.save(out, format="PNG")
    else:
        rgb.save(out, format="JPEG", quality=spec.get("jpeg_quality", 85),
                 subsampling=0, optimize=True)
    return out.getvalue()


def render_regions(spec: dict, original: bytes) -> list[bytes]:
    untouched = (
        spec["encode"] == "jpeg" and spec.get("jpeg_quality", 85) == 85
        and not spec["contrast"] and not spec["grayscale"] and spec["gamma"] is None
        and not spec["sharpen"] and not spec["denoise"] and not spec["trim"]
        and spec["longest"] == 3000 and spec["segment"] == "page"
    )
    if untouched:
        return [infer_image(original)]
    rgb = _scaled_rgb(original, spec["longest"])
    if spec["grayscale"]:
        rgb = ImageOps.grayscale(rgb).convert("RGB")
    if spec["contrast"] == "autocontrast":
        rgb = ImageOps.autocontrast(rgb, cutoff=1)
    if spec["gamma"] is not None:
        rgb = _gamma(rgb, float(spec["gamma"]))
    if spec["denoise"]:
        rgb = rgb.filter(ImageFilter.MedianFilter(size=3))
    if spec["sharpen"]:
        rgb = ImageEnhance.Sharpness(rgb).enhance(1.4)
    if spec["trim"]:
        rgb = _trim(rgb)
    return [_encode(region, spec) for region in _regions(rgb, spec["segment"])]


def postprocess(spec: dict, text: str) -> str:
    if spec["dedupe_lines"]:
        kept = []
        previous = None
        for line in text.splitlines():
            token = line.strip()
            if token and token == previous:
                continue
            kept.append(line)
            previous = token
        text = "\n".join(kept)
    if spec["collapse_spaces"]:
        text = "\n".join(" ".join(line.split()) for line in text.splitlines())
    return text


def prompt_for(spec: dict) -> tuple[str, str]:
    system, user = PROMPTS[spec["prompt"]]
    return system, user


def apply_candidate(name: str, original: bytes) -> bytes:
    spec = historical_specs().get(name)
    if spec is None:
        raise ValueError("PR10_UNKNOWN_CANDIDATE")
    regions = render_regions(spec, original)
    if len(regions) != 1:
        raise ValueError("PR10_UNEXPECTED_REGIONS")
    return regions[0]
