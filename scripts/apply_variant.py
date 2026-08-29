"""Apply a variant JSON to the repo in-place before iOS build.

Reads variants/<id>.json and mutates:
  - capacitor.config.json          -> appId, appName
  - ios/App/App/Info.plist         -> CFBundleDisplayName
  - ios/App/App.xcodeproj/…pbxproj -> PRODUCT_BUNDLE_IDENTIFIER (all occurrences)
  - www/index.html                 -> image source (baked or dynamic fetch URL)
  - AppIcon-512@2x.png             -> 1024x1024 opaque RGB PNG (if icon supplied)

Idempotent: re-running with the same variant produces identical files.

Usage:  python scripts/apply_variant.py variants/red.json
"""

from __future__ import annotations

import base64
import io
import json
import plistlib
import re
import sys
import urllib.request
from pathlib import Path

BASE_BUNDLE = "app.claude.applicationclaude"
REPO = Path(__file__).resolve().parent.parent

SUFFIX_RE = re.compile(r"^[a-z0-9]([a-z0-9-]*[a-z0-9])?$")
ID_RE = re.compile(r"^[a-z0-9]([a-z0-9-]*[a-z0-9])?$")


def load_variant(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    vid = data.get("id", "")
    if not ID_RE.match(vid):
        raise SystemExit(f"invalid variant id: {vid!r} (allowed: a-z0-9-, must start/end alnum)")
    suffix = data.get("appIdSuffix", "")
    if suffix and not SUFFIX_RE.match(suffix):
        raise SystemExit(f"invalid appIdSuffix: {suffix!r}")
    if not data.get("appName"):
        raise SystemExit("appName is required")
    # Exactly one of image_url / image_data_url / config_url must be present.
    modes = [k for k in ("image_url", "image_data_url", "config_url") if data.get(k)]
    if len(modes) != 1:
        raise SystemExit(f"variant must have exactly one of image_url|image_data_url|config_url (got: {modes})")
    return data


def compute_bundle_id(suffix: str) -> str:
    return BASE_BUNDLE if not suffix else f"{BASE_BUNDLE}.{suffix}"


def patch_capacitor_config(bundle_id: str, app_name: str) -> None:
    path = REPO / "capacitor.config.json"
    cfg = json.loads(path.read_text(encoding="utf-8"))
    cfg["appId"] = bundle_id
    cfg["appName"] = app_name
    path.write_text(json.dumps(cfg, indent=2) + "\n", encoding="utf-8")
    print(f"  [ok] capacitor.config.json -> appId={bundle_id}, appName={app_name!r}")


def patch_info_plist(app_name: str) -> None:
    path = REPO / "ios" / "App" / "App" / "Info.plist"
    with path.open("rb") as fh:
        plist = plistlib.load(fh)
    plist["CFBundleDisplayName"] = app_name
    plist["CFBundleName"] = app_name
    with path.open("wb") as fh:
        plistlib.dump(plist, fh, sort_keys=False)
    print(f"  [ok] Info.plist -> CFBundleDisplayName={app_name!r}")


def patch_pbxproj(bundle_id: str) -> None:
    path = REPO / "ios" / "App" / "App.xcodeproj" / "project.pbxproj"
    text = path.read_text(encoding="utf-8")
    new_text, n = re.subn(
        r"PRODUCT_BUNDLE_IDENTIFIER = [^;]+;",
        f"PRODUCT_BUNDLE_IDENTIFIER = {bundle_id};",
        text,
    )
    if n == 0:
        raise SystemExit("no PRODUCT_BUNDLE_IDENTIFIER lines found in pbxproj")
    path.write_text(new_text, encoding="utf-8")
    print(f"  [ok] project.pbxproj -> PRODUCT_BUNDLE_IDENTIFIER replaced ({n}× -> {bundle_id})")


IMAGE_BLOCK_RE = re.compile(
    r"/\* VARIANT:IMAGE:START \*/.*?/\* VARIANT:IMAGE:END \*/",
    re.DOTALL,
)


def build_image_block(variant: dict) -> str:
    """Return the JS snippet that decides how #img is populated."""
    if variant.get("image_data_url"):
        # Bake the data URL as a literal — no network call, no polling.
        data_url_js = json.dumps(variant["image_data_url"])
        return (
            "/* VARIANT:IMAGE:START */\n"
            f"  imgEl.src = {data_url_js};\n"
            "  /* VARIANT:IMAGE:END */"
        )
    if variant.get("image_url"):
        # Static remote URL — fetched once at load, no polling.
        url_js = json.dumps(variant["image_url"])
        return (
            "/* VARIANT:IMAGE:START */\n"
            f"  imgEl.src = {url_js};\n"
            "  /* VARIANT:IMAGE:END */"
        )
    # Fallback: dynamic polling from a config endpoint.
    cfg_url = variant["config_url"]
    cfg_js = json.dumps(cfg_url)
    return (
        "/* VARIANT:IMAGE:START */\n"
        f"  var CONFIG_URL = {cfg_js};\n"
        "  var lastSrc = null;\n"
        "  async function refresh() {\n"
        "    try {\n"
        "      var r = await fetch(CONFIG_URL + '?t=' + Date.now(), {cache:'no-store'});\n"
        "      if (!r.ok) return;\n"
        "      var cfg = await r.json();\n"
        "      var url = (cfg.image_url || '').trim();\n"
        "      if (!url) return;\n"
        f"      if (!/^(https?:|data:)/.test(url)) url = new URL(url, {cfg_js}).href;\n"
        "      if (url !== lastSrc) { imgEl.src = url; lastSrc = url; }\n"
        "    } catch (_) {}\n"
        "  }\n"
        "  refresh();\n"
        "  setInterval(refresh, 5000);\n"
        "  /* VARIANT:IMAGE:END */"
    )


def patch_www_index(variant: dict) -> None:
    path = REPO / "www" / "index.html"
    text = path.read_text(encoding="utf-8")
    new_block = build_image_block(variant)
    if IMAGE_BLOCK_RE.search(text):
        text = IMAGE_BLOCK_RE.sub(new_block, text)
    else:
        # First run: inject after `var imgEl = ...;` and remove any legacy code
        # between that line and the SystemBars call.
        marker_start = "var imgEl = document.getElementById('img');"
        marker_end = "// Hide status bar"
        s = text.find(marker_start)
        e = text.find(marker_end)
        if s < 0 or e < 0 or e < s:
            raise SystemExit("www/index.html markers not found — cannot inject variant image block")
        head = text[: s + len(marker_start)]
        tail = text[e:]
        text = head + "\n\n  " + new_block + "\n\n  " + tail
    path.write_text(text, encoding="utf-8")
    mode = "data_url" if variant.get("image_data_url") else "url" if variant.get("image_url") else "dynamic"
    print(f"  [ok] www/index.html -> image mode={mode}")


def load_icon_bytes(variant: dict) -> bytes | None:
    if variant.get("icon_b64"):
        return base64.b64decode(variant["icon_b64"])
    url = variant.get("icon_url")
    if url:
        with urllib.request.urlopen(url, timeout=30) as r:
            return r.read()
    return None


def patch_app_icon(icon_bytes: bytes) -> None:
    from PIL import Image  # imported lazily so envs without Pillow can dry-run

    im = Image.open(io.BytesIO(icon_bytes))
    if im.mode in ("RGBA", "LA") or (im.mode == "P" and "transparency" in im.info):
        bg = Image.new("RGB", im.size, (255, 255, 255))
        bg.paste(im, mask=im.convert("RGBA").split()[-1])
        im = bg
    else:
        im = im.convert("RGB")
    # Center-crop to square, then resize to 1024.
    w, h = im.size
    side = min(w, h)
    im = im.crop(((w - side) // 2, (h - side) // 2, (w + side) // 2, (h + side) // 2))
    im = im.resize((1024, 1024), Image.LANCZOS)
    out = REPO / "ios" / "App" / "App" / "Assets.xcassets" / "AppIcon.appiconset" / "AppIcon-512@2x.png"
    im.save(out, format="PNG", optimize=True)
    print(f"  [ok] AppIcon-512@2x.png -> 1024x1024 opaque replaced ({out.stat().st_size} bytes)")


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__, file=sys.stderr)
        return 2
    variant_path = Path(argv[1]).resolve()
    variant = load_variant(variant_path)
    bundle_id = compute_bundle_id(variant.get("appIdSuffix", ""))
    print(f"[apply] variant id={variant['id']!r} bundle={bundle_id} name={variant['appName']!r}")
    patch_capacitor_config(bundle_id, variant["appName"])
    patch_info_plist(variant["appName"])
    patch_pbxproj(bundle_id)
    patch_www_index(variant)
    icon = load_icon_bytes(variant)
    if icon:
        patch_app_icon(icon)
    else:
        print("  [skip] no custom icon — keeping default AppIcon")
    print(f"[done] variant {variant['id']!r} applied.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
