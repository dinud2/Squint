import Foundation
import Observation

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
    private var photos: [String: Data] = [:]          // person id -> face photo (phone only for now)

    init() {
        let d = UserDefaults.standard
        useDemoData = d.object(forKey: "useDemoData") as? Bool ?? true
        backendURL = d.string(forKey: "backendURL") ?? "http://192.168.1.10:8000"
        homeURL = d.string(forKey: "homeURL") ?? "http://192.168.1.10:8765"
        onboarded = d.bool(forKey: "onboarded")
    }

    private func save() {
        let d = UserDefaults.standard
        d.set(useDemoData, forKey: "useDemoData")
        d.set(backendURL, forKey: "backendURL")
        d.set(homeURL, forKey: "homeURL")
        d.set(onboarded, forKey: "onboarded")
    }

    var api: SquintAPI {
        if !useDemoData, let url = URL(string: backendURL) { return LiveAPI(base: url) }
        return MockAPI.shared
    }

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
            people = ppl
            medications = try await m
            doses = try await t
            lastError = nil
            lastRefresh = Date()
        } catch {
            lastError = error.localizedDescription
        }
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
