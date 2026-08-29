import UIKit
import WebKit
import Capacitor

// Custom ViewController that forces the WKWebView to extend behind the
// physical screen edges (notch + home indicator). CAPBridgeViewController
// keeps its own status-bar/home-indicator overrides (declared non-open),
// so we act on the webView + safeAreaInsets instead.
class MainViewController: CAPBridgeViewController {

    // Inject at documentStart so the CSS rules kill the Safari-only
    // fullscreen video hack + notif button BEFORE the PWA renders them.
    // Kept in Swift so the native wrapper is independent of the PWA deploy state.
    override func webViewConfiguration(for instanceConfiguration: InstanceConfiguration) -> WKWebViewConfiguration {
        let config = super.webViewConfiguration(for: instanceConfiguration)
        // JS injects a style tag + a class on <html>. The style hides the Safari
        // fullscreen hack (fsBtn, fsVideo) + notif button, and makes #img cover
        // the entire physical viewport (which now goes edge-to-edge thanks to
        // negative safeAreaInsets in viewSafeAreaInsetsDidChange).
        let js = "(function(){"
            + "document.documentElement.classList.add('native-app');"
            + "var s=document.createElement('style');"
            + "s.setAttribute('data-native-override','1');"
            + "s.textContent='html.native-app #fsBtn,html.native-app #fsVideo,html.native-app #notifBtn{display:none !important;}"
            + "html.native-app,html.native-app body{background:#000 !important;overflow:hidden !important;}"
            + "html.native-app #img{object-fit:cover !important;object-position:center center !important;}';"
            + "(document.head||document.documentElement).appendChild(s);"
            + "})();"
        let userScript = WKUserScript(source: js, injectionTime: .atDocumentStart, forMainFrameOnly: true)
        config.userContentController.addUserScript(userScript)
        return config
    }

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

    // Auto-dim the home indicator bar after brief inactivity.
    override var prefersHomeIndicatorAutoHidden: Bool {
        return true
    }

    // Defer the bottom edge swipe so a first swipe just wakes UI instead of
    // dismissing the app — the physical bar becomes practically invisible.
    override var preferredScreenEdgesDeferringSystemGestures: UIRectEdge {
        return [.bottom, .top]
    }
}
