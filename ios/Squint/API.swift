import Foundation

/// Everything the app asks the backend. Two versions: MockAPI (fake data on the phone, works today)
/// and LiveAPI (the real server, docs/api-contract.md). The rest of the app can't tell them apart.
protocol SquintAPI: Sendable {
    func people() async throws -> [Person]
    func addPerson(_ p: Person) async throws -> Person
    func medications() async throws -> [Medication]
    func saveMedication(_ m: Medication) async throws -> Medication
    func deleteMedication(id: String) async throws
    func today() async throws -> [Dose]
}

nonisolated struct APIError: LocalizedError {
    let message: String
    var errorDescription: String? { message }
}

// MARK: - Mock

/// Margaret and Robert, a few meds each, and a "today" that follows the real clock:
/// doses before now are taken (one missed, one flagged), later ones are still due.
actor MockAPI: SquintAPI {
    static let shared = MockAPI()

    private var ppl: [Person] = [
        Person(id: "margaret", name: "Margaret"),
        Person(id: "robert", name: "Robert"),
    ]
    private var meds: [Medication] = [
        Medication(id: "warfarin", name: "Warfarin", strength: "5 mg", personID: "margaret", times: ["08:00"],
                   notes: "Blood thinner. Never a second dose.", risk: .high),
        Medication(id: "metformin", name: "Metformin", strength: "500 mg", personID: "margaret",
                   times: ["08:00", "18:00"], notes: "With food"),
        Medication(id: "vitamin_d", name: "Vitamin D", strength: "1000 IU", personID: "margaret", times: ["12:00"]),
        Medication(id: "metoprolol", name: "Metoprolol", strength: "25 mg", personID: "robert", times: ["08:00", "20:00"]),
        Medication(id: "atorvastatin", name: "Atorvastatin", strength: "20 mg", personID: "robert", times: ["21:00"]),
    ]

    func people() async throws -> [Person] { ppl }

    func addPerson(_ p: Person) async throws -> Person {
        var p = p
        p.id = unique(slug(p.name), in: ppl.map(\.id))
        ppl.append(p)
        return p
    }

    func medications() async throws -> [Medication] { meds }

    func saveMedication(_ m: Medication) async throws -> Medication {
        var m = m
        if let i = meds.firstIndex(where: { $0.id == m.id }) {
            meds[i] = m
        } else {
            m.id = unique(slug(m.name), in: meds.map(\.id))
            meds.append(m)
        }
        return m
    }

    func deleteMedication(id: String) async throws { meds.removeAll { $0.id == id } }

    func today() async throws -> [Dose] {
        let now = ClockTime.nowMinutes
        var out: [Dose] = []
        for m in meds {
            for t in m.times {
                let due = ClockTime.minutes(t)
                var d = Dose(medID: m.id, personID: m.personID, due: t, status: .due)
                if now > due + 45 {                       // the dose window has closed
                    if m.id == "vitamin_d" {
                        d.status = .missed
                        d.reason = "Margaret didn't come for her noon pill. Squint reminded her twice."
                    } else if m.id == "metoprolol" && t == "08:00" {
                        d.status = .flagged
                        d.at = ClockTime.string(due + 6)
                        d.reason = "Robert picked up Margaret's Warfarin first. Squint caught it and pointed him to his own bottle."
                    } else {
                        d.status = .taken
                        // a few minutes late, the same every time (hashValue changes per launch)
                        d.at = ClockTime.string(due + m.id.unicodeScalars.reduce(0) { $0 + Int($1.value) } % 9 + 1)
                    }
                }
                out.append(d)
            }
        }
        return out.sorted { ($0.due, $0.personID) < ($1.due, $1.personID) }
    }

    private func unique(_ base: String, in ids: [String]) -> String {
        var id = base.isEmpty ? "item" : base, n = 2
        while ids.contains(id) { id = "\(base)_\(n)"; n += 1 }
        return id
    }
}

// MARK: - Live

nonisolated struct LiveAPI: SquintAPI {
    let base: URL

    func people() async throws -> [Person] { try await get("people") }
    func addPerson(_ p: Person) async throws -> Person { try await send("POST", "people", p) }
    func medications() async throws -> [Medication] { try await get("medications") }

    func saveMedication(_ m: Medication) async throws -> Medication {
        m.id.isEmpty ? try await send("POST", "medications", m) : try await send("PUT", "medications/\(m.id)", m)
    }

    func deleteMedication(id: String) async throws {
        _ = try await request("DELETE", "medications/\(id)", body: nil as Data?)
    }

    func today() async throws -> [Dose] { try await get("today") }

    // ---- plumbing
    private func get<T: Decodable>(_ path: String) async throws -> T {
        try JSONDecoder().decode(T.self, from: try await request("GET", path, body: nil as Data?))
    }

    private func send<B: Encodable, T: Decodable>(_ method: String, _ path: String, _ body: B) async throws -> T {
        try JSONDecoder().decode(T.self, from: try await request(method, path, body: try JSONEncoder().encode(body)))
    }

    private func request(_ method: String, _ path: String, body: Data?) async throws -> Data {
        var req = URLRequest(url: base.appendingPathComponent(path), timeoutInterval: 8)
        req.httpMethod = method
        if let body {
            req.httpBody = body
            req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        }
        let (data, resp) = try await URLSession.shared.data(for: req)
        guard let http = resp as? HTTPURLResponse else { throw APIError(message: "No response from the station") }
        guard (200..<300).contains(http.statusCode) else {
            let msg = (try? JSONDecoder().decode([String: String].self, from: data))?["error"]
            throw APIError(message: msg ?? "The station answered \(http.statusCode)")
        }
        return data
    }
}

// MARK: - Google Home (home/server.py)

nonisolated struct HomeSpeaker {
    struct Result: Decodable { let ok: Bool?; let speaker: String?; let seconds: Double?; let error: String? }

    let base: URL

    /// Says `text` out loud on the Nest (or the laptop, if the server runs with --local).
    func announce(_ text: String) async throws -> Result {
        var req = URLRequest(url: base.appendingPathComponent("announce"), timeoutInterval: 20)
        req.httpMethod = "POST"
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        req.httpBody = try JSONEncoder().encode(["text": text])
        let (data, _) = try await URLSession.shared.data(for: req)
        let r = try JSONDecoder().decode(Result.self, from: data)
        if let e = r.error { throw APIError(message: e) }
        return r
    }
}
