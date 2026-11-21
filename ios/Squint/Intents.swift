import AppIntents
import SwiftUI

// Siri, Spotlight and Shortcuts: ask Squint about today without opening the app.
// "Hey Siri, has Dinu taken his pills in Squint?"   "Hey Siri, ask Squint how everyone's doing."
// Both answer from Glance (Shared/Glance.swift), the same summary the widget draws.

struct PersonEntity: AppEntity {
    static let typeDisplayRepresentation: TypeDisplayRepresentation = "Person"
    static let defaultQuery = PersonQuery()

    var id: String
    var name: String
    var displayRepresentation: DisplayRepresentation { DisplayRepresentation(title: "\(name)") }
}

struct PersonQuery: EntityStringQuery {
    private func all() async throws -> [PersonEntity] {
        try await SquintSettings.api.people()
            .filter { $0.role == .elder }
            .map { PersonEntity(id: $0.id, name: $0.name) }
    }

    func entities(for identifiers: [String]) async throws -> [PersonEntity] {
        try await all().filter { identifiers.contains($0.id) }
    }

    func entities(matching string: String) async throws -> [PersonEntity] {
        let s = string.lowercased()
        return try await all().filter { $0.name.lowercased().contains(s) || s.contains($0.name.lowercased()) }
    }

    func suggestedEntities() async throws -> [PersonEntity] { try await all() }
}

struct CheckPillsIntent: AppIntent {
    static let title: LocalizedStringResource = "Check someone's pills"
    static let description = IntentDescription("Whether they've taken today's pills, and what's next.")

    @Parameter(title: "Person", requestValueDialog: "Who should I check on?")
    var person: PersonEntity

    static var parameterSummary: some ParameterSummary { Summary("Check \(\.$person)'s pills") }

    func perform() async throws -> some IntentResult & ProvidesDialog & ShowsSnippetView {
        let g = try await Glance.fetch()
        guard let day = g.person(person.id) else {
            return .result(dialog: "Squint doesn't have \(person.name) set up.", view: GlanceSnippet(glance: g, only: nil))
        }
        return .result(dialog: "\(g.sentence(for: day))", view: GlanceSnippet(glance: g, only: day.id))
    }
}

struct TodaySummaryIntent: AppIntent {
    static let title: LocalizedStringResource = "How's everyone doing"
    static let description = IntentDescription("Everyone's pills today, and anything that needs you.")

    func perform() async throws -> some IntentResult & ProvidesDialog & ShowsSnippetView {
        let g = try await Glance.fetch()
        return .result(dialog: "\(g.summary)", view: GlanceSnippet(glance: g, only: nil))
    }
}

struct SquintShortcuts: AppShortcutsProvider {
    static var appShortcuts: [AppShortcut] {
        AppShortcut(intent: CheckPillsIntent(), phrases: [
            "Has \(\.$person) taken their pills in \(.applicationName)",
            "Has \(\.$person) taken his pills in \(.applicationName)",
            "Has \(\.$person) taken her pills in \(.applicationName)",
            "Ask \(.applicationName) about \(\.$person)",
            "Check \(\.$person) in \(.applicationName)",
        ], shortTitle: "Check pills", systemImageName: "pills.fill")
        AppShortcut(intent: TodaySummaryIntent(), phrases: [
            "Ask \(.applicationName) how everyone's doing",
            "How is everyone doing in \(.applicationName)",
            "What does \(.applicationName) say",
        ], shortTitle: "Today", systemImageName: "eyes")
    }
}

/// The little card Siri shows under its answer.
struct GlanceSnippet: View {
    let glance: Glance
    let only: String?

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            ForEach(glance.people.filter { only == nil || $0.id == only }) { p in
                HStack(spacing: 12) {
                    Text(p.name).font(Theme.display(18, .bold))
                    Spacer()
                    HStack(spacing: 3) {
                        ForEach(0..<p.total, id: \.self) { i in
                            Capsule().fill(i < p.taken ? Theme.taken : Theme.line)
                                .frame(width: 14, height: 7)
                        }
                    }
                    Text("\(p.taken)/\(p.total)").font(Theme.display(16)).monospacedDigit()
                }
            }
            if let problem {
                Label(problem, systemImage: "exclamationmark.circle.fill")
                    .font(.footnote).foregroundStyle(Theme.missed)
            }
        }
        .foregroundStyle(Theme.ink)
        .padding()
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Theme.surface)          // its own paper, so it reads on Siri's light or dark panel
    }

    /// The first thing that needs the caregiver: that person's, or anyone's.
    private var problem: String? {
        if let only { return glance.person(only)?.problems.first }
        return glance.problems.first
    }
}
