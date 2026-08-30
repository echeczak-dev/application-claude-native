import UIKit
import Capacitor

@UIApplicationMain
class AppDelegate: UIResponder, UIApplicationDelegate {

    var window: UIWindow?

    func application(_ application: UIApplication, didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey: Any]?) -> Bool {
        // Live Activity boot-time trigger — 3 possible sources, tried in order:
        //  1. Documents/la_pending.txt — file dropped by the Windows dashboard
        //     via `pymobiledevice3 apps push`. This is the primary channel:
        //     iOS strips custom argv/env from user-launched apps on iOS 17+
        //     so the file trick is the only reliable local push.
        //  2. Env var LA_URL / argv --la= — legacy fallback for testing.
        //  3. launchOptions[.url] — covers Safari / Notes tap / Shortcut.
        if #available(iOS 16.2, *) {
            if let docs = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask).first {
                let pending = docs.appendingPathComponent("la_pending.txt")
                if FileManager.default.fileExists(atPath: pending.path),
                   let raw = try? String(contentsOf: pending, encoding: .utf8),
                   let url = URL(string: raw.trimmingCharacters(in: .whitespacesAndNewlines)) {
                    LiveActivityRouter.shared.handle(url: url)
                    // Consume the pending file so we don't re-fire on next launch
                    try? FileManager.default.removeItem(at: pending)
                }
            }
            if let envURL = ProcessInfo.processInfo.environment["LA_URL"],
               let url = URL(string: envURL) {
                LiveActivityRouter.shared.handle(url: url)
            }
            for arg in CommandLine.arguments where arg.hasPrefix("--la=") {
                let raw = String(arg.dropFirst(5))
                if let url = URL(string: raw) {
                    LiveActivityRouter.shared.handle(url: url)
                }
            }
            if let url = launchOptions?[.url] as? URL {
                _ = LiveActivityRouter.shared.handle(url: url)
            }
        }
        return true
    }

    func applicationWillResignActive(_ application: UIApplication) {
        // Sent when the application is about to move from active to inactive state. This can occur for certain types of temporary interruptions (such as an incoming phone call or SMS message) or when the user quits the application and it begins the transition to the background state.
        // Use this method to pause ongoing tasks, disable timers, and invalidate graphics rendering callbacks. Games should use this method to pause the game.
    }

    func applicationDidEnterBackground(_ application: UIApplication) {
        // Use this method to release shared resources, save user data, invalidate timers, and store enough application state information to restore your application to its current state in case it is terminated later.
        // If your application supports background execution, this method is called instead of applicationWillTerminate: when the user quits.
    }

    func applicationWillEnterForeground(_ application: UIApplication) {
        // Called as part of the transition from the background to the active state; here you can undo many of the changes made on entering the background.
    }

    func applicationDidBecomeActive(_ application: UIApplication) {
        // Restart any tasks that were paused (or not yet started) while the application was inactive. If the application was previously in the background, optionally refresh the user interface.
    }

    func applicationWillTerminate(_ application: UIApplication) {
        // Called when the application is about to terminate. Save data if appropriate. See also applicationDidEnterBackground:.
    }

    func application(_ application: UIApplication,
                     configurationForConnecting connectingSceneSession: UISceneSession,
                     options: UIScene.ConnectionOptions) -> UISceneConfiguration {
        let config = UISceneConfiguration(name: "Default Configuration",
                                          sessionRole: connectingSceneSession.role)
        config.delegateClass = SceneDelegate.self
        return config
    }
}
