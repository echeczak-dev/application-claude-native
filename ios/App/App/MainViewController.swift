import UIKit
import Capacitor

// Custom ViewController that forces TRUE fullscreen on iOS.
// - Hides status bar entirely
// - Hides home indicator (auto-hides after 3s inactivity)
// - Sets WKWebView to ignore safe areas → draws behind notch + home indicator
// - Sets background to black to match PWA
class MainViewController: CAPBridgeViewController {

    override var prefersStatusBarHidden: Bool {
        return true
    }

    override var prefersHomeIndicatorAutoHidden: Bool {
        return true
    }

    override var preferredScreenEdgesDeferringSystemGestures: UIRectEdge {
        return .all
    }

    override func viewDidLoad() {
        super.viewDidLoad()
        view.backgroundColor = .black

        // Force WKWebView to extend behind safe areas (notch + home indicator)
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
        // Ignore all safe area insets: WKWebView fills the physical screen
        additionalSafeAreaInsets = UIEdgeInsets(
            top: -view.safeAreaInsets.top,
            left: -view.safeAreaInsets.left,
            bottom: -view.safeAreaInsets.bottom,
            right: -view.safeAreaInsets.right
        )
    }
}
