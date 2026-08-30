// LiveActivityWidgetBundle.swift
// Widget extension entry point — WidgetKit auto-discovers widgets exported
// from a WidgetBundle. We only ship one widget: the universal Live Activity.

import SwiftUI
import WidgetKit

@main
@available(iOS 16.2, *)
struct LiveActivityWidgetBundle: WidgetBundle {
    var body: some Widget {
        LiveActivityWidget()
    }
}
