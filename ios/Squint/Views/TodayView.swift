import SwiftUI

/// The screen the caregiver opens: is everyone okay today?
struct TodayView: View {
    @Environment(AppStore.self) private var store

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 16) {
                    summary
                    ForEach(store.attention) { AttentionCard(dose: $0) }
                    ForEach(store.elders) { PersonCard(person: $0) }
                    if let err = store.lastError {
                        Label(err, systemImage: "wifi.exclamationmark")
                            .font(.footnote).foregroundStyle(.secondary)
                    }
                }
                .padding()
            }
            .navigationTitle(Date().formatted(.dateTime.weekday(.wide).month().day()))
            .refreshable { await store.refresh() }
            .task {
                // keep it live: the station updates doses as they happen
                while !Task.isCancelled {
                    try? await Task.sleep(for: .seconds(15))
                    await store.refresh()
                }
            }
        }
    }

    private var summary: some View {
        let taken = store.doses.filter { $0.status == .taken || $0.status == .flagged }.count
        let issues = store.attention.count
        return VStack(alignment: .leading, spacing: 4) {
            Text(issues == 0 ? "All good so far" : issues == 1 ? "1 thing needs you" : "\(issues) things need you")
                .font(.title2.weight(.semibold))
            Text("\(taken) of \(store.doses.count) doses taken today")
                .foregroundStyle(.secondary)
        }
    }
}

struct AttentionCard: View {
    @Environment(AppStore.self) private var store
    let dose: Dose

    var body: some View {
        let who = store.person(dose.personID)?.name ?? dose.personID
        let med = store.medication(dose.medID)?.name ?? dose.medID
        HStack(alignment: .top, spacing: 12) {
            Image(systemName: Theme.icon(dose.status))
                .font(.title2).foregroundStyle(Theme.color(dose.status))
            VStack(alignment: .leading, spacing: 4) {
                Text(dose.status == .missed ? "\(who) missed \(med) (\(ClockTime.display(dose.due)))"
                                            : "\(who): \(med) at \(ClockTime.display(dose.due))")
                    .font(.headline)
                if let r = dose.reason { Text(r).font(.subheadline).foregroundStyle(.secondary) }
            }
            Spacer(minLength: 0)
        }
        .padding()
        .background(Theme.color(dose.status).opacity(0.1), in: RoundedRectangle(cornerRadius: 16))
    }
}

struct PersonCard: View {
    @Environment(AppStore.self) private var store
    let person: Person

    var body: some View {
        let doses = store.doses(for: person)
        let done = doses.filter { $0.status == .taken || $0.status == .flagged }.count
        VStack(alignment: .leading, spacing: 12) {
            HStack(spacing: 12) {
                Avatar(person: person, size: 48)
                VStack(alignment: .leading) {
                    Text(person.name).font(.title3.weight(.semibold))
                    Text(doses.isEmpty ? "No medications yet" : "\(done) of \(doses.count) taken")
                        .font(.subheadline).foregroundStyle(.secondary)
                }
                Spacer()
                if !doses.isEmpty {
                    Gauge(value: Double(done), in: 0...Double(doses.count)) { EmptyView() }
                        .gaugeStyle(.accessoryCircularCapacity)
                        .tint(Theme.taken)
                        .scaleEffect(0.7)
                }
            }
            ForEach(doses) { d in
                Divider()
                HStack {
                    VStack(alignment: .leading, spacing: 2) {
                        Text(store.medication(d.medID)?.name ?? d.medID).font(.body.weight(.medium))
                        Text([store.medication(d.medID)?.strength, ClockTime.display(d.due)]
                                .compactMap { $0 }.joined(separator: " · "))
                            .font(.subheadline).foregroundStyle(.secondary)
                    }
                    Spacer()
                    StatusLabel(dose: d)
                }
            }
        }
        .padding()
        .background(Theme.card, in: RoundedRectangle(cornerRadius: 20))
    }
}
