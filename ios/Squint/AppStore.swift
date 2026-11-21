import Foundation
import Observation
import WidgetKit

/// The app's state in one place. Views read from it; it talks to the API.
@MainActor
@Observable
final class AppStore {
    // settings, saved on the phone
    var useDemoData: Bool { didSet { save() } }
    var backendURL: String { didSet { save() } }
    var homeURL: String { didSet { save() } }
    var onboarded: Bool { didSet { save() } }

    // data
    var people: [Person] = []
    var medications: [Medication] = []
    var doses: [Dose] = []
    var lastError: String?
    var lastRefresh: Date?
    var insights: [PersonInsight] = []             // routine tracking (GET /insights)
    var insightsError: String?
    private var photos: [String: Data] = [:]          // person id -> face photo (phone only for now)

    // Squint, the buddy on the counter
    var live: SquintState?                            // what the Tab5 is showing (live mode)
    var liveConnected = false
    var demoScene: SquintState?                       // while "Play a demo" runs
    private var commandSeq = 0
    private var lastGlance: Glance?

    init() {
        useDemoData = SquintSettings.useDemoData
        backendURL = SquintSettings.backendURL
        homeURL = SquintSettings.homeURL
        onboarded = SquintSettings.onboarded
    }

    /// Settings live in the App Group (Shared/Settings.swift), so the widget and Siri see them too.
    private func save() {
        SquintSettings.useDemoData = useDemoData
        SquintSettings.backendURL = backendURL
        SquintSettings.homeURL = homeURL
        SquintSettings.onboarded = onboarded
        WidgetCenter.shared.reloadAllTimelines()          // demo/live or the station may have changed
    }

    var api: SquintAPI { SquintSettings.api }

    var elders: [Person] { people.filter { $0.role == .elder } }
    func person(_ id: String) -> Person? { people.first { $0.id == id } }
    func medication(_ id: String) -> Medication? { medications.first { $0.id == id } }
    func doses(for p: Person) -> [Dose] { doses.filter { $0.personID == p.id } }
    var attention: [Dose] { doses.filter(\.needsAttention) }

    func refresh() async {
        do {
            async let p = api.people()
            async let m = api.medications()
            async let t = api.today()
            var ppl = try await p
            for i in ppl.indices { ppl[i].photo = photos[ppl[i].id] }
            if ppl.map(\.name) != people.map(\.name) {
                SquintShortcuts.updateAppShortcutParameters()   // so Siri knows the names
            }
            people = ppl
            medications = try await m
            doses = try await t
            lastError = nil
            lastRefresh = Date()
            let g = Glance.make(people: people, medications: medications, doses: doses)
            if g.people != lastGlance?.people || g.mood != lastGlance?.mood {
                lastGlance = g
                WidgetCenter.shared.reloadAllTimelines()      // something changed: redraw the widget now
            }
        } catch {
            lastError = error.localizedDescription
        }
        await refreshInsights()
    }

    /// Separate from the rest: an older station without /insights must not break Today.
    func refreshInsights() async {
        do {
            insights = try await api.insights(days: 30).people
            insightsError = nil
        } catch {
            insightsError = error.localizedDescription
        }
    }

    func insight(for p: Person) -> PersonInsight? { insights.first { $0.person == p.id } }

    /// The most important routine change, if any, for the tab badge and Today.
    var routineAlert: PersonInsight? {
        insights.filter { $0.level == .talk }.first ?? insights.filter { $0.level == .watch }.first
    }

    func addPerson(name: String, photo: Data?) async {
        do {
            let p = try await api.addPerson(Person(id: "", name: name))
            if let photo { photos[p.id] = photo }
            await refresh()
        } catch { lastError = error.localizedDescription }
    }

    func save(_ m: Medication) async -> Bool {
        do {
            _ = try await api.saveMedication(m)
            await refresh()
            return true
        } catch {
            lastError = error.localizedDescription
            return false
        }
    }

    func delete(_ m: Medication) async {
        do {
            try await api.deleteMedication(id: m.id)
            await refresh()
        } catch { lastError = error.localizedDescription }
    }

    // MARK: - Squint

    /// What Squint is showing right now.
    var squint: SquintState {
        if let demoScene { return demoScene }
        if !useDemoData, let live { return live }
        return derivedSquint
    }

    /// Demo mode (or before the station has said anything): work it out from today's doses.
    private var derivedSquint: SquintState {
        let now = ClockTime.nowMinutes
        let dueNow = doses.filter { $0.status == .due && ClockTime.minutes($0.due) <= now }
        if let d = dueNow.first {
            let who = person(d.personID)?.name ?? ""
            let meds = dueNow.filter { $0.personID == d.personID }.compactMap { medication($0.medID)?.name }
            return SquintState(mood: .remind, title: medication(d.medID)?.name ?? "Pill time",
                               detail: "\(who): \(meds.joined(separator: " and "))")
        }
        let hour = now / 60
        if hour >= 22 || hour < 6 { return .asleep }
        if !doses.isEmpty && doses.allSatisfy({ $0.status != .due || ClockTime.minutes($0.due) > now }) &&
            doses.contains(where: { $0.status == .taken }) && attention.isEmpty {
            return SquintState(mood: .happy, title: "All done", detail: "for now")
        }
        return SquintState(mood: .idle)
    }

    /// Live mode: follow the same command stream the Tab5 reads (GET /tab5/commands, long-poll).
    func followStation() async {
        commandSeq = 0
        while !Task.isCancelled && !useDemoData {
            guard let base = URL(string: backendURL) else { return }
            var comps = URLComponents(url: base.appendingPathComponent("tab5/commands"), resolvingAgainstBaseURL: false)
            comps?.queryItems = [URLQueryItem(name: "after", value: String(commandSeq)), URLQueryItem(name: "wait", value: "20")]
            guard let url = comps?.url else { return }
            do {
                let (data, _) = try await URLSession.shared.data(for: URLRequest(url: url, timeoutInterval: 25))
                struct Batch: Decodable { let seq: Int; let lines: [String] }
                let b = try JSONDecoder().decode(Batch.self, from: data)
                commandSeq = b.seq
                liveConnected = true
                if let s = b.lines.compactMap(SquintState.init(line:)).last {
                    live = s
                    await refresh()                 // a new face usually means a dose changed
                }
            } catch {
                liveConnected = false
                try? await Task.sleep(for: .seconds(3))
            }
        }
    }

    /// Margaret's morning in 20 seconds: every face Squint can make, for showing people the app.
    func playDemo() async {
        let scenes: [(SquintState, Double)] = [
            (.asleep, 2),
            (SquintState(mood: .greet, title: "Hi Margaret!"), 2.5),
            (SquintState(mood: .remind, title: "Warfarin", detail: "1 pink pill"), 3),
            (SquintState(mood: .happy, title: "Well done!", detail: "Warfarin"), 2.5),
            (SquintState(mood: .wrong, title: "Robert's pills", detail: "That's Robert's Metoprolol"), 3),
            (SquintState(mood: .concerned, title: "Show me the label"), 2.5),
            (SquintState(mood: .stop, title: "STOP", detail: "Taken at 8:02"), 3.5),
        ]
        for (s, secs) in scenes {
            if Task.isCancelled { break }
            demoScene = s
            try? await Task.sleep(for: .seconds(secs))
        }
        demoScene = nil
    }

    /// "Test voice" and any other announcement from the app.
    func announce(_ text: String) async -> String {
        guard let url = URL(string: homeURL) else { return "That speaker address doesn't look right." }
        do {
            let r = try await HomeSpeaker(base: url).announce(text)
            return "Playing on \(r.speaker ?? "the speaker")."
        } catch {
            return "Couldn't reach the speaker: \(error.localizedDescription)"
        }
    }
}
