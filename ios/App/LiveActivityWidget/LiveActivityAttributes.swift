// LiveActivityAttributes.swift
// Universal Live Activity payload — same shape for every use case (deposit,
// delivery, upload, workout, etc.). The main app fills fixed fields once at
// start, then pushes ContentState updates to advance progress / change text.
//
// Kept intentionally string-heavy so the whole thing can be marshalled
// from a URL query string (dashboard :9042 pushes via URL scheme).

import ActivityKit
import Foundation

@available(iOS 16.2, *)
public struct UniversalActivityAttributes: ActivityAttributes {
    // ContentState = the parts iOS lets us update after start.
    public struct ContentState: Codable, Hashable {
        // Main headline shown big (e.g. "468.483547 USDC")
        public var value: String
        // Secondary line under the value (e.g. "Processing in 2 mins")
        public var subtitle: String
        // Step index: 0 = only step-1 lit, 1 = step-1+2 lit, 2 = all lit.
        // -1 means no progress row (single value display).
        public var stepIndex: Int
        // Optional custom hex color for the accent (default = yellow like Binance)
        public var accentHex: String
        // Optional right-column label (e.g. "Deposit", "Delivery", "Upload")
        public var kind: String

        public init(value: String, subtitle: String, stepIndex: Int = 1,
                    accentHex: String = "#F0B90B", kind: String = "") {
            self.value = value
            self.subtitle = subtitle
            self.stepIndex = stepIndex
            self.accentHex = accentHex
            self.kind = kind
        }
    }

    // Fixed part — set once when the activity starts.
    // Brand shown top-left ("Binance", "PayPal", "Amazon", "DHL", etc.)
    public var brand: String
    // Optional emoji or single character used as brand icon glyph
    public var glyph: String
    // Labels for the 3 progress steps (e.g. "Confirmed", "Processing", "Credited")
    public var step1Label: String
    public var step2Label: String
    public var step3Label: String

    public init(brand: String, glyph: String = "◆",
                step1Label: String = "Confirmed",
                step2Label: String = "Processing",
                step3Label: String = "Credited") {
        self.brand = brand
        self.glyph = glyph
        self.step1Label = step1Label
        self.step2Label = step2Label
        self.step3Label = step3Label
    }
}
