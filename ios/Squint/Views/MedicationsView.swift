import SwiftUI

struct MedicationsView: View {
    @Environment(AppStore.self) private var store
    @State private var editing: Medication?
    @State private var adding = false

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: Space.section) {
                    ZStack {
                        Text("Medicines").font(Theme.display(24, .semibold)).foregroundStyle(Theme.ink)
                        HStack {
                            Spacer()
                            Button { adding = true } label: {
                                Image(systemName: "plus").font(.system(size: 18, weight: .semibold))
                                    .foregroundStyle(.white)
                                    .frame(width: 46, height: 46)
                                    .background(Theme.accent, in: Circle())
                            }
                            .accessibilityLabel("Add a medicine")
                        }
                    }
                    .padding(.top, 8)

                    ForEach(store.elders) { p in
                        let meds = store.medications.filter { $0.personID == p.id }
                        VStack(alignment: .leading, spacing: 0) {
                            HStack(spacing: 12) {
                                Avatar(person: p, size: 42)
                                Text(p.name).font(Theme.display(21, .semibold)).foregroundStyle(Theme.ink)
                                Spacer()
                            }
                            .padding(.bottom, 8)
                            if meds.isEmpty {
                                Button { adding = true } label: {
                                    Label("Add \(p.name)'s first medicine", systemImage: "plus")
                                        .font(.subheadline.weight(.semibold)).foregroundStyle(Theme.muted)
                                        .frame(maxWidth: .infinity, alignment: .leading).padding(.vertical, 10)
                                }
                            }
                            ForEach(meds) { m in
                                Button { editing = m } label: { MedicationRow(med: m) }
                                    .buttonStyle(.plain)
                                    .contextMenu {
                                        Button("Edit", systemImage: "pencil") { editing = m }
                                        Button("Delete", systemImage: "trash", role: .destructive) {
                                            Task { await store.delete(m) }
                                        }
                                    }
                                if m.id != meds.last?.id { Divider().overlay(Theme.line) }
                            }
                        }
                        .paperCard()
                    }
                }
                .padding(.horizontal, 20).padding(.bottom, 24)
            }
            .statusBarFade()
            .background(PageBackground())
            .toolbar(.hidden, for: .navigationBar)
            .sheet(isPresented: $adding) { AddMedicationView() }
            .sheet(item: $editing) { AddMedicationView(existing: $0) }
            .refreshable { await store.refresh() }
        }
    }
}

struct MedicationRow: View {
    let med: Medication

    var body: some View {
        // Two lines: the medicine, then when. Notes and other details are one tap away.
        HStack(alignment: .center, spacing: 16) {
            // The pill in its person's colour, so each person's medicines are easy to pick out.
            let c = Theme.personColor(med.personID)
            PillGlyph(status: .taken, width: 22, tint: c)
                .frame(width: 46, height: 46)
                .background(c.opacity(0.14), in: Circle())
            VStack(alignment: .leading, spacing: 3) {
                HStack(alignment: .firstTextBaseline, spacing: 6) {
                    Text(med.name).font(Theme.display(19, .semibold)).foregroundStyle(Theme.ink)
                    if !med.strength.isEmpty { Text(med.strength).font(.subheadline).foregroundStyle(Theme.muted) }
                    if med.risk == .high {
                        Image(systemName: "exclamationmark.shield.fill")
                            .font(.subheadline).foregroundStyle(Theme.flagged)
                            .accessibilityLabel("Extra careful")
                    }
                }
                Text(schedule).font(.system(size: 14, design: .rounded)).foregroundStyle(Theme.muted)
            }
            Spacer(minLength: 0)
            Image(systemName: "chevron.right").font(.footnote.weight(.bold)).foregroundStyle(Theme.muted.opacity(0.6))
        }
        .padding(.vertical, Space.row)
        .frame(minHeight: Space.rowMinHeight)
        .contentShape(Rectangle())
        .accessibilityElement(children: .combine)
    }

    /// "Daily, 9 PM" or "Daily, 8 AM and 6 PM"
    private var schedule: String {
        let times = med.times.sorted { ClockTime.minutes($0) < ClockTime.minutes($1) }.map { ClockTime.display($0) }
        return times.isEmpty ? "As needed" : "Daily, " + times.formatted(.list(type: .and))
    }
}
