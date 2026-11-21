import Foundation

/// Today in one look: per person what's taken, what's next and what needs you, plus Squint's mood.
/// Siri answers from it and the widget draws it, so the two always agree with each other.
nonisolated struct Glance: Hashable, Sendable {
    /// The same words as SquintMood in the app, for the few moods a glance can have.
    enum Mood: String, Sendable { case sleep, idle, remind, happy, wrong }

    struct PersonDay: Hashable, Identifiable, Sendable {
        var id: String
        var name: String
        var taken: Int
        var total: Int
        var dueNow: [String]                 // medicine names, due and not taken yet
        var next: (med: String, due: String)?
        var problems: [String]               // missed or flagged, in words

        var allDone: Bool { total > 0 && taken == total }

        static func == (a: Self, b: Self) -> Bool {
            a.id == b.id && a.taken == b.taken && a.total == b.total && a.dueNow == b.dueNow &&
                a.next?.med == b.next?.med && a.next?.due == b.next?.due && a.problems == b.problems
        }
        func hash(into h: inout Hasher) { h.combine(id); h.combine(taken); h.combine(total); h.combine(dueNow) }
    }

    var people: [PersonDay]
    var mood: Mood
    var updated: Date

    var taken: Int { people.reduce(0) { $0 + $1.taken } }
    var total: Int { people.reduce(0) { $0 + $1.total } }
    var problems: [String] { people.flatMap(\.problems) }

    func person(_ id: String) -> PersonDay? { people.first { $0.id == id } }

    /// One short line, for the widget and as Siri's opener.
    var headline: String {
        if let p = problems.first { return p }
        if let p = people.first(where: { !$0.dueNow.isEmpty }) {
            return "\(p.name): \(p.dueNow.joined(separator: " and ")) due now"
        }
        if total > 0 && taken == total { return "All done for today" }
        if let p = people.compactMap({ p in p.next.map { (p, $0) } }).min(by: { $0.1.due < $1.1.due }) {
            return "Next: \(p.0.name)'s \(p.1.med) at \(ClockTime.display(p.1.due))"
        }
        return "Nothing due"
    }

    // MARK: - building one

    static func make(people: [Person], medications: [Medication], doses: [Dose], now: Date = .now) -> Glance {
        let nowM = ClockTime.minutes(ClockTime.from(now))
        func med(_ id: String) -> String { medications.first { $0.id == id }?.name ?? id }
        let elders = people.filter { $0.role == .elder }
        let days: [PersonDay] = elders.map { p in
            let mine = doses.filter { $0.personID == p.id }.sorted { $0.due < $1.due }
            let done = mine.filter { $0.status == .taken || $0.status == .flagged }
            let open = mine.filter { $0.status == .due }
            let dueNow = open.filter { ClockTime.minutes($0.due) <= nowM }.map { med($0.medID) }
            let next = open.first { ClockTime.minutes($0.due) > nowM }.map { (med: med($0.medID), due: $0.due) }
            let problems: [String] = mine.compactMap { d in
                switch d.status {
                case .missed: "\(p.name) missed \(med(d.medID)) at \(ClockTime.display(d.due))"
                case .flagged: d.reason ?? "Check \(p.name)'s \(med(d.medID))"
                default: nil
                }
            }
            return PersonDay(id: p.id, name: p.name, taken: done.count, total: mine.count,
                             dueNow: dueNow, next: next, problems: problems)
        }
        let hour = nowM / 60
        let mood: Mood =
            days.contains { !$0.problems.isEmpty } ? .wrong :
            days.contains { !$0.dueNow.isEmpty } ? .remind :
            (hour >= 22 || hour < 6) ? .sleep :
            (!days.isEmpty && days.allSatisfy { $0.allDone || $0.total == 0 }) ? .happy : .idle
        return Glance(people: days, mood: mood, updated: now)
    }

    /// Ask the station (or the demo data) for today.
    static func fetch(_ api: SquintAPI = SquintSettings.api) async throws -> Glance {
        async let p = api.people()
        async let m = api.medications()
        async let t = api.today()
        return make(people: try await p, medications: try await m, doses: try await t)
    }

    // MARK: - in words (Siri)

    func sentence(for p: PersonDay) -> String {
        var s: String
        if p.total == 0 {
            s = "\(p.name) has no pills today."
        } else if p.allDone {
            s = "Yes. \(p.name) has taken all \(p.total == 1 ? "of today's pills" : "\(p.total) of today's doses")."
        } else if !p.dueNow.isEmpty {
            s = "Not yet. \(p.name) still needs \(Self.list(p.dueNow)), and has taken \(p.taken) of \(p.total) today."
        } else if let n = p.next {
            s = "\(p.name) has taken \(p.taken) of \(p.total) so far. Next is \(n.med) at \(ClockTime.display(n.due))."
        } else {
            s = "\(p.name) has taken \(p.taken) of \(p.total) today."
        }
        if let problem = p.problems.first { s += " Heads up: \(problem)." }
        return s
    }

    var summary: String {
        if people.isEmpty { return "Squint isn't set up with anyone yet." }
        let lines = people.map { p -> String in
            if p.allDone { return "\(p.name) is all done" }
            if !p.dueNow.isEmpty { return "\(p.name) still needs \(Self.list(p.dueNow))" }
            return "\(p.name) has taken \(p.taken) of \(p.total)"
        }
        var s = Self.list(lines) + "."
        switch problems.count {
        case 0: break
        case 1: s += " One thing needs you: \(problems[0])."
        default: s += " \(problems.count) things need you. The first: \(problems[0])."
        }
        return s
    }

    static func list(_ xs: [String]) -> String {
        switch xs.count {
        case 0: ""
        case 1: xs[0]
        default: xs.dropLast().joined(separator: ", ") + " and " + xs.last!
        }
    }
}
