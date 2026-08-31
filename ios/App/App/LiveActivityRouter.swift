// LiveActivityRouter.swift
// URL-scheme entrypoint for the Live Activity system.
//
// Dashboard :9042 pushes activities by opening URLs like:
//
//   applicationclaude://la/start?brand=Binance&glyph=◆&kind=Deposit&value=468.483547%20USDC&subtitle=Processing%20in%202%20mins&step=1&color=%23F0B90B
//   applicationclaude://la/update?value=468.483547%20USDC&subtitle=Credited&step=2
//   applicationclaude://la/stop
//
// iOS opens the app briefly (200-500 ms), we catch the URL in SceneDelegate,
// dispatch here, and ActivityKit starts / updates / ends the Live Activity
// which persists on the lock screen after the app closes again (up to 8h).
//
// The "single active activity" model: we track one activity ID at a time.
// A second /start replaces the first. This keeps the flow simple.

import Foundation
#if canImport(ActivityKit)
import ActivityKit
#endif

@available(iOS 16.2, *)
final class LiveActivityRouter {
    static let shared = LiveActivityRouter()

    // Track the currently-live activity so /update can address it and /stop
    // can end it cleanly.
    private var activeActivity: Activity<UniversalActivityAttributes>?

    /// Parse an incoming applicationclaude://la/... URL and dispatch.
    /// Returns true if the URL was handled (path matched /la/*).
    @discardableResult
    func handle(url: URL) -> Bool {
        guard url.host == "la" else { return false }
        let action = url.path.trimmingCharacters(in: CharacterSet(charactersIn: "/"))
        let params = queryDict(url: url)
        switch action {
        case "start":  startActivity(params: params); return true
        case "update": updateActivity(params: params); return true
        case "stop":   stopActivity(params: params); return true
        default:
            NSLog("[LA] unknown action '\(action)'")
            return false
        }
    }

    // MARK: - Actions

    private func startActivity(params: [String: String]) {
        // End any previous activity so we don't stack up.
        if let a = activeActivity {
            Task { await a.end(nil, dismissalPolicy: .immediate) }
            activeActivity = nil
        }
        // We deliberately DO NOT gate on ActivityAuthorizationInfo here:
        // on a fresh install iOS hasn't formed an opinion yet (the flag can
        // be false even though Activity.request() would succeed and trigger
        // the system-level "Allow" prompt). Instead we try the request and
        // log any thrown error so we can diagnose from the on-device debug log.
        _debugLog("start params=\(params)")
        _debugLog("areActivitiesEnabled=\(ActivityAuthorizationInfo().areActivitiesEnabled)")
        let attrs = UniversalActivityAttributes(
            brand: params["brand"] ?? "Application Claude",
            glyph: params["glyph"] ?? "◆",
            step1Label: params["s1"] ?? "Confirmed",
            step2Label: params["s2"] ?? "Processing",
            step3Label: params["s3"] ?? "Credited"
        )
        let state = UniversalActivityAttributes.ContentState(
            value:    params["value"] ?? "",
            subtitle: params["subtitle"] ?? "",
            stepIndex: Int(params["step"] ?? "1") ?? 1,
            accentHex: params["color"] ?? "#F0B90B",
            kind:      params["kind"] ?? ""
        )
        do {
            let content = ActivityContent(state: state, staleDate: nil)
            let activity = try Activity.request(
                attributes: attrs,
                content: content,
                pushType: nil     // local-only, no APNs push token needed
            )
            activeActivity = activity
            _debugLog("started activity id=\(activity.id) brand=\(attrs.brand)")
        } catch {
            _debugLog("start FAILED: \(type(of: error))=\(error) desc=\(error.localizedDescription)")
        }
    }

    // MARK: - Debug log to Documents/la_debug.log (last 200 lines).
    // The dashboard can pull this file via `pymobiledevice3 apps pull` to
    // see what happened after each firing attempt.
    private func _debugLog(_ msg: String) {
        NSLog("[LA] \(msg)")
        guard let docs = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask).first else { return }
        let f = docs.appendingPathComponent("la_debug.log")
        let ts = ISO8601DateFormatter().string(from: Date())
        let line = "[\(ts)] \(msg)\n"
        if let handle = try? FileHandle(forWritingTo: f) {
            handle.seekToEndOfFile()
            if let data = line.data(using: .utf8) { handle.write(data) }
            handle.closeFile()
        } else {
            try? line.write(to: f, atomically: true, encoding: .utf8)
        }
    }

    private func updateActivity(params: [String: String]) {
        guard let activity = activeActivity else {
            // No active activity — treat update like a fresh start so a URL
            // fired mid-flow "just works" instead of silently dropping.
            NSLog("[LA] no active activity, promoting update -> start")
            startActivity(params: params); return
        }
        let current = activity.content.state
        let state = UniversalActivityAttributes.ContentState(
            value:     params["value"]    ?? current.value,
            subtitle:  params["subtitle"] ?? current.subtitle,
            stepIndex: Int(params["step"] ?? "\(current.stepIndex)") ?? current.stepIndex,
            accentHex: params["color"]    ?? current.accentHex,
            kind:      params["kind"]     ?? current.kind
        )
        Task {
            let content = ActivityContent(state: state, staleDate: nil)
            await activity.update(content)
            NSLog("[LA] updated activity id=\(activity.id) step=\(state.stepIndex)")
        }
    }

    private func stopActivity(params: [String: String]) {
        guard let activity = activeActivity else { return }
        let dismiss: ActivityUIDismissalPolicy = (params["dismiss"] == "immediate")
            ? .immediate : .default
        Task {
            await activity.end(nil, dismissalPolicy: dismiss)
            NSLog("[LA] stopped activity id=\(activity.id)")
        }
        activeActivity = nil
    }

    // MARK: - Helpers
    private func queryDict(url: URL) -> [String: String] {
        var out: [String: String] = [:]
        guard let comps = URLComponents(url: url, resolvingAgainstBaseURL: false) else { return out }
        for item in comps.queryItems ?? [] {
            out[item.name] = item.value ?? ""
        }
        return out
    }
}
