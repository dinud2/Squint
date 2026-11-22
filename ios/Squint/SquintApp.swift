import BackgroundTasks
import SwiftUI

@main
struct SquintApp: App {
    @State private var store = AppStore()
    @Environment(\.scenePhase) private var phase
    nonisolated static let refreshTask = "com.hackwestern.squint.refresh"

    init() { Notifier.shared.start() }

    var body: some Scene {
        WindowGroup {
            RootView()
                .environment(store)
                .tint(Theme.accent)
                .fontDesign(.rounded)
        }
        .onChange(of: phase) { if phase == .background { Self.scheduleRefresh() } }
        // iOS wakes the app now and then (about every 15 min at best) to check the station,
        // so a dose taken or a STOP still turns into a notification when the app is closed.
        .backgroundTask(.appRefresh(Self.refreshTask)) {
            Self.scheduleRefresh()
            await store.refresh()
        }
    }

    nonisolated static func scheduleRefresh() {
        let r = BGAppRefreshTaskRequest(identifier: refreshTask)
        r.earliestBeginDate = Date(timeIntervalSinceNow: 15 * 60)
        try? BGTaskScheduler.shared.submit(r)
    }
}

struct RootView: View {
    @Environment(AppStore.self) private var store
    @State private var tab = Tab.today

    enum Tab: String, CaseIterable {
        case today = "Today", trends = "Trends", medications = "Medicines", settings = "Settings"
        var icon: String {
            switch self {
            case .today: "house.fill"
            case .trends: "chart.xyaxis.line"
            case .medications: "pills.fill"
            case .settings: "gearshape.fill"
            }
        }
    }

    var body: some View {
        Group {
            if store.onboarded {
                ZStack {
                    switch tab {
                    case .today: TodayView { withAnimation(.spring(duration: 0.3)) { tab = .trends } }
                    case .trends: TrendsView()
                    case .medications: MedicationsView()
                    case .settings: SettingsView()
                    }
                }
                .safeAreaInset(edge: .bottom) { tabBar }
            } else {
                OnboardingView()
            }
        }
        .background(PageBackground())
        .task { await store.refresh() }
        .task(id: store.useDemoData) {
            if !store.useDemoData { await store.followStation() }
        }
        .task(id: store.useDemoData) {
            if !store.useDemoData { await store.pollWhileOpen() }
        }
        .task(id: store.onboarded) {
            if store.onboarded { await Notifier.shared.requestPermission() }
        }
    }

    /// A floating dark capsule of icons, no words. The open tab sits in a blue circle.
    /// (VoiceOver still reads each tab's name.)
    private var tabBar: some View {
        HStack(spacing: 10) {
            ForEach(Tab.allCases, id: \.self) { t in
                Button {
                    withAnimation(.spring(duration: 0.3)) { tab = t }
                } label: {
                    Image(systemName: t.icon)
                        .font(.system(size: 19, weight: .semibold))
                        .foregroundStyle(tab == t ? Color.white : Color.white.opacity(0.6))
                        .frame(width: 54, height: 54)
                        .background { if tab == t { Circle().fill(Theme.accent) } }
                        .contentShape(Circle())
                }
                .buttonStyle(.plain)
                .accessibilityLabel(t.rawValue)
                .accessibilityAddTraits(tab == t ? .isSelected : [])
            }
        }
        .padding(6)
        .background(Theme.navBar, in: Capsule())
        .shadow(color: .black.opacity(0.18), radius: 16, y: 8)
        .padding(.bottom, 4)
        .sensoryFeedback(.selection, trigger: tab)
    }
}
