import SwiftUI

@main
struct SquintApp: App {
    @State private var store = AppStore()

    var body: some Scene {
        WindowGroup {
            RootView()
                .environment(store)
                .tint(Theme.accent)
        }
    }
}

struct RootView: View {
    @Environment(AppStore.self) private var store

    var body: some View {
        Group {
            if store.onboarded {
                TabView {
                    TodayView().tabItem { Label("Today", systemImage: "sun.max") }
                    MedicationsView().tabItem { Label("Medications", systemImage: "pills") }
                    SettingsView().tabItem { Label("Settings", systemImage: "gearshape") }
                }
            } else {
                OnboardingView()
            }
        }
        .task { await store.refresh() }
    }
}
