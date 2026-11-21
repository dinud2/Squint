import SwiftUI

struct MedicationsView: View {
    @Environment(AppStore.self) private var store
    @State private var editing: Medication?
    @State private var adding = false

    var body: some View {
        NavigationStack {
            List {
                ForEach(store.elders) { p in
                    Section {
                        let meds = store.medications.filter { $0.personID == p.id }
                        if meds.isEmpty {
                            Text("Nothing yet").foregroundStyle(.secondary)
                        }
                        ForEach(meds) { m in
                            Button { editing = m } label: { MedicationRow(med: m) }
                                .buttonStyle(.plain)
                        }
                        .onDelete { idx in
                            let doomed = idx.map { meds[$0] }
                            Task { for m in doomed { await store.delete(m) } }
                        }
                    } header: {
                        HStack { Avatar(person: p, size: 24); Text(p.name) }
                    }
                }
            }
            .navigationTitle("Medications")
            .toolbar {
                Button { adding = true } label: { Label("Add", systemImage: "plus") }
            }
            .sheet(isPresented: $adding) { AddMedicationView() }
            .sheet(item: $editing) { AddMedicationView(existing: $0) }
            .refreshable { await store.refresh() }
        }
    }
}

struct MedicationRow: View {
    let med: Medication

    var body: some View {
        HStack(spacing: 12) {
            Image(systemName: med.risk == .high ? "exclamationmark.shield.fill" : "pills.fill")
                .foregroundStyle(med.risk == .high ? Theme.flagged : Theme.accent)
                .frame(width: 28)
            VStack(alignment: .leading, spacing: 2) {
                Text("\(med.name) \(med.strength)").font(.body.weight(.medium))
                Text(med.times.map(ClockTime.display).joined(separator: ", "))
                    .font(.subheadline).foregroundStyle(.secondary)
                if !med.notes.isEmpty {
                    Text(med.notes).font(.caption).foregroundStyle(.secondary)
                }
            }
            Spacer()
        }
        .contentShape(Rectangle())
    }
}
