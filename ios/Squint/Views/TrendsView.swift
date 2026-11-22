import Charts
import SwiftUI

/// Routine tracking for the caregiver: each person's last week against their own usual.
/// Squint notices change; it never diagnoses (docs/decline-tracking.md).
struct TrendsView: View {
    @Environment(AppStore.self) private var store

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: Space.section) {
                    Text("Routine").font(Theme.display(24, .semibold)).foregroundStyle(Theme.ink)
                        .frame(maxWidth: .infinity)
                        .padding(.top, 12)

                    if store.insights.isEmpty {
                        empty
                    }
                    ForEach(store.insights) { InsightCard(insight: $0) }

                    Label("Squint notices changes in a routine. It can't diagnose anything. If a change keeps up, mention it to their doctor.",
                          systemImage: "info.circle")
                        .font(.subheadline).foregroundStyle(Theme.muted)
                        .lineSpacing(4)
                        .padding(.horizontal, 6)
                }
                .padding(.horizontal, 20).padding(.bottom, 24)
            }
            .statusBarFade()
            .background(PageBackground())
            .toolbar(.hidden, for: .navigationBar)
            .refreshable { await store.refreshInsights() }
        }
    }

    private var empty: some View {
        VStack(spacing: 12) {
            IconBubble(symbol: "chart.xyaxis.line", size: 52)
            Text(store.insightsError == nil ? "No routine yet" : "Couldn't load the routine")
                .font(Theme.display(20, .semibold)).foregroundStyle(Theme.ink)
            Text(store.insightsError ?? "Squint needs about two weeks at the counter before it can tell what's usual.")
                .font(.subheadline).foregroundStyle(Theme.muted).multilineTextAlignment(.center)
        }
        .frame(maxWidth: .infinity)
        .paperCard()
    }
}

extension InsightLevel {
    var color: Color {
        switch self {
        case .steady: Theme.taken
        case .watch: Theme.missed
        case .talk: Theme.flagged
        case .learning: Theme.muted
        }
    }

    var label: String {
        switch self {
        case .steady: "Steady"
        case .watch: "Worth watching"
        case .talk: "Worth a chat"
        case .learning: "Learning"
        }
    }

    var mood: SquintMood {
        switch self {
        case .steady: .happy
        case .watch: .concerned
        case .talk: .wrong
        case .learning: .idle
        }
    }
}

extension PersonInsight.Signal {
    /// The icon that says what a signal measures.
    var symbol: String {
        switch id {
        case "taken": "pills.fill"
        case "late": "clock.fill"
        case "regularity": "repeat"
        case "double_dose": "exclamationmark.triangle.fill"
        case "wrong_bottle": "arrow.left.arrow.right"
        case "unsure": "questionmark"
        case "visit_no_dose": "figure.walk"
        case "finish": "timer"
        default: "circle.dashed"
        }
    }

    /// A calm category colour per signal, so the tiles are easy to tell apart.
    /// (How serious a change is gets said once, in the card above.)
    var tint: Color {
        switch id {
        case "taken": Theme.green
        case "late", "finish": Theme.accent
        case "regularity": Theme.indigo
        case "double_dose", "wrong_bottle": Theme.coral
        case "unsure": Theme.pink
        case "visit_no_dose": Theme.teal
        default: Theme.accent
        }
    }
}

/// One person's routine: a graph card, then small signal tiles.
struct InsightCard: View {
    @Environment(AppStore.self) private var store
    let insight: PersonInsight
    @State private var showAll = false

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            graphCard
            if !insight.learning { signals }
        }
    }

    private var graphCard: some View {
        VStack(alignment: .leading, spacing: 18) {
            HStack(spacing: 12) {
                if let p = store.person(insight.person) { Avatar(person: p, size: 42) }
                TitleBlock(title: insight.name, subtitle: insight.level.label,
                           subtitleColor: insight.level == .steady ? Theme.muted : insight.level.color)
                Spacer()
                SteadinessRing(value: insight.steadiness, color: Theme.personColor(insight.person))
            }
            VStack(alignment: .leading, spacing: 6) {
                if let late = insight.signals.first(where: { $0.id == "late" }), !insight.learning {
                    Text(late.format(late.recent)).font(Theme.number(48)).foregroundStyle(Theme.ink)
                }
                Text(insight.headline)
                    .font(.body).foregroundStyle(Theme.muted)
                    .lineSpacing(4)
                    .fixedSize(horizontal: false, vertical: true)
            }
            if !insight.learning { TimingChart(insight: insight, color: Theme.personColor(insight.person)) }
        }
        .paperCard()
    }

    private var signals: some View {
        // Timing is already the big number on the graph card.
        let shown = insight.signals.filter { $0.id != "late" }
        let moved = shown.filter { $0.level != .steady }
        let rest = shown.filter { $0.level == .steady }
        return VStack(spacing: 14) {
            LazyVGrid(columns: [GridItem(.flexible(), spacing: 14), GridItem(.flexible(), spacing: 14)], spacing: 14) {
                ForEach(moved + (showAll ? rest : [])) { SignalTile(signal: $0) }
            }
            if !rest.isEmpty {
                Button {
                    withAnimation(.snappy) { showAll.toggle() }
                } label: {
                    Label(showAll ? "Show less" : moved.isEmpty ? "Show all \(rest.count)" : "Show \(rest.count) steady",
                          systemImage: showAll ? "chevron.up" : "chevron.down")
                        .font(.subheadline.weight(.medium)).foregroundStyle(Theme.accent)
                        .padding(.horizontal, 18).padding(.vertical, 12)
                        .background(Theme.accentSoft, in: Capsule())
                }
                .buttonStyle(.plain)
            }
        }
    }
}

/// A small tile: what it measures (icon + name) and this week's value.
struct SignalTile: View {
    let signal: PersonInsight.Signal

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            IconBubble(symbol: signal.symbol, tint: signal.tint, size: 38)
            Spacer(minLength: 12)
            // Label and value as one pair: small label, 2 pt gap, big value.
            VStack(alignment: .leading, spacing: 2) {
                Text(signal.title).font(.system(size: 13, design: .rounded)).foregroundStyle(Theme.muted)
                    .lineLimit(1).minimumScaleFactor(0.75)
                Text(signal.format(signal.recent)).font(Theme.number(30)).foregroundStyle(Theme.ink)
                    .lineLimit(1).minimumScaleFactor(0.7)
            }
        }
        .padding(18)
        .frame(maxWidth: .infinity, minHeight: 150, maxHeight: 150, alignment: .topLeading)
        .widgetBackground(26)
        .accessibilityElement(children: .combine)
    }
}

/// 0–100 ring: how close this week is to their usual.
struct SteadinessRing: View {
    let value: Int?
    var color: Color = Theme.accent

    var body: some View {
        ZStack {
            Circle().stroke(color.opacity(0.14), lineWidth: 5)
            Circle().trim(from: 0, to: CGFloat(value ?? 0) / 100)
                .stroke(color, style: StrokeStyle(lineWidth: 5, lineCap: .round))
                .rotationEffect(.degrees(-90))
            Text(value.map(String.init) ?? "–").font(Theme.number(16)).foregroundStyle(Theme.ink)
        }
        .frame(width: 48, height: 48)
        .accessibilityElement()
        .accessibilityLabel("Steadiness \(value ?? 0) out of 100")
    }
}

/// Minutes late per day, in the person's colour, with the usual as a dashed line.
struct TimingChart: View {
    let insight: PersonInsight
    var color: Color = Theme.accent

    var body: some View {
        let pts = insight.daily.filter { $0.lateMin != nil }
        let lates = pts.compactMap(\.lateMin) + [insight.usualLate ?? 0]
        let lo = min(0, (lates.min() ?? 0) - 5), hi = max(30, (lates.max() ?? 0) + 10)
        Chart {
            ForEach(pts) { d in
                AreaMark(x: .value("Day", d.day, unit: .day), y: .value("Min late", d.lateMin ?? 0))
                    .foregroundStyle(LinearGradient(colors: [color.opacity(0.22), color.opacity(0)],
                                                    startPoint: .top, endPoint: .bottom))
                    .interpolationMethod(.catmullRom)
                LineMark(x: .value("Day", d.day, unit: .day), y: .value("Min late", d.lateMin ?? 0))
                    .foregroundStyle(color)
                    .lineStyle(StrokeStyle(lineWidth: 2.5, lineCap: .round))
                    .interpolationMethod(.catmullRom)
            }
            if let u = insight.usualLate {
                RuleMark(y: .value("Usual", u))
                    .foregroundStyle(Theme.muted.opacity(0.6))
                    .lineStyle(StrokeStyle(lineWidth: 1, dash: [4, 4]))
            }
        }
        .chartYScale(domain: lo...hi)
        .chartYAxis {
            AxisMarks(position: .leading, values: .automatic(desiredCount: 3)) { v in
                AxisGridLine().foregroundStyle(Theme.line)
                AxisValueLabel { if let m = v.as(Double.self) { Text("\(Int(m))m") } }
            }
        }
        .chartXAxis {
            AxisMarks(values: .stride(by: .day, count: 7)) { _ in
                AxisValueLabel(format: .dateTime.month(.abbreviated).day())
            }
        }
        .frame(height: 150)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel("Chart of how late each day's doses were")
    }
}
