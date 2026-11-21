import Foundation

/// The settings the app, its widget and Siri all need (demo or live, and where the station is).
/// They live in the App Group so the widget extension, a separate process, can read them.
nonisolated enum SquintSettings {
    static let appGroup = "group.com.hackwestern.squint"
    static let defaultBackend = "http://172.20.10.9:8081"
    static let defaultHome = "http://192.168.1.10:8765"

    /// The shared defaults. Without the App Group entitlement this quietly falls back to the
    /// app's own defaults: the app still works, the widget just sees demo data.
    static let defaults: UserDefaults = {
        let d = UserDefaults(suiteName: appGroup) ?? .standard
        migrate(into: d)
        return d
    }()

    static var useDemoData: Bool {
        get { defaults.object(forKey: "useDemoData") as? Bool ?? true }
        set { defaults.set(newValue, forKey: "useDemoData") }
    }
    static var backendURL: String {
        get { defaults.string(forKey: "backendURL") ?? defaultBackend }
        set { defaults.set(newValue, forKey: "backendURL") }
    }
    static var homeURL: String {
        get { defaults.string(forKey: "homeURL") ?? defaultHome }
        set { defaults.set(newValue, forKey: "homeURL") }
    }
    static var onboarded: Bool {
        get { defaults.bool(forKey: "onboarded") }
        set { defaults.set(newValue, forKey: "onboarded") }
    }

    /// The station, or the demo data, as the settings say.
    static var api: SquintAPI {
        if !useDemoData, let url = URL(string: backendURL) { return LiveAPI(base: url) }
        return MockAPI.shared
    }

    /// Settings saved before the App Group existed were in the app's own defaults: copy them once.
    private static func migrate(into d: UserDefaults) {
        guard d !== UserDefaults.standard, !d.bool(forKey: "migrated") else { return }
        for key in ["useDemoData", "backendURL", "homeURL", "onboarded"] {
            if d.object(forKey: key) == nil, let v = UserDefaults.standard.object(forKey: key) {
                d.set(v, forKey: key)
            }
        }
        d.set(true, forKey: "migrated")
    }
}
