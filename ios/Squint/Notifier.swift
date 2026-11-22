import Foundation
import UserNotifications

/// Tells the caregiver, as a phone notification, when a dose changes: taken, missed, or
/// flagged (Squint stopped a double dose or a mix-up).
///
/// It works by comparing each new GET /today with the last one it saw. The app checks the
/// station live while it's open (the Tab5 command stream, plus a refresh every 30 s), and iOS
/// wakes it now and then in the background to check again. Without a push server, a phone that
/// hasn't opened the app in a while hears about it at the next background check, not instantly.
@MainActor
final class Notifier: NSObject, UNUserNotificationCenterDelegate {
    static let shared = Notifier()

    private let center = UNUserNotificationCenter.current()
    private let defaults = UserDefaults.standard
    private let seenKey = "notifier.seen"          // dose id -> status, for today
    private let dayKey = "notifier.day"

    /// "Every dose taken" can be turned off in Settings; problems are always sent.
    var notifyTaken: Bool {
        get { defaults.object(forKey: "notifyTaken") as? Bool ?? true }
        set { defaults.set(newValue, forKey: "notifyTaken") }
    }

    func start() {
        center.delegate = self
    }

    func requestPermission() async {
        _ = try? await center.requestAuthorization(options: [.alert, .sound, .badge])
    }

    /// Compare today's doses with the last ones seen and send one notification per change.
    /// The first look on a new day only records what's there, so opening the app doesn't
    /// replay the whole morning.
    func update(doses: [Dose], people: [Person], medications: [Medication]) {
        let today = ClockTime.dayKey(Date())
        var seen = defaults.dictionary(forKey: seenKey) as? [String: String] ?? [:]
        let firstLook = defaults.string(forKey: dayKey) != today
        if firstLook { seen = [:] }

        for d in doses {
            let before = seen[d.id].flatMap(Dose.Status.init(rawValue:))
            seen[d.id] = d.status.rawValue
            guard !firstLook, before != d.status else { continue }
            // a dose we've never seen (a new medication) only counts if it's already a problem
            if before == nil && !d.needsAttention { continue }
            let who = people.first { $0.id == d.personID }?.name ?? "Someone"
            let med = medications.first { $0.id == d.medID }?.name ?? "a medicine"
            send(dose: d, who: who, med: med)
        }
        defaults.set(seen, forKey: seenKey)
        defaults.set(today, forKey: dayKey)
    }

    private func send(dose d: Dose, who: String, med: String) {
        let c = UNMutableNotificationContent()
        c.threadIdentifier = d.personID                  // one stack per person
        c.sound = .default
        switch d.status {
        case .taken:
            guard notifyTaken else { return }
            c.title = "\(who) took \(med)"
            c.body = "At \(ClockTime.display(d.at ?? d.due)). Squint saw it."
            c.interruptionLevel = .passive              // good news: into the list, no buzz
            c.sound = nil
        case .flagged:
            c.title = "Squint stepped in for \(who)"
            c.body = d.reason ?? "\(med): Squint stopped a dose at \(ClockTime.display(d.at ?? d.due)). Worth a call."
            c.interruptionLevel = .timeSensitive
        case .missed:
            c.title = "\(who) missed \(med)"
            c.body = d.reason ?? "It was due at \(ClockTime.display(d.due)) and hasn't been taken."
            c.interruptionLevel = .timeSensitive
        case .due:
            return
        }
        post(c, id: "\(ClockTime.dayKey(Date()))/\(d.id)/\(d.status.rawValue)")
    }

    /// For "Play a demo": the notifications Maya would get during Margaret's morning.
    func demo(title: String, body: String, urgent: Bool) {
        let c = UNMutableNotificationContent()
        c.title = title
        c.body = body
        c.sound = urgent ? .default : nil
        c.interruptionLevel = urgent ? .timeSensitive : .active
        post(c, id: "demo/\(UUID().uuidString)")
    }

    private func post(_ c: UNMutableNotificationContent, id: String) {
        center.add(UNNotificationRequest(identifier: id, content: c, trigger: nil))
    }

    // Show the banner even when the app is open.
    nonisolated func userNotificationCenter(_ center: UNUserNotificationCenter, willPresent notification: UNNotification)
        async -> UNNotificationPresentationOptions {
        [.banner, .list, .sound]
    }
}

extension ClockTime {
    static func dayKey(_ date: Date) -> String {
        let c = Calendar.current.dateComponents([.year, .month, .day], from: date)
        return "\(c.year ?? 0)-\(c.month ?? 0)-\(c.day ?? 0)"
    }
}
