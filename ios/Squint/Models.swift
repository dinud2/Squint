import Foundation

// The three things the app knows about. Field names on the wire are in docs/api-contract.md;
// CodingKeys map them to Swift names.

nonisolated struct Person: Identifiable, Codable, Hashable {
    enum Role: String, Codable { case elder, caregiver }

    var id: String
    var name: String
    var role: Role = .elder
    var photoURL: String? = nil
    var photo: Data? = nil            // kept on the phone for now (not sent to the backend yet)

    enum CodingKeys: String, CodingKey { case id, name, role, photoURL = "photo_url" }

    var initials: String {
        name.split(separator: " ").prefix(2).compactMap(\.first).map(String.init).joined().uppercased()
    }
}

nonisolated struct Medication: Identifiable, Codable, Hashable {
    enum Risk: String, Codable, CaseIterable { case normal, high }

    var id: String
    var name: String
    var strength: String
    var personID: String
    var times: [String]               // "08:00", 24-hour
    var notes: String = ""
    var risk: Risk = .normal
    var bottlePhotos: [Data] = []     // kept on the phone for now

    enum CodingKeys: String, CodingKey { case id, name, strength, personID = "for", times, notes, risk }
}

nonisolated struct Dose: Identifiable, Codable, Hashable {
    enum Status: String, Codable { case due, taken, missed, flagged }

    var medID: String
    var personID: String
    var due: String                   // "08:00"
    var status: Status
    var at: String? = nil             // when it was taken, "08:02"
    var reason: String? = nil

    var id: String { "\(personID)/\(medID)/\(due)" }
    var needsAttention: Bool { status == .missed || status == .flagged }

    enum CodingKeys: String, CodingKey { case medID = "med", personID = "for", due, status, at, reason }
}

// MARK: - time helpers ("08:00" <-> "8:00 AM")

nonisolated enum ClockTime {
    static func minutes(_ hhmm: String) -> Int {
        let p = hhmm.split(separator: ":").compactMap { Int($0) }
        return p.count == 2 ? p[0] * 60 + p[1] : 0
    }

    static func string(_ minutes: Int) -> String {
        String(format: "%02d:%02d", (minutes / 60) % 24, minutes % 60)
    }

    static func display(_ hhmm: String) -> String {
        let m = minutes(hhmm)
        let h = m / 60, mm = m % 60
        let h12 = h % 12 == 0 ? 12 : h % 12
        return mm == 0 ? "\(h12) \(h < 12 ? "AM" : "PM")" : String(format: "%d:%02d %@", h12, mm, h < 12 ? "AM" : "PM")
    }

    static func from(_ date: Date) -> String {
        let c = Calendar.current.dateComponents([.hour, .minute], from: date)
        return string((c.hour ?? 0) * 60 + (c.minute ?? 0))
    }

    static func date(_ hhmm: String) -> Date {
        let m = minutes(hhmm)
        return Calendar.current.date(bySettingHour: m / 60, minute: m % 60, second: 0, of: Date()) ?? Date()
    }

    static var nowMinutes: Int { minutes(from(Date())) }
}

nonisolated func slug(_ s: String) -> String {
    let allowed = s.lowercased().map { $0.isLetter || $0.isNumber ? $0 : "_" }
    return String(allowed).split(separator: "_").joined(separator: "_")
}
