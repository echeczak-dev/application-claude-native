// LiveActivityView.swift
// SwiftUI rendering for the universal Live Activity — mirrors the layout of
// the Binance deposit widget the user screenshotted:
//
//   ┌────────────────────────────────────────────┐
//   │ ◆ BINANCE                          Deposit │
//   │                                            │
//   │ 468.483547 USDC                            │
//   │ Processing in 2 mins                       │
//   │                                            │
//   │ ●────────●────────○                        │
//   │ Confirmed  Processing  Credited            │
//   └────────────────────────────────────────────┘
//
// All strings + step index + accent color come from ContentState so a single
// widget can render any workflow the dashboard pushes.

import ActivityKit
import SwiftUI
import WidgetKit

@available(iOS 16.2, *)
public struct LiveActivityWidget: Widget {
    public init() {}

    public var body: some WidgetConfiguration {
        ActivityConfiguration(for: UniversalActivityAttributes.self) { context in
            // ── Lock screen / banner presentation ─────────────────────────
            LiveActivityLockScreenView(
                attributes: context.attributes,
                state: context.state
            )
            .activityBackgroundTint(.black)
            .activitySystemActionForegroundColor(.white)
        } dynamicIsland: { context in
            // ── Dynamic Island (iPhone 14 Pro+) ───────────────────────────
            DynamicIsland {
                DynamicIslandExpandedRegion(.leading) {
                    Text(context.attributes.glyph)
                        .font(.title2)
                        .foregroundColor(Color(hex: context.state.accentHex))
                }
                DynamicIslandExpandedRegion(.trailing) {
                    Text(context.state.kind)
                        .font(.caption)
                        .foregroundColor(.gray)
                }
                DynamicIslandExpandedRegion(.center) {
                    Text(context.attributes.brand)
                        .font(.headline)
                        .foregroundColor(Color(hex: context.state.accentHex))
                }
                DynamicIslandExpandedRegion(.bottom) {
                    VStack(spacing: 6) {
                        Text(context.state.value)
                            .font(.title2)
                            .bold()
                            .foregroundColor(.white)
                        Text(context.state.subtitle)
                            .font(.caption)
                            .foregroundColor(.gray)
                        if context.state.stepIndex >= 0 {
                            ProgressStrip(
                                stepIndex: context.state.stepIndex,
                                accent: Color(hex: context.state.accentHex),
                                labels: [context.attributes.step1Label,
                                         context.attributes.step2Label,
                                         context.attributes.step3Label]
                            )
                        }
                    }
                    .frame(maxWidth: .infinity)
                }
            } compactLeading: {
                Text(context.attributes.glyph)
                    .foregroundColor(Color(hex: context.state.accentHex))
            } compactTrailing: {
                Text(context.state.value.prefix(8))
                    .font(.caption2.monospacedDigit())
                    .foregroundColor(.white)
            } minimal: {
                Text(context.attributes.glyph)
                    .foregroundColor(Color(hex: context.state.accentHex))
            }
        }
    }
}

// ── Lock screen row ─────────────────────────────────────────────────────
@available(iOS 16.2, *)
struct LiveActivityLockScreenView: View {
    let attributes: UniversalActivityAttributes
    let state: UniversalActivityAttributes.ContentState

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            // Top row: brand (accent-colored) on the left, "kind" tag on the right
            HStack {
                Text(attributes.glyph)
                    .font(.title3)
                    .foregroundColor(Color(hex: state.accentHex))
                Text(attributes.brand.uppercased())
                    .font(.subheadline.bold())
                    .foregroundColor(Color(hex: state.accentHex))
                Spacer()
                Text(state.kind)
                    .font(.subheadline)
                    .foregroundColor(.white)
            }

            // Main value + subtitle
            VStack(alignment: .leading, spacing: 2) {
                Text(state.value)
                    .font(.title2)
                    .bold()
                    .foregroundColor(.white)
                Text(state.subtitle)
                    .font(.subheadline)
                    .foregroundColor(.gray)
            }

            // Optional 3-step progress
            if state.stepIndex >= 0 {
                ProgressStrip(
                    stepIndex: state.stepIndex,
                    accent: Color(hex: state.accentHex),
                    labels: [attributes.step1Label,
                             attributes.step2Label,
                             attributes.step3Label]
                )
            }
        }
        .padding(16)
    }
}

// ── 3-step progress strip: ●──●──○ layout ───────────────────────────────
@available(iOS 16.2, *)
struct ProgressStrip: View {
    let stepIndex: Int
    let accent: Color
    let labels: [String]

    var body: some View {
        VStack(spacing: 6) {
            HStack(spacing: 0) {
                stepDot(index: 0)
                connector(active: stepIndex >= 1)
                stepDot(index: 1)
                connector(active: stepIndex >= 2)
                stepDot(index: 2)
            }
            HStack {
                ForEach(0..<3, id: \.self) { i in
                    Text(labels[i])
                        .font(.caption2)
                        .foregroundColor(i <= stepIndex ? .white : .gray)
                        .frame(maxWidth: .infinity)
                }
            }
        }
    }

    @ViewBuilder
    private func stepDot(index: Int) -> some View {
        let active = index <= stepIndex
        ZStack {
            Circle()
                .fill(active ? accent : Color.gray.opacity(0.3))
                .frame(width: 18, height: 18)
            if active {
                Image(systemName: "checkmark")
                    .font(.system(size: 10, weight: .bold))
                    .foregroundColor(.black)
            }
        }
    }

    @ViewBuilder
    private func connector(active: Bool) -> some View {
        Rectangle()
            .fill(active ? accent : Color.gray.opacity(0.3))
            .frame(height: 2)
    }
}

// ── Hex color helper ─────────────────────────────────────────────────────
extension Color {
    init(hex: String) {
        let s = hex.trimmingCharacters(in: CharacterSet(charactersIn: "# "))
        var val: UInt64 = 0
        Scanner(string: s).scanHexInt64(&val)
        let r = Double((val >> 16) & 0xFF) / 255.0
        let g = Double((val >> 8) & 0xFF) / 255.0
        let b = Double(val & 0xFF) / 255.0
        self = Color(red: r, green: g, blue: b)
    }
}
