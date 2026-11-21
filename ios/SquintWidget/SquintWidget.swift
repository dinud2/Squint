import SwiftUI
import WidgetKit

// Squint on the home screen and lock screen: today's pills at a glance, with Squint's face.
// The widget asks the station (or the demo data) itself, using the settings the app keeps in the
// App Group (Shared/Settings.swift), so it stays fresh without the app being open.

@main
struct SquintWidgetBundle: WidgetBundle {
    var body: some Widget { TodayWidget() }
}

struct TodayWidget: Widget {
    var body: some WidgetConfiguration {
        StaticConfiguration(kind: "SquintToday", provider: Provider()) { entry in
            TodayWidgetView(entry: entry)
        }
        .configurationDisplayName("Today")
        .description("Everyone's pills today, and Squint's face.")
        .supportedFamilies([.systemSmall, .systemMedium, .accessoryCircular, .accessoryRectangular, .accessoryInline])
    }
}

// MARK: - Timeline

struct Entry: TimelineEntry {
    var date: Date
    var glance: Glance?
    var error: String?
}

struct Provider: TimelineProvider {
    func placeholder(in context: Context) -> Entry { Entry(date: .now, glance: .sample) }

    func getSnapshot(in context: Context, completion: @escaping (Entry) -> Void) {
        if context.isPreview { return completion(placeholder(in: context)) }
        Task { completion(await load()) }
    }

    func getTimeline(in context: Context, completion: @escaping (Timeline<Entry>) -> Void) {
        Task {
            let e = await load()
            // Ask again in 15 minutes, or right when the next dose is due if that's sooner.
            var next = Date.now.addingTimeInterval(15 * 60)
            let dues = e.glance?.people.compactMap { $0.next.map { ClockTime.date($0.due) } } ?? []
            if let soonest = dues.filter({ $0 > .now }).min(), soonest < next { next = soonest.addingTimeInterval(60) }
            completion(Timeline(entries: [e], policy: .after(next)))
        }
    }

    private func load() async -> Entry {
        do { return Entry(date: .now, glance: try await Glance.fetch()) }
        catch { return Entry(date: .now, glance: nil, error: "Can't reach the station") }
    }
}

// MARK: - Views

struct TodayWidgetView: View {
    @Environment(\.widgetFamily) private var family
    let entry: Entry

    var body: some View {
        Group {
            switch family {
            case .accessoryCircular: circular
            case .accessoryRectangular: rectangular
            case .accessoryInline: Text(entry.glance?.headline ?? entry.error ?? "Squint")
            case .systemMedium: medium
            default: small
            }
        }
        .containerBackground(for: .widget) { Color(red: 0.043, green: 0.043, blue: 0.051) }   // Squint's screen
    }

    private var mood: Glance.Mood { entry.glance?.mood ?? .sleep }

    // Home screen, small: the face, the count, one line.
    private var small: some View {
        VStack(alignment: .leading, spacing: 6) {
            Eyes(mood: mood).frame(width: 64, height: 30)
            Spacer(minLength: 0)
            if let g = entry.glance {
                HStack(alignment: .firstTextBaseline, spacing: 2) {
                    Text("\(g.taken)").font(Theme.display(34))
                    Text("/\(g.total)").font(Theme.display(17, .bold)).foregroundStyle(.white.opacity(0.5))
                }
                Text(g.headline).font(.system(size: 12, weight: .semibold, design: .rounded))
                    .foregroundStyle(g.problems.isEmpty ? .white.opacity(0.75) : Theme.missed)
                    .lineLimit(2)
            } else {
                Text(entry.error ?? "").font(.caption.weight(.semibold)).foregroundStyle(.white.opacity(0.7))
            }
        }
        .foregroundStyle(.white)
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .leading)
    }

    // Home screen, medium: the face and line on the left, a row per person on the right.
    private var medium: some View {
        HStack(spacing: 14) {
            VStack(alignment: .leading, spacing: 8) {
                Eyes(mood: mood).frame(width: 70, height: 32)
                Spacer(minLength: 0)
                Text(entry.glance?.headline ?? entry.error ?? "")
                    .font(.system(size: 13, weight: .semibold, design: .rounded))
                    .foregroundStyle(entry.glance?.problems.isEmpty == false ? Theme.missed : .white.opacity(0.8))
                    .lineLimit(3)
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            VStack(alignment: .leading, spacing: 10) {
                ForEach(entry.glance?.people ?? []) { p in
                    VStack(alignment: .leading, spacing: 4) {
                        HStack {
                            Text(p.name).font(Theme.display(15, .bold))
                            Spacer()
                            Text("\(p.taken)/\(p.total)").font(Theme.display(14, .bold)).monospacedDigit()
                                .foregroundStyle(.white.opacity(0.6))
                        }
                        PillDots(taken: p.taken, total: p.total, trouble: !p.problems.isEmpty)
                    }
                }
            }
            .frame(maxWidth: .infinity)
        }
        .foregroundStyle(.white)
    }

    // Lock screen, round: how much of today is done.
    private var circular: some View {
        let g = entry.glance
        return Gauge(value: Double(g?.taken ?? 0), in: 0...Double(max(g?.total ?? 1, 1))) {
            Image(systemName: "pills.fill")
        } currentValueLabel: {
            Text("\(g?.taken ?? 0)/\(g?.total ?? 0)").font(.system(size: 13, weight: .bold, design: .rounded))
        }
        .gaugeStyle(.accessoryCircularCapacity)
    }

    // Lock screen, wide: one line per person.
    private var rectangular: some View {
        VStack(alignment: .leading, spacing: 1) {
            Text(entry.glance?.headline ?? entry.error ?? "Squint")
                .font(.system(size: 13, weight: .bold, design: .rounded)).lineLimit(1)
            ForEach(entry.glance?.people.prefix(2).map { $0 } ?? []) { p in
                Text("\(p.name)  \(p.taken)/\(p.total)\(p.problems.isEmpty ? "" : "  !")")
                    .font(.system(size: 13, weight: .medium, design: .rounded))
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }
}

/// One capsule per dose today: filled when taken.
struct PillDots: View {
    let taken: Int, total: Int, trouble: Bool
    var body: some View {
        HStack(spacing: 3) {
            ForEach(0..<max(total, 0), id: \.self) { i in
                Capsule()
                    .fill(i < taken ? Theme.taken : (trouble && i == taken ? Theme.missed : .white.opacity(0.18)))
                    .frame(width: 13, height: 6)
            }
        }
    }
}

/// Squint's eyes, still: the same moods as the Tab5, drawn with plain shapes.
struct Eyes: View {
    let mood: Glance.Mood

    var body: some View {
        GeometryReader { geo in
            let d = min(geo.size.height, geo.size.width * 0.42)
            HStack(spacing: geo.size.width - 2 * d) {
                eye(left: true, d: d)
                eye(left: false, d: d)
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity)
        }
    }

    @ViewBuilder private func eye(left: Bool, d: CGFloat) -> some View {
        switch mood {
        case .idle:
            Circle().fill(.white).frame(width: d, height: d)
        case .happy:
            Arc().stroke(.white, style: StrokeStyle(lineWidth: d * 0.24, lineCap: .round)).frame(width: d, height: d)
        case .remind:      // the wink
            if left { Circle().fill(.white).frame(width: d, height: d) }
            else { Arc().stroke(.white, style: StrokeStyle(lineWidth: d * 0.24, lineCap: .round)).frame(width: d, height: d) }
        case .wrong:       // amber half-moons, looking worried
            HalfMoon().fill(Theme.missed).frame(width: d, height: d)
        case .sleep:
            Arc(flipped: true).stroke(Color(red: 0.36, green: 0.54, blue: 0.81),
                                      style: StrokeStyle(lineWidth: d * 0.16, lineCap: .round))
                .frame(width: d, height: d * 0.6)
        }
    }
}

/// An upside-down U (a happy squint), or a U (closed, asleep).
struct Arc: Shape {
    var flipped = false
    func path(in r: CGRect) -> Path {
        var p = Path()
        let c = CGPoint(x: r.midX, y: flipped ? r.minY + r.height * 0.2 : r.maxY - r.height * 0.15)
        p.addArc(center: c, radius: r.width * 0.42, startAngle: .degrees(flipped ? 20 : 200),
                 endAngle: .degrees(flipped ? 160 : 340), clockwise: false)
        return p
    }
}

/// The bottom half of a circle (Squint's "wrong" eyes).
struct HalfMoon: Shape {
    func path(in r: CGRect) -> Path {
        var p = Path()
        p.addArc(center: CGPoint(x: r.midX, y: r.midY - r.height * 0.1), radius: r.width / 2,
                 startAngle: .degrees(0), endAngle: .degrees(180), clockwise: false)
        p.closeSubpath()
        return p
    }
}

extension Glance {
    /// What the widget gallery shows before it has real data.
    static let sample = Glance(people: [
        .init(id: "margaret", name: "Margaret", taken: 2, total: 4, dueNow: [], next: (med: "Metformin", due: "18:00"), problems: []),
        .init(id: "robert", name: "Robert", taken: 1, total: 3, dueNow: [], next: (med: "Metoprolol", due: "20:00"), problems: []),
    ], mood: .remind, updated: .now)
}
