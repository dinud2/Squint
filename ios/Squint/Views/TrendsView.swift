import Charts
import SwiftUI

/// Routine tracking for the caregiver: each person's last week against their own usual.
/// Squint notices change; it never diagnoses (docs/decline-tracking.md).
struct TrendsView: View {
    @Environment(AppStore.self) private var store

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 22) {
                    VStack(alignment: .leading, spacing: 4) {
                        Eyebrow("Last 30 days")
                        Text("Routine").font(Theme.display(34)).foregroundStyle(Theme.ink)
                        Text("Squint compares each week with their own usual, and speaks up only when something changes.")
                            .font(.subheadline).foregroundStyle(Theme.muted)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                    .padding(.top, 12)

                    if store.insights.isEmpty {
                        empty
                    }
                    ForEach(store.insights) { InsightCard(insight: $0) }

                    Label("Squint notices changes in a routine. It can't diagnose anything. If a change keeps up, mention it to their doctor.",
                          systemImage: "info.circle")
                        .font(.footnote).foregroundStyle(Theme.muted)
                        .padding(.horizontal, 6)
                }
                .padding(.horizontal, 20).padding(.bottom, 24)
            }
            .background(Theme.paper.ignoresSafeArea())
            .toolbar(.hidden, for: .navigationBar)
            .refreshable { await store.refreshInsights() }
        }
    }

    private var empty: some View {
        VStack(spacing: 12) {
            SquintBadge(mood: .sleep, size: 44)
            Text(store.insightsError == nil ? "No routine yet" : "Couldn't load the routine")
                .font(Theme.display(20, .bold)).foregroundStyle(Theme.ink)
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

struct InsightCard: View {
    @Environment(AppStore.self) private var store
    let insight: PersonInsight
    @State private var showAll = false

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            header
            Text(insight.headline)
                .font(Theme.display(19, .bold)).foregroundStyle(Theme.ink)
                .fixedSize(horizontal: false, vertical: true)
            if !insight.learning {
                TimingChart(insight: insight)
                signals
            }
        }
        .paperCard()
    }

    private var header: some View {
        HStack(spacing: 12) {
            if let p = store.person(insight.person) { Avatar(person: p, size: 40) }
            VStack(alignment: .leading, spacing: 2) {
                Text(insight.name).font(Theme.display(20, .bold)).foregroundStyle(Theme.ink)
                Text(insight.level.label.uppercased())
                    .font(.system(size: 11, weight: .heavy, design: .rounded)).kerning(1)
                    .foregroundStyle(insight.level.color)
            }
            Spacer()
            SteadinessRing(value: insight.steadiness, color: insight.level.color)
        }
    }

    private var signals: some View {
        let moved = insight.signals.filter { $0.level != .steady }
        let rest = insight.signals.filter { $0.level == .steady }
        return VStack(spacing: 0) {
            ForEach(moved + (showAll ? rest : [])) { s in
                SignalRow(signal: s)
                Divider().overlay(Theme.line)
            }
            Button {
                withAnimation(.snappy) { showAll.toggle() }
            } label: {
                HStack {
                    Text(showAll ? "Show less" : moved.isEmpty ? "Show all \(rest.count) signals" : "Show \(rest.count) steady signals")
                    Spacer()
                    Image(systemName: showAll ? "chevron.up" : "chevron.down")
                }
                .font(.subheadline.weight(.semibold)).foregroundStyle(Theme.muted)
                .padding(.vertical, 10)
                .contentShape(Rectangle())
            }
            .buttonStyle(.plain)
        }
    }
}

/// 0–100 ring: how close this week is to their usual.
struct SteadinessRing: View {
    let value: Int?
    let color: Color

    var body: some View {
        ZStack {
            Circle().stroke(Theme.line, lineWidth: 5)
            Circle().trim(from: 0, to: CGFloat(value ?? 0) / 100)
                .stroke(color, style: StrokeStyle(lineWidth: 5, lineCap: .round))
                .rotationEffect(.degrees(-90))
            VStack(spacing: -2) {
                Text(value.map(String.init) ?? "–").font(Theme.display(17)).foregroundStyle(Theme.ink)
                Text("of 100").font(.system(size: 8, weight: .bold, design: .rounded)).foregroundStyle(Theme.muted)
            }
        }
        .frame(width: 54, height: 54)
        .accessibilityElement()
        .accessibilityLabel("Steadiness \(value ?? 0) out of 100")
    }
}

/// Minutes late per day, the usual as a dashed line, and dots on days something went wrong.
struct TimingChart: View {
    let insight: PersonInsight

    var body: some View {
        let pts = insight.daily.filter { $0.lateMin != nil }
        let lates = pts.compactMap(\.lateMin) + [insight.usualLate ?? 0]
        let lo = min(0, (lates.min() ?? 0) - 5), hi = max(30, (lates.max() ?? 0) + 10)
        VStack(alignment: .leading, spacing: 6) {
            Text("How late, each day").font(.caption.weight(.bold)).foregroundStyle(Theme.muted)
            Chart {
                ForEach(pts) { d in
                    AreaMark(x: .value("Day", d.day, unit: .day), y: .value("Min late", d.lateMin ?? 0))
                        .foregroundStyle(LinearGradient(colors: [insight.level.color.opacity(0.25), .clear],
                                                        startPoint: .top, endPoint: .bottom))
                        .interpolationMethod(.monotone)
                    LineMark(x: .value("Day", d.day, unit: .day), y: .value("Min late", d.lateMin ?? 0))
                        .foregroundStyle(Theme.ink)
                        .lineStyle(StrokeStyle(lineWidth: 2, lineCap: .round))
                        .interpolationMethod(.monotone)
                }
                if let u = insight.usualLate {
                    RuleMark(y: .value("Usual", u))
                        .foregroundStyle(Theme.muted)
                        .lineStyle(StrokeStyle(lineWidth: 1, dash: [4, 4]))
                        .annotation(position: .top, alignment: .leading) {
                            Text("usual").font(.caption2.weight(.bold)).foregroundStyle(Theme.muted)
                        }
                }
                ForEach(insight.daily.filter { $0.doubleDose + $0.wrongBottle > 0 }) { d in
                    PointMark(x: .value("Day", d.day, unit: .day), y: .value("Min late", d.lateMin ?? 0))
                        .foregroundStyle(Theme.flagged)
                        .symbolSize(40)
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
            .frame(height: 140)
            HStack(spacing: 6) {
                Circle().fill(Theme.flagged).frame(width: 7, height: 7)
                Text("double-dose attempt or mix-up").font(.caption2).foregroundStyle(Theme.muted)
            }
        }
        .accessibilityElement(children: .ignore)
        .accessibilityLabel("Chart of how late each day's doses were")
    }
}

struct SignalRow: View {
    let signal: PersonInsight.Signal

    var body: some View {
        HStack(alignment: .firstTextBaseline, spacing: 10) {
            Circle().fill(signal.level.color).frame(width: 8, height: 8)
            VStack(alignment: .leading, spacing: 2) {
                Text(signal.title).font(.body.weight(.semibold)).foregroundStyle(Theme.ink)
                Text("usually \(signal.format(signal.usual))").font(.footnote).foregroundStyle(Theme.muted)
            }
            Spacer()
            VStack(alignment: .trailing, spacing: 2) {
                Text(signal.format(signal.recent)).font(Theme.display(16, .bold))
                    .foregroundStyle(signal.level == .steady ? Theme.ink : signal.level.color)
                Text("this week").font(.caption2).foregroundStyle(Theme.muted)
            }
        }
        .padding(.vertical, 10)
        .accessibilityElement(children: .combine)
    }
}
