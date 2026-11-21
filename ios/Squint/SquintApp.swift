import SwiftUI

@main
struct SquintApp: App {
    @State private var store = AppStore()

    var body: some Scene {
        WindowGroup {
            RootView()
                .environment(store)
                .tint(Theme.ink)
                .fontDesign(.rounded)
        }
    }
}

struct RootView: View {
    @Environment(AppStore.self) private var store
    @State private var tab = Tab.today

    enum Tab: String, CaseIterable {
        case today = "Today", trends = "Trends", medications = "Medicines", settings = "Settings"
        var icon: String {
            switch self {
            case .today: "eyes"
            case .trends: "chart.line.uptrend.xyaxis"
            case .medications: "pills.fill"
            case .settings: "slider.horizontal.3"
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
        .background(Theme.paper.ignoresSafeArea())
        .task { await store.refresh() }
        .task(id: store.useDemoData) {
            if !store.useDemoData { await store.followStation() }
        }
    }

    /// A dot on a tab that has something for the caregiver: red for today's alerts, amber/red for routine.
    private func badge(for t: Tab) -> Color? {
        switch t {
        case .today: store.attention.isEmpty ? nil : Theme.flagged
        case .trends: store.routineAlert?.level.color
        default: nil
        }
    }

    /// A floating ink capsule instead of the stock tab bar.
    private var tabBar: some View {
        HStack(spacing: 4) {
            ForEach(Tab.allCases, id: \.self) { t in
                Button {
                    withAnimation(.spring(duration: 0.3)) { tab = t }
                } label: {
                    HStack(spacing: 6) {
                        Image(systemName: t.icon).font(.system(size: 16, weight: .bold))
                        if tab == t { Text(t.rawValue).font(Theme.display(15, .bold)).lineLimit(1) }
                    }
                    .foregroundStyle(tab == t ? Theme.ink : Theme.paper.opacity(0.7))
                    .padding(.horizontal, tab == t ? 18 : 16).padding(.vertical, 12)
                    .background { if tab == t { Capsule().fill(Theme.paper) } }
                    .overlay(alignment: .topTrailing) {
                        if tab != t, let c = badge(for: t) {
                            Circle().fill(c).frame(width: 8, height: 8).offset(x: -8, y: 6)
                        }
                    }
                    .contentShape(Capsule())
                }
                .buttonStyle(.plain)
                .accessibilityLabel(t.rawValue)
                .accessibilityAddTraits(tab == t ? .isSelected : [])
            }
        }
        .padding(5)
        .background(Theme.ink, in: Capsule())
        .shadow(color: .black.opacity(0.18), radius: 16, y: 8)
        .padding(.bottom, 4)
        .sensoryFeedback(.selection, trigger: tab)
    }
}
