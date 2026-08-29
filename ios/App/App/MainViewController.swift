import UIKit
import WebKit
import Capacitor

// Custom ViewController that forces the WKWebView to extend behind the
// physical screen edges (notch + home indicator). CAPBridgeViewController
// keeps its own status-bar/home-indicator overrides (declared non-open),
// so we act on the webView + safeAreaInsets instead.
class MainViewController: CAPBridgeViewController {

    // Local www/index.html is baked into the .ipa — no WKUserScript override
    // needed since we control 100% of the HTML/CSS/JS that renders.

    override func viewDidLoad() {
        super.viewDidLoad()
        view.backgroundColor = .black

        if let webView = self.webView {
            webView.backgroundColor = .black
            webView.isOpaque = true
            webView.scrollView.backgroundColor = .black
            webView.scrollView.contentInsetAdjustmentBehavior = .never
            webView.scrollView.isScrollEnabled = false
            webView.scrollView.bounces = false
            if #available(iOS 13.0, *) {
                webView.scrollView.automaticallyAdjustsScrollIndicatorInsets = false
            }
        }
    }

    override func viewSafeAreaInsetsDidChange() {
        super.viewSafeAreaInsetsDidChange()
        // Cancel all safe-area padding: web content fills the physical screen
        // (notch + home indicator drawn on top of the webview).
        additionalSafeAreaInsets = UIEdgeInsets(
            top: -view.safeAreaInsets.top,
            left: -view.safeAreaInsets.left,
            bottom: -view.safeAreaInsets.bottom,
            right: -view.safeAreaInsets.right
        )
    }

    // Defer bottom + top edge swipes so a first swipe only wakes UI instead of
    // triggering system gestures (home indicator swipe / notif center).
    // (prefersHomeIndicatorAutoHidden is handled via the SystemBars plugin JS
    // call in the WKUserScript above — Capacitor declares it non-open in its
    // SystemBars extension so we can't override it in Swift.)
    override var preferredScreenEdgesDeferringSystemGestures: UIRectEdge {
        return [.bottom, .top]
    }
}
