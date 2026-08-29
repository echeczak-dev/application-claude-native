import UIKit
import WebKit
import Capacitor

// Custom ViewController that forces the WKWebView to extend behind the
// physical screen edges (notch + home indicator). CAPBridgeViewController
// keeps its own status-bar/home-indicator overrides (declared non-open),
// so we act on the webView + safeAreaInsets instead.
class MainViewController: CAPBridgeViewController {

    // Hook after Capacitor built its own userContentController but BEFORE
    // loadWebView() fires the initial URL request. This is the earliest
    // safe point to add a WKUserScript that will actually be honored
    // (webViewConfiguration override doesn't work: Capacitor overwrites
    // userContentController in prepareWebView after we return).
    override func capacitorDidLoad() {
        super.capacitorDidLoad()
        guard let controller = webView?.configuration.userContentController else { return }

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
            + "html.native-app #img{object-fit:cover !important;object-position:center center !important;position:fixed !important;top:0 !important;left:0 !important;width:100vw !important;height:100vh !important;height:100dvh !important;}';"
            + "(document.head||document.documentElement).appendChild(s);"
            + "function tryHideBars(){"
            + "  if(window.Capacitor&&window.Capacitor.Plugins&&window.Capacitor.Plugins.SystemBars){"
            + "    try{window.Capacitor.Plugins.SystemBars.hide({});}catch(e){}"
            + "  }else{setTimeout(tryHideBars,50);}"
            + "}"
            + "tryHideBars();"
            + "})();"
        let userScript = WKUserScript(source: js, injectionTime: .atDocumentStart, forMainFrameOnly: true)
        controller.addUserScript(userScript)
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

    // Defer bottom + top edge swipes so a first swipe only wakes UI instead of
    // triggering system gestures (home indicator swipe / notif center).
    // (prefersHomeIndicatorAutoHidden is handled via the SystemBars plugin JS
    // call in the WKUserScript above — Capacitor declares it non-open in its
    // SystemBars extension so we can't override it in Swift.)
    override var preferredScreenEdgesDeferringSystemGestures: UIRectEdge {
        return [.bottom, .top]
    }
}
