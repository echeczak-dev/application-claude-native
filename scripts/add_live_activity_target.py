"""Add the LiveActivityWidget extension target to App.xcodeproj/project.pbxproj.

Idempotent — safe to re-run. Detects the target's presence and no-ops.

Why raw text surgery: pbxproj (pypi v4.3.3) doesn't expose a way to add a new
native target, only files/groups on existing targets. Rewriting the whole
project via xcodegen would require adopting a project.yml. Text surgery on
the well-formatted pbxproj is the cheapest path — we just insert well-known
snippets at named markers ("Begin/End PBXBuildFile section", etc.).

Run this once locally + in CI (before xcodebuild). We also bump the main
App target's IPHONEOS_DEPLOYMENT_TARGET to 16.2 so ActivityKit APIs are
available in LiveActivityRouter.
"""
from __future__ import annotations

import hashlib
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PBXPROJ = REPO / "ios" / "App" / "App.xcodeproj" / "project.pbxproj"
EXT_NAME = "LiveActivityWidget"


def uuid(seed: str) -> str:
    """Deterministic 24-char hex uppercase — mimics Xcode's PBX UUIDs so
    the script is idempotent (same seed => same UUID)."""
    return hashlib.md5(seed.encode()).hexdigest()[:24].upper()


# ── Stable UUIDs (all prefixed LA_ so they don't collide with existing) ──
IDS = {
    # PBXFileReference IDs
    "attrs_ref":     uuid("LA_ref_LiveActivityAttributes.swift"),
    "view_ref":      uuid("LA_ref_LiveActivityView.swift"),
    "bundle_ref":    uuid("LA_ref_LiveActivityWidgetBundle.swift"),
    "router_ref":    uuid("LA_ref_LiveActivityRouter.swift"),
    "plist_ref":     uuid("LA_ref_ExtInfoPlist"),
    "appex_ref":     uuid("LA_ref_LiveActivityWidget.appex"),
    # PBXBuildFile IDs (file compiled into a target)
    "attrs_bf_ext":  uuid("LA_bf_ext_attrs"),
    "attrs_bf_app":  uuid("LA_bf_app_attrs"),
    "view_bf":       uuid("LA_bf_view"),
    "bundle_bf":     uuid("LA_bf_bundle"),
    "router_bf":     uuid("LA_bf_router"),
    "embed_bf":      uuid("LA_bf_embed_appex"),
    # Groups
    "ext_group":     uuid("LA_group_ext"),
    # Target + phases
    "target":        uuid("LA_target"),
    "sources_phase": uuid("LA_phase_sources"),
    "resources_phase": uuid("LA_phase_resources"),
    "frameworks_phase": uuid("LA_phase_frameworks"),
    "embed_phase":   uuid("LA_phase_embed"),
    # Configurations
    "target_debug":  uuid("LA_cfg_debug"),
    "target_release": uuid("LA_cfg_release"),
    "target_cfglist": uuid("LA_cfg_list"),
    # Dependency
    "tgt_dep":       uuid("LA_tgt_dep"),
    "container_proxy": uuid("LA_container_proxy"),
}

# The main App target's UUID is stable (comes from Capacitor template).
# If it ever changes, we auto-detect it from the pbxproj text.
DEFAULT_MAIN_TARGET_UUID = "504EC3031FED79650016851F"


def find_main_target_uuid(text: str) -> str:
    m = re.search(r"([0-9A-F]{24}) /\* App \*/ = \{\s*isa = PBXNativeTarget;", text)
    if m:
        return m.group(1)
    return DEFAULT_MAIN_TARGET_UUID


def find_project_uuid(text: str) -> str:
    m = re.search(r"([0-9A-F]{24}) /\* Project object \*/ = \{\s*isa = PBXProject;", text)
    return m.group(1) if m else ""


def find_root_group_uuid(text: str) -> str:
    """Root group has mainGroup pointing at it, and its children include
    'App' and 'Products'."""
    m = re.search(r"mainGroup = ([0-9A-F]{24});", text)
    return m.group(1) if m else ""


def find_products_group_uuid(text: str) -> str:
    m = re.search(r"([0-9A-F]{24}) /\* Products \*/ = \{\s*isa = PBXGroup;", text)
    return m.group(1) if m else ""


def find_app_group_uuid(text: str) -> str:
    m = re.search(r"([0-9A-F]{24}) /\* App \*/ = \{\s*isa = PBXGroup;", text)
    return m.group(1) if m else ""


def find_app_sources_phase(text: str) -> str:
    """Find the App target's Sources phase UUID (referenced from the target's
    buildPhases list). The first PBXSourcesBuildPhase whose id appears in
    the App target's buildPhases wins."""
    app_uuid = find_main_target_uuid(text)
    m = re.search(
        rf"{app_uuid} /\* App \*/ = \{{[^}}]+?buildPhases = \(([^)]+)\);",
        text, re.DOTALL,
    )
    if not m:
        return ""
    for phase_id in re.findall(r"([0-9A-F]{24})", m.group(1)):
        # Is it a Sources phase?
        if re.search(rf"{phase_id} /\* Sources \*/ = \{{\s*isa = PBXSourcesBuildPhase;", text):
            return phase_id
    return ""


def find_app_bundle_id(text: str) -> str:
    m = re.search(r"PRODUCT_BUNDLE_IDENTIFIER = ([^;]+);", text)
    return m.group(1).strip() if m else "app.claude.applicationclaude"


# ── Snippet builders ────────────────────────────────────────────────────

def build_pbxbuildfile_entries() -> str:
    return f"""		{IDS["attrs_bf_ext"]} /* LiveActivityAttributes.swift in Sources */ = {{isa = PBXBuildFile; fileRef = {IDS["attrs_ref"]} /* LiveActivityAttributes.swift */; }};
		{IDS["view_bf"]} /* LiveActivityView.swift in Sources */ = {{isa = PBXBuildFile; fileRef = {IDS["view_ref"]} /* LiveActivityView.swift */; }};
		{IDS["bundle_bf"]} /* LiveActivityWidgetBundle.swift in Sources */ = {{isa = PBXBuildFile; fileRef = {IDS["bundle_ref"]} /* LiveActivityWidgetBundle.swift */; }};
		{IDS["router_bf"]} /* LiveActivityRouter.swift in Sources */ = {{isa = PBXBuildFile; fileRef = {IDS["router_ref"]} /* LiveActivityRouter.swift */; }};
		{IDS["attrs_bf_app"]} /* LiveActivityAttributes.swift in Sources */ = {{isa = PBXBuildFile; fileRef = {IDS["attrs_ref"]} /* LiveActivityAttributes.swift */; }};
		{IDS["embed_bf"]} /* {EXT_NAME}.appex in Embed App Extensions */ = {{isa = PBXBuildFile; fileRef = {IDS["appex_ref"]} /* {EXT_NAME}.appex */; settings = {{ATTRIBUTES = (RemoveHeadersOnCopy, ); }}; }};
"""


def build_pbxfilereference_entries() -> str:
    return f"""		{IDS["attrs_ref"]} /* LiveActivityAttributes.swift */ = {{isa = PBXFileReference; lastKnownFileType = sourcecode.swift; path = LiveActivityAttributes.swift; sourceTree = "<group>"; }};
		{IDS["view_ref"]} /* LiveActivityView.swift */ = {{isa = PBXFileReference; lastKnownFileType = sourcecode.swift; path = LiveActivityView.swift; sourceTree = "<group>"; }};
		{IDS["bundle_ref"]} /* LiveActivityWidgetBundle.swift */ = {{isa = PBXFileReference; lastKnownFileType = sourcecode.swift; path = LiveActivityWidgetBundle.swift; sourceTree = "<group>"; }};
		{IDS["router_ref"]} /* LiveActivityRouter.swift */ = {{isa = PBXFileReference; lastKnownFileType = sourcecode.swift; path = LiveActivityRouter.swift; sourceTree = "<group>"; }};
		{IDS["plist_ref"]} /* Info.plist */ = {{isa = PBXFileReference; lastKnownFileType = text.plist.xml; path = Info.plist; sourceTree = "<group>"; }};
		{IDS["appex_ref"]} /* {EXT_NAME}.appex */ = {{isa = PBXFileReference; explicitFileType = "wrapper.app-extension"; includeInIndex = 0; path = "{EXT_NAME}.appex"; sourceTree = BUILT_PRODUCTS_DIR; }};
"""


def build_pbxgroup_ext(text: str) -> str:
    return f"""		{IDS["ext_group"]} /* {EXT_NAME} */ = {{
			isa = PBXGroup;
			children = (
				{IDS["attrs_ref"]} /* LiveActivityAttributes.swift */,
				{IDS["view_ref"]} /* LiveActivityView.swift */,
				{IDS["bundle_ref"]} /* LiveActivityWidgetBundle.swift */,
				{IDS["plist_ref"]} /* Info.plist */,
			);
			path = {EXT_NAME};
			sourceTree = "<group>";
		}};
"""


def build_target_and_phases(text: str) -> tuple[str, str, str, str]:
    """Return (sources_phase, resources_phase, frameworks_phase, target)
    snippets as pbxproj text."""
    sources = f"""		{IDS["sources_phase"]} /* Sources */ = {{
			isa = PBXSourcesBuildPhase;
			buildActionMask = 2147483647;
			files = (
				{IDS["attrs_bf_ext"]} /* LiveActivityAttributes.swift in Sources */,
				{IDS["view_bf"]} /* LiveActivityView.swift in Sources */,
				{IDS["bundle_bf"]} /* LiveActivityWidgetBundle.swift in Sources */,
			);
			runOnlyForDeploymentPostprocessing = 0;
		}};
"""
    resources = f"""		{IDS["resources_phase"]} /* Resources */ = {{
			isa = PBXResourcesBuildPhase;
			buildActionMask = 2147483647;
			files = (
			);
			runOnlyForDeploymentPostprocessing = 0;
		}};
"""
    frameworks = f"""		{IDS["frameworks_phase"]} /* Frameworks */ = {{
			isa = PBXFrameworksBuildPhase;
			buildActionMask = 2147483647;
			files = (
			);
			runOnlyForDeploymentPostprocessing = 0;
		}};
"""
    target = f"""		{IDS["target"]} /* {EXT_NAME} */ = {{
			isa = PBXNativeTarget;
			buildConfigurationList = {IDS["target_cfglist"]} /* Build configuration list for PBXNativeTarget "{EXT_NAME}" */;
			buildPhases = (
				{IDS["sources_phase"]} /* Sources */,
				{IDS["frameworks_phase"]} /* Frameworks */,
				{IDS["resources_phase"]} /* Resources */,
			);
			buildRules = (
			);
			dependencies = (
			);
			name = {EXT_NAME};
			productName = {EXT_NAME};
			productReference = {IDS["appex_ref"]} /* {EXT_NAME}.appex */;
			productType = "com.apple.product-type.app-extension";
		}};
"""
    return sources, resources, frameworks, target


def build_embed_phase() -> str:
    return f"""		{IDS["embed_phase"]} /* Embed App Extensions */ = {{
			isa = PBXCopyFilesBuildPhase;
			buildActionMask = 2147483647;
			dstPath = "";
			dstSubfolderSpec = 13;
			files = (
				{IDS["embed_bf"]} /* {EXT_NAME}.appex in Embed App Extensions */,
			);
			name = "Embed App Extensions";
			runOnlyForDeploymentPostprocessing = 0;
		}};
"""


def build_target_dep_and_proxy(main_uuid: str, project_uuid: str) -> str:
    return f"""		{IDS["container_proxy"]} /* PBXContainerItemProxy */ = {{
			isa = PBXContainerItemProxy;
			containerPortal = {project_uuid} /* Project object */;
			proxyType = 1;
			remoteGlobalIDString = {IDS["target"]};
			remoteInfo = {EXT_NAME};
		}};
		{IDS["tgt_dep"]} /* PBXTargetDependency */ = {{
			isa = PBXTargetDependency;
			target = {IDS["target"]} /* {EXT_NAME} */;
			targetProxy = {IDS["container_proxy"]} /* PBXContainerItemProxy */;
		}};
"""


def build_configurations(app_bundle_id: str) -> str:
    ext_bundle = f"{app_bundle_id}.{EXT_NAME}"
    common = f"""				CODE_SIGN_STYLE = Automatic;
				CURRENT_PROJECT_VERSION = 1;
				GENERATE_INFOPLIST_FILE = NO;
				INFOPLIST_FILE = {EXT_NAME}/Info.plist;
				INFOPLIST_KEY_CFBundleDisplayName = {EXT_NAME};
				INFOPLIST_KEY_NSHumanReadableCopyright = "";
				IPHONEOS_DEPLOYMENT_TARGET = 16.2;
				LD_RUNPATH_SEARCH_PATHS = (
					"$(inherited)",
					"@executable_path/Frameworks",
					"@executable_path/../../Frameworks",
				);
				MARKETING_VERSION = 1.0;
				MTL_FAST_MATH = YES;
				PRODUCT_BUNDLE_IDENTIFIER = {ext_bundle};
				PRODUCT_NAME = "$(TARGET_NAME)";
				SKIP_INSTALL = YES;
				SWIFT_EMIT_LOC_STRINGS = YES;
				SWIFT_VERSION = 5.0;
				TARGETED_DEVICE_FAMILY = "1,2";"""
    return f"""		{IDS["target_debug"]} /* Debug */ = {{
			isa = XCBuildConfiguration;
			buildSettings = {{
{common}
			}};
			name = Debug;
		}};
		{IDS["target_release"]} /* Release */ = {{
			isa = XCBuildConfiguration;
			buildSettings = {{
{common}
			}};
			name = Release;
		}};
"""


def build_cfg_list() -> str:
    return f"""		{IDS["target_cfglist"]} /* Build configuration list for PBXNativeTarget "{EXT_NAME}" */ = {{
			isa = XCConfigurationList;
			buildConfigurations = (
				{IDS["target_debug"]} /* Debug */,
				{IDS["target_release"]} /* Release */,
			);
			defaultConfigurationIsVisible = 0;
			defaultConfigurationName = Release;
		}};
"""


# ── Section insertion helper ────────────────────────────────────────────

def insert_before_end(text: str, section: str, snippet: str) -> str:
    """Insert snippet just before `/* End <section> */`."""
    marker = f"/* End {section} */"
    idx = text.find(marker)
    if idx < 0:
        # Section doesn't exist — we have to create a new section entirely.
        return _create_section(text, section, snippet)
    return text[:idx] + snippet + text[idx:]


def _create_section(text: str, section: str, snippet: str) -> str:
    """Create a brand-new /* Begin X */ ... /* End X */ block. Insert it
    just before the closing objects dict. Only used when a section doesn't
    exist yet in the pbxproj."""
    block = f"\n/* Begin {section} */\n{snippet}/* End {section} */\n"
    # Insert before the closing "};" of the objects block near the top
    # of the file. Easiest: put it right after the last existing "/* End X */".
    end_matches = list(re.finditer(r"/\* End [A-Za-z]+ section \*/", text))
    if end_matches:
        last = end_matches[-1].end()
        return text[:last] + block + text[last:]
    return text + block


# ── Main mutations ───────────────────────────────────────────────────────

def apply_all_mutations(text: str) -> str:
    if EXT_NAME in text and IDS["target"] in text:
        print(f"[skip-most] {EXT_NAME} target already present — running only "
              f"idempotent post-checks (register in project.targets, bump deployment)")
        # Even if target exists, still ensure it's registered in PBXProject.targets
        # and deployment bump is applied (they have their own idempotency).
        text = _register_target_in_project(text, find_project_uuid(text))
        text = _ensure_deployment_bump(text)
        return text

    project_uuid = find_project_uuid(text)
    main_uuid    = find_main_target_uuid(text)
    root_group   = find_root_group_uuid(text)
    products_grp = find_products_group_uuid(text)
    app_group    = find_app_group_uuid(text)
    app_sources  = find_app_sources_phase(text)
    app_bundle   = find_app_bundle_id(text)

    print(f"[info] project={project_uuid} app_target={main_uuid} root={root_group}")
    print(f"[info] products_group={products_grp} app_group={app_group}")
    print(f"[info] app_sources_phase={app_sources} bundle={app_bundle}")
    if not all([project_uuid, main_uuid, root_group, products_grp, app_group, app_sources]):
        raise RuntimeError("could not locate all required UUIDs in pbxproj")

    # 1. PBXBuildFile — add all our build files
    text = insert_before_end(text, "PBXBuildFile section", build_pbxbuildfile_entries())

    # 2. PBXFileReference — file refs
    text = insert_before_end(text, "PBXFileReference section", build_pbxfilereference_entries())

    # 3. Add router to App group children + LiveActivityWidget group to root
    text = _add_router_to_app_group(text, app_group)
    text = _add_appex_to_products(text, products_grp)
    text = _add_ext_group_to_root(text, root_group)
    text = insert_before_end(text, "PBXGroup section", build_pbxgroup_ext(text))

    # 4. PBXNativeTarget
    sources, resources, frameworks, target = build_target_and_phases(text)
    text = insert_before_end(text, "PBXNativeTarget section", target)

    # 5. Build phases (Sources, Resources, Frameworks, CopyFiles)
    text = insert_before_end(text, "PBXSourcesBuildPhase section", sources)
    text = insert_before_end(text, "PBXResourcesBuildPhase section", resources)
    text = insert_before_end(text, "PBXFrameworksBuildPhase section", frameworks)
    text = insert_before_end(text, "PBXCopyFilesBuildPhase section", build_embed_phase())

    # 6. TargetDependency + ContainerProxy
    dep_and_proxy = build_target_dep_and_proxy(main_uuid, project_uuid)
    # Split by section
    proxy_snip = re.search(r"(\s*[0-9A-F]{24} /\* PBXContainerItemProxy \*/ = \{[^}]+\};\n)", dep_and_proxy).group(1)
    dep_snip   = re.search(r"(\s*[0-9A-F]{24} /\* PBXTargetDependency \*/ = \{[^}]+\};\n)", dep_and_proxy).group(1)
    text = insert_before_end(text, "PBXContainerItemProxy section", proxy_snip)
    text = insert_before_end(text, "PBXTargetDependency section", dep_snip)

    # 7. Add router source to main App target's Sources phase
    text = _add_router_to_app_sources(text, app_sources)

    # 8. Add copy-files phase to main App target's buildPhases (embedding)
    text = _add_embed_phase_to_app(text, main_uuid)
    text = _add_target_dependency_to_app(text, main_uuid)

    # 9. Register the target in PBXProject.targets + TargetAttributes
    text = _register_target_in_project(text, project_uuid)

    # 10. Add XCBuildConfiguration + XCConfigurationList for the widget
    text = insert_before_end(text, "XCBuildConfiguration section", build_configurations(app_bundle))
    text = insert_before_end(text, "XCConfigurationList section", build_cfg_list())

    # 11. Bump main App target deployment to 16.2
    text = _ensure_deployment_bump(text)

    return text


def _add_router_to_app_group(text: str, app_group_uuid: str) -> str:
    """Add LiveActivityRouter.swift to the App/ group children."""
    router_line = f"				{IDS['router_ref']} /* LiveActivityRouter.swift */,\n"
    pattern = rf"({app_group_uuid} /\* App \*/ = \{{\s*isa = PBXGroup;\s*children = \(\s*\n)"
    return re.sub(pattern, r"\1" + router_line, text, count=1)


def _add_appex_to_products(text: str, products_uuid: str) -> str:
    appex_line = f"				{IDS['appex_ref']} /* {EXT_NAME}.appex */,\n"
    pattern = rf"({products_uuid} /\* Products \*/ = \{{\s*isa = PBXGroup;\s*children = \(\s*\n)"
    return re.sub(pattern, r"\1" + appex_line, text, count=1)


def _add_ext_group_to_root(text: str, root_uuid: str) -> str:
    ext_line = f"				{IDS['ext_group']} /* {EXT_NAME} */,\n"
    pattern = rf"({root_uuid} = \{{\s*isa = PBXGroup;\s*children = \(\s*\n)"
    return re.sub(pattern, r"\1" + ext_line, text, count=1)


def _add_router_to_app_sources(text: str, sources_phase_uuid: str) -> str:
    """Add LiveActivityRouter.swift + LiveActivityAttributes.swift to the App
    target's Sources phase so the main app can use them too."""
    lines = (
        f"				{IDS['router_bf']} /* LiveActivityRouter.swift in Sources */,\n"
        f"				{IDS['attrs_bf_app']} /* LiveActivityAttributes.swift in Sources */,\n"
    )
    pattern = rf"({sources_phase_uuid} /\* Sources \*/ = \{{\s*isa = PBXSourcesBuildPhase;\s*buildActionMask = 2147483647;\s*files = \(\s*\n)"
    return re.sub(pattern, r"\1" + lines, text, count=1)


def _add_embed_phase_to_app(text: str, main_uuid: str) -> str:
    """Append embed_phase UUID to the App target's buildPhases list."""
    embed_line = f"				{IDS['embed_phase']} /* Embed App Extensions */,\n"
    pattern = rf"({main_uuid} /\* App \*/ = \{{[^}}]+?buildPhases = \(\s*\n)"
    return re.sub(pattern, r"\1" + embed_line, text, count=1, flags=re.DOTALL)


def _add_target_dependency_to_app(text: str, main_uuid: str) -> str:
    dep_line = f"				{IDS['tgt_dep']} /* PBXTargetDependency */,\n"
    pattern = rf"({main_uuid} /\* App \*/ = \{{[^}}]+?dependencies = \(\s*\n)"
    return re.sub(pattern, r"\1" + dep_line, text, count=1, flags=re.DOTALL)


def _register_target_in_project(text: str, project_uuid: str) -> str:
    """Insert the widget target UUID into PBXProject.targets. The naive
    `[^}]+?` regex fails because the Project block has nested `{}` in
    its `attributes = { TargetAttributes = { … } }` sub-dict — the lazy
    match stops at the first closing brace inside `attributes`. Since
    there's exactly ONE `targets = (` in the whole pbxproj (the PBXProject's),
    we just target that unique marker without needing to match the enclosing
    block. Idempotent — no-op if the widget UUID is already listed."""
    target_line = f"				{IDS['target']} /* {EXT_NAME} */,\n"
    # If already present, don't duplicate.
    if IDS['target'] in text.split("targets = (", 1)[1].split(");", 1)[0]:
        return text
    return re.sub(
        r"(targets = \(\s*\n)",
        r"\1" + target_line,
        text, count=1,
    )


def _ensure_deployment_bump(text: str) -> str:
    """Bump every IPHONEOS_DEPLOYMENT_TARGET < 16.2 to 16.2 for ActivityKit."""
    def repl(m):
        val = m.group(1).strip()
        try:
            if float(val) < 16.2:
                return "IPHONEOS_DEPLOYMENT_TARGET = 16.2;"
        except ValueError:
            pass
        return m.group(0)
    return re.sub(r"IPHONEOS_DEPLOYMENT_TARGET = ([0-9.]+);", repl, text)


# ── Also ensure sections that don't exist yet get created ───────────────

def _ensure_empty_section(text: str, section: str) -> str:
    """Create /* Begin X */ ... /* End X */ if not present. Empty body."""
    if f"/* Begin {section} */" in text:
        return text
    block = f"\n/* Begin {section} */\n/* End {section} */\n"
    end_matches = list(re.finditer(r"/\* End [A-Za-z]+ section \*/", text))
    if end_matches:
        last = end_matches[-1].end()
        return text[:last] + block + text[last:]
    return text + block


def _patch_info_plist() -> None:
    """Ensure the main App's Info.plist has:
      - NSSupportsLiveActivities
      - CFBundleURLTypes with the `applicationclaude` scheme

    Capacitor sync sometimes rewrites Info.plist to add plugin keys, so we
    re-apply these after every sync to be safe. Idempotent."""
    import plistlib
    p = REPO / "ios" / "App" / "App" / "Info.plist"
    if not p.exists():
        print(f"[warn] Info.plist not found at {p}", file=sys.stderr)
        return
    plist = plistlib.loads(p.read_bytes())
    changed = False
    if plist.get("NSSupportsLiveActivities") is not True:
        plist["NSSupportsLiveActivities"] = True
        changed = True
    if plist.get("NSSupportsLiveActivitiesFrequentUpdates") is not True:
        plist["NSSupportsLiveActivitiesFrequentUpdates"] = True
        changed = True
    url_types = plist.get("CFBundleURLTypes") or []
    has_scheme = any(
        "applicationclaude" in (u.get("CFBundleURLSchemes") or [])
        for u in url_types
    )
    if not has_scheme:
        url_types.append({
            "CFBundleTypeRole": "Editor",
            "CFBundleURLName": "app.claude.applicationclaude.la",
            "CFBundleURLSchemes": ["applicationclaude"],
        })
        plist["CFBundleURLTypes"] = url_types
        changed = True
    if changed:
        p.write_bytes(plistlib.dumps(plist, sort_keys=False))
        print(f"[ok] patched Info.plist (NSSupportsLiveActivities + URL scheme)")
    else:
        print(f"[skip] Info.plist already has LA keys + URL scheme")


def main() -> int:
    if not PBXPROJ.exists():
        print(f"ERROR: pbxproj not found at {PBXPROJ}", file=sys.stderr)
        return 1

    # 1. Patch Info.plist first (independent of pbxproj)
    _patch_info_plist()

    # 2. Patch pbxproj
    text = PBXPROJ.read_text(encoding="utf-8")
    # Pre-create the sections that may not exist in a fresh Capacitor pbxproj:
    #  - PBXContainerItemProxy, PBXTargetDependency, PBXCopyFilesBuildPhase
    for s in ("PBXContainerItemProxy section",
              "PBXTargetDependency section",
              "PBXCopyFilesBuildPhase section"):
        text = _ensure_empty_section(text, s)

    text = apply_all_mutations(text)
    PBXPROJ.write_text(text, encoding="utf-8")
    print(f"[done] wrote {PBXPROJ}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
