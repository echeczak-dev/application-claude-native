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
    # Optional alt images — if present, a secret 3-second long-press on the
    # top-right 80x80 corner of the app CYCLES through them (primary → alt →
    # alt2 → primary). Choice is persisted in localStorage.imgIdx.
    # Slot 1 keys: image_url_alt   / image_data_url_alt
    # Slot 2 keys: image_url_alt2  / image_data_url_alt2
    for suf in ("", "2"):
        slot_present = [k for k in (f"image_url_alt{suf}", f"image_data_url_alt{suf}") if data.get(k)]
        if len(slot_present) > 1:
            raise SystemExit(f"at most one source for alt{suf} (got: {slot_present})")
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
    """Rewrite the main App target's PRODUCT_BUNDLE_IDENTIFIER + keep any
    extension targets in the form `<new_app_bundle>.<ExtName>`.

    Prior naive re.subn replaced ALL occurrences with the same id — that
    breaks Widget Extensions because they must have a distinct bundle id.
    We now detect which lines are the "app bundle" (bases matching the
    known BASE_BUNDLE prefix, no dotted extension name) vs "ext bundle"
    (has a suffix that looks like an extension target name like
    'LiveActivityWidget') and rewrite each accordingly."""
    path = REPO / "ios" / "App" / "App.xcodeproj" / "project.pbxproj"
    text = path.read_text(encoding="utf-8")

    # Known extension target suffixes — kept explicit so we don't accidentally
    # try to treat a legit dotted app bundle id as an extension.
    EXT_SUFFIXES = {"LiveActivityWidget"}

    def repl(m: re.Match) -> str:
        old = m.group(1).strip()
        # Trailing part after the last dot — check if it's a known ext name.
        parts = old.rsplit(".", 1)
        if len(parts) == 2 and parts[1] in EXT_SUFFIXES:
            new = f"{bundle_id}.{parts[1]}"
        else:
            new = bundle_id
        return f"PRODUCT_BUNDLE_IDENTIFIER = {new};"

    new_text, n = re.subn(
        r"PRODUCT_BUNDLE_IDENTIFIER = ([^;]+);",
        repl,
        text,
    )
    if n == 0:
        raise SystemExit("no PRODUCT_BUNDLE_IDENTIFIER lines found in pbxproj")
    path.write_text(new_text, encoding="utf-8")
    print(f"  [ok] project.pbxproj -> PRODUCT_BUNDLE_IDENTIFIER rewritten "
          f"({n}× app={bundle_id}, extensions preserved)")


IMAGE_BLOCK_RE = re.compile(
    r"/\* VARIANT:IMAGE:START \*/.*?/\* VARIANT:IMAGE:END \*/",
    re.DOTALL,
)


def _resolve_image_literal_for_slot(variant: dict, slot: int) -> str | None:
    """Return a JS string literal for the given image slot (0/1/2), or None
    if that slot is not configured. Slot 0 = primary. Slots 1/2 = alt/alt2.
    Both data-URL and remote-URL become string literals."""
    if slot == 0:
        keys = ("image_data_url", "image_url")
    elif slot == 1:
        keys = ("image_data_url_alt", "image_url_alt")
    else:
        keys = ("image_data_url_alt2", "image_url_alt2")
    for k in keys:
        if variant.get(k):
            return json.dumps(variant[k])
    return None


def build_image_block(variant: dict) -> str:
    """Return the JS snippet that decides how #img is populated.

    Behaviour:
      - Renders images[0] on load (or the last-chosen index from localStorage).
      - If more than one image is configured, registers a secret gesture:
        3-second long-press on the top-right 80x80 corner CYCLES through
        them (0 → 1 → 2 → 0). A tiny green dot fades in at 2.5s to hint,
        then flashes brighter at 3s when the swap fires.
      - Choice persists in localStorage.imgIdx across relaunches.
      - The dynamic config_url mode is preserved but doesn't participate
        in cycling (it just polls the remote endpoint every 5s)."""
    slots = [_resolve_image_literal_for_slot(variant, i) for i in range(3)]
    slots = [s for s in slots if s]   # keep configured slots only

    if variant.get("config_url"):
        # Dynamic polling mode — no toggle available.
        cfg_js = json.dumps(variant["config_url"])
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

    # Static mode: bake 1..3 images + optional secret-gesture cycle.
    lines = ["/* VARIANT:IMAGE:START */"]
    lines.append(f"  var IMAGES = [{', '.join(slots)}];")
    if len(slots) >= 2:
        lines.append(_cycle_js_snippet())
    else:
        # Single image — no cycle attached.
        lines.append("  imgEl.src = IMAGES[0];")
    lines.append("  /* VARIANT:IMAGE:END */")
    return "\n".join(lines)


def _cycle_js_snippet() -> str:
    """Gesture handler. Cycles through IMAGES[] on every successful 3-sec
    long-press in the top-right 80x80 corner. Persists chosen index in
    localStorage.imgIdx.

    Fix 2026-08-31 : iOS Safari/WebKit intercepts long-press on <img> to
    show its native 'Save Image / Copy' menu + kicks off a drag-preview
    animation that makes the picture look like it's peeling off. That
    stole our timers. Solution : create a dedicated invisible <div>
    overlay in the hotzone, positioned on top of the image, with all
    native touch behaviours disabled (touch-callout none, user-select
    none, user-drag none, touch-action none, contextmenu prevented).
    All handlers live on this div so the img below never sees the touch."""
    return """  function _laImgIdx() {
    var v = parseInt(localStorage.getItem('imgIdx') || '0', 10);
    if (isNaN(v) || v < 0 || v >= IMAGES.length) v = 0;
    return v;
  }
  function _laApplyImg() { imgEl.src = IMAGES[_laImgIdx()]; }
  _laApplyImg();

  // Also disable native long-press callout on the image itself as a
  // belt-and-suspenders measure (in case the user long-presses just OUTSIDE
  // our 80x80 hotzone).
  imgEl.style.webkitTouchCallout = 'none';
  imgEl.style.webkitUserSelect   = 'none';
  imgEl.style.userSelect         = 'none';
  imgEl.style.webkitUserDrag     = 'none';
  imgEl.setAttribute('draggable', 'false');
  imgEl.addEventListener('dragstart', function(e){ e.preventDefault(); });
  imgEl.addEventListener('contextmenu', function(e){ e.preventDefault(); });

  (function _laSecretCycle(){
    var HOTZONE = 80;
    var HOLD_MS = 3000;
    var HINT_MS = 2500;

    // Invisible overlay div in the top-right corner. Sits above everything,
    // eats all touches, prevents iOS native long-press menu / drag preview.
    var pad = document.createElement('div');
    pad.id = 'la-hotpad';
    pad.style.cssText = 'position:fixed;top:0;right:0;width:' + HOTZONE + 'px;height:' + HOTZONE + 'px;'
      + 'z-index:2147483646;background:transparent;'
      + '-webkit-touch-callout:none;-webkit-user-select:none;user-select:none;'
      + '-webkit-user-drag:none;touch-action:none;';
    document.body.appendChild(pad);
    pad.addEventListener('contextmenu', function(e){ e.preventDefault(); }, false);
    pad.addEventListener('dragstart',   function(e){ e.preventDefault(); }, false);

    var pd = null;
    var timerFire = null;
    var timerHint = null;
    var dot = null;
    function cleanup() {
      if (timerFire) { clearTimeout(timerFire); timerFire = null; }
      if (timerHint) { clearTimeout(timerHint); timerHint = null; }
      if (dot) { dot.remove(); dot = null; }
      pd = null;
    }
    function showHint() {
      dot = document.createElement('div');
      dot.style.cssText = 'position:fixed;top:14px;right:14px;width:8px;height:8px;'
        + 'border-radius:50%;background:#4ade80;opacity:0.35;'
        + 'transition:opacity 300ms ease,transform 400ms ease;'
        + 'z-index:2147483647;pointer-events:none';
      document.body.appendChild(dot);
    }
    function fire() {
      if (dot) {
        dot.style.opacity = '1';
        dot.style.transform = 'scale(1.8)';
        dot.style.boxShadow = '0 0 14px #4ade80';
      }
      var next = (_laImgIdx() + 1) % IMAGES.length;
      localStorage.setItem('imgIdx', String(next));
      _laApplyImg();
      setTimeout(cleanup, 320);
    }
    // Use touchstart/touchmove/touchend (not just pointer) so we can
    // preventDefault on iOS webview. Pointer events on iOS won't stop
    // native behaviours reliably; touch events with {passive:false} do.
    pad.addEventListener('touchstart', function(e){
      e.preventDefault();
      var t = e.touches[0];
      pd = {x: t.clientX, y: t.clientY};
      timerHint = setTimeout(showHint, HINT_MS);
      timerFire = setTimeout(fire, HOLD_MS);
    }, {passive: false});
    pad.addEventListener('touchmove', function(e){
      e.preventDefault();
      if (!pd) return;
      var t = e.touches[0];
      if (Math.abs(t.clientX - pd.x) > 30 || Math.abs(t.clientY - pd.y) > 30) cleanup();
    }, {passive: false});
    pad.addEventListener('touchend', function(e){
      e.preventDefault();
      cleanup();
    }, {passive: false});
    pad.addEventListener('touchcancel', function(){ cleanup(); }, {passive: true});

    // Desktop fallback (mouse) — same logic via pointer events on the pad.
    pad.addEventListener('mousedown', function(e){
      pd = {x: e.clientX, y: e.clientY};
      timerHint = setTimeout(showHint, HINT_MS);
      timerFire = setTimeout(fire, HOLD_MS);
    });
    pad.addEventListener('mousemove', function(e){
      if (!pd) return;
      if (Math.abs(e.clientX - pd.x) > 30 || Math.abs(e.clientY - pd.y) > 30) cleanup();
    });
    pad.addEventListener('mouseup', cleanup);
    pad.addEventListener('mouseleave', cleanup);
  })();"""


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
