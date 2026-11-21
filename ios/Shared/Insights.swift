import Foundation

/// Routine tracking from GET /insights (docs/decline-tracking.md): each person's last week
/// against their own usual. Decoded with snake_case keys converted.
nonisolated struct Insights: Decodable {
    var generated: String
    var people: [PersonInsight]
}

nonisolated enum InsightLevel: String, Decodable {
    case steady, watch, talk, learning
}

nonisolated struct PersonInsight: Decodable, Identifiable, Hashable {
    var person: String
    var name: String
    var daysOfData: Int
    var learning: Bool
    var steadiness: Int?
    var level: InsightLevel
    var headline: String
    var signals: [Signal]
    var daily: [DayPoint]
    var id: String { person }

    nonisolated struct Signal: Decodable, Identifiable, Hashable {
        var id: String
        var title: String
        var unit: String
        var recent: Double?
        var usual: Double?
        var level: InsightLevel
        var worseBy: Double
        var higherIsWorse: Bool
    }

    nonisolated struct DayPoint: Decodable, Identifiable, Hashable {
        var date: String
        var scheduled: Int
        var taken: Int
        var lateMin: Double?
        var doubleDose: Int
        var wrongBottle: Int
        var unsure: Int
        var visitNoDose: Int
        var finishS: Double?
        var id: String { date }

        var day: Date { DayPoint.parser.date(from: date) ?? .now }
        var events: Int { doubleDose + wrongBottle + unsure + visitNoDose }

        static let parser: DateFormatter = {
            let f = DateFormatter()
            f.dateFormat = "yyyy-MM-dd"
            f.locale = Locale(identifier: "en_US_POSIX")
            return f
        }()
    }

    /// The usual lateness (for the chart's dashed line).
    var usualLate: Double? { signals.first { $0.id == "late" }?.usual }
}

extension PersonInsight.Signal {
    /// "48 min late", "81%", "3 a week": how the station's units read in a sentence.
    nonisolated func format(_ v: Double?) -> String {
        guard let v else { return "—" }
        switch unit {
        case "%": return "\(Int(v.rounded()))%"
        case "min late": return v < 0 ? "\(Int(-v.rounded())) min early" : "\(Int(v.rounded())) min late"
        case "min spread": return "±\(Int(v.rounded())) min"
        case "s": return "\(Int(v.rounded())) s"
        case "a week": return v == v.rounded() ? "\(Int(v))× a week" : String(format: "%.1f× a week", v)
        default: return String(format: "%.0f %@", v, unit)
        }
    }
}

// MARK: - Demo data

extension MockAPI {
    /// 35 made-up days in the same shape as the station's: Margaret's mornings have been slipping
    /// over the last two weeks, Robert is steady. Seeded, so it looks the same every launch.
    nonisolated static func demoInsights(people: [Person], now: Date = .now) -> Insights {
        var rng = SeededRandom(seed: 11)
        let cal = Calendar.current
        let today = cal.startOfDay(for: now)
        var out: [PersonInsight] = []
        for (i, p) in people.prefix(2).enumerated() {
            let slipping = i == 0
            var days: [PersonInsight.DayPoint] = []
            for back in stride(from: 29, through: 0, by: -1) {
                let d = cal.date(byAdding: .day, value: -back, to: today)!
                let k = slipping ? max(0, Double(14 - back) / 14) : 0
                let sched = slipping ? 4 : 3
                let missed = rng.next() < 0.04 + 0.6 * k ? 1 : 0
                days.append(.init(
                    date: PersonInsight.DayPoint.parser.string(from: d), scheduled: sched,
                    taken: back == 0 ? 1 : sched - missed,
                    lateMin: (6 + 70 * k + rng.gauss() * (6 + 18 * k)).rounded(),
                    doubleDose: rng.next() < 0.02 + 0.35 * k ? 1 : 0,
                    wrongBottle: rng.next() < 0.01 + 0.12 * k ? 1 : 0,
                    unsure: rng.next() < 0.05 + 0.25 * k ? 1 : 0,
                    visitNoDose: rng.next() < 0.02 + 0.2 * k ? 1 : 0,
                    finishS: (42 + 55 * k + rng.gauss() * 8).rounded()))
            }
            out.append(slipping ? margaretLike(p, days) : steady(p, days))
        }
        return Insights(generated: ISO8601DateFormatter().string(from: now), people: out)
    }

    private nonisolated static func sig(_ id: String, _ title: String, _ unit: String, _ r: Double, _ u: Double,
                                        _ l: InsightLevel, worse: Bool = true) -> PersonInsight.Signal {
        .init(id: id, title: title, unit: unit, recent: r, usual: u, level: l,
              worseBy: worse ? r - u : u - r, higherIsWorse: worse)
    }

    private nonisolated static func margaretLike(_ p: Person, _ d: [PersonInsight.DayPoint]) -> PersonInsight {
        PersonInsight(person: p.id, name: p.name, daysOfData: 35, learning: false, steadiness: 36, level: .talk,
                      headline: "\(p.name)'s morning pills are coming about 50 min later than usual this week.",
                      signals: [
                        sig("taken", "Doses taken", "%", 79, 96, .watch, worse: false),
                        sig("late", "Timing", "min late", 58, 8, .talk),
                        sig("regularity", "Regularity", "min spread", 24, 7, .watch),
                        sig("double_dose", "Double-dose attempts", "a week", 3, 0.3, .talk),
                        sig("wrong_bottle", "Mix-ups", "a week", 1, 0.3, .steady),
                        sig("unsure", "Unsure moments", "a week", 2, 0.5, .steady),
                        sig("visit_no_dose", "Visits with nothing taken", "a week", 1, 0.2, .steady),
                        sig("finish", "Time to finish", "s", 91, 44, .watch),
                      ], daily: d)
    }

    private nonisolated static func steady(_ p: Person, _ d: [PersonInsight.DayPoint]) -> PersonInsight {
        PersonInsight(person: p.id, name: p.name, daysOfData: 35, learning: false, steadiness: 100, level: .steady,
                      headline: "\(p.name)'s routine looks like usual.",
                      signals: [
                        sig("taken", "Doses taken", "%", 100, 97, .steady, worse: false),
                        sig("late", "Timing", "min late", 5, 7, .steady),
                        sig("regularity", "Regularity", "min spread", 6, 7, .steady),
                        sig("double_dose", "Double-dose attempts", "a week", 0, 0.3, .steady),
                        sig("wrong_bottle", "Mix-ups", "a week", 0, 0.3, .steady),
                        sig("unsure", "Unsure moments", "a week", 0, 0.3, .steady),
                        sig("visit_no_dose", "Visits with nothing taken", "a week", 0, 0, .steady),
                        sig("finish", "Time to finish", "s", 40, 43, .steady),
                      ], daily: d)
    }
}

/// Small deterministic random numbers, so the demo charts don't change between launches.
nonisolated struct SeededRandom {
    private var s: UInt64
    init(seed: UInt64) { s = seed &* 0x9E3779B97F4A7C15 | 1 }
    mutating func next() -> Double {
        s ^= s << 13; s ^= s >> 7; s ^= s << 17
        return Double(s % 1_000_000) / 1_000_000
    }
    mutating func gauss() -> Double {                 // roughly normal, mean 0, sd 1
        (0..<6).reduce(0) { acc, _ in acc + next() } - 3
    }
}
