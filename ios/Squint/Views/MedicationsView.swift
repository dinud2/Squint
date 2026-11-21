import SwiftUI

struct MedicationsView: View {
    @Environment(AppStore.self) private var store
    @State private var editing: Medication?
    @State private var adding = false

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 22) {
                    HStack(alignment: .bottom) {
                        VStack(alignment: .leading, spacing: 4) {
                            Eyebrow("\(store.medications.count) on file")
                            Text("Medicines").font(Theme.display(34)).foregroundStyle(Theme.ink)
                        }
                        Spacer()
                        Button { adding = true } label: {
                            Image(systemName: "plus").font(.system(size: 18, weight: .heavy))
                                .foregroundStyle(Theme.paper)
                                .frame(width: 46, height: 46)
                                .background(Theme.ink, in: Circle())
                        }
                        .accessibilityLabel("Add a medicine")
                    }
                    .padding(.top, 12)

                    ForEach(store.elders) { p in
                        let meds = store.medications.filter { $0.personID == p.id }
                        VStack(alignment: .leading, spacing: 4) {
                            HStack(spacing: 10) {
                                Avatar(person: p, size: 34)
                                Text(p.name).font(Theme.display(20, .bold)).foregroundStyle(Theme.ink)
                                Spacer()
                                Text("\(meds.count)").font(Theme.display(15, .bold)).foregroundStyle(Theme.muted)
                            }
                            .padding(.bottom, 6)
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

                    Text("Tap a medicine to change it. Squint picks up changes straight away.")
                        .font(.footnote).foregroundStyle(Theme.muted)
                        .padding(.horizontal, 6)
                }
                .padding(.horizontal, 20).padding(.bottom, 24)
            }
            .background(Theme.paper.ignoresSafeArea())
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
        HStack(alignment: .top, spacing: 14) {
            ZStack {
                RoundedRectangle(cornerRadius: 12, style: .continuous)
                    .fill(med.risk == .high ? Theme.flagged.opacity(0.12) : Theme.line)
                PillGlyph(status: med.risk == .high ? .flagged : .taken, width: 24)
                    .saturation(med.risk == .high ? 1 : 0)
            }
            .frame(width: 44, height: 44)
            VStack(alignment: .leading, spacing: 6) {
                HStack(spacing: 6) {
                    Text(med.name).font(.body.weight(.bold)).foregroundStyle(Theme.ink)
                    if !med.strength.isEmpty { Text(med.strength).font(.subheadline).foregroundStyle(Theme.muted) }
                }
                FlowRow(spacing: 6) {
                    ForEach(med.times, id: \.self) { t in
                        Text(ClockTime.display(t))
                            .font(.system(size: 12, weight: .bold, design: .rounded))
                            .foregroundStyle(Theme.ink)
                            .padding(.horizontal, 9).padding(.vertical, 4)
                            .overlay(Capsule().strokeBorder(Theme.ink.opacity(0.2)))
                    }
                    if med.risk == .high {
                        Label("Extra careful", systemImage: "exclamationmark.shield.fill")
                            .font(.system(size: 12, weight: .bold, design: .rounded))
                            .foregroundStyle(Theme.flagged)
                            .padding(.horizontal, 9).padding(.vertical, 4)
                            .background(Theme.flagged.opacity(0.1), in: Capsule())
                    }
                }
                if !med.notes.isEmpty {
                    Text(med.notes).font(.footnote).foregroundStyle(Theme.muted)
                }
            }
            Spacer(minLength: 0)
            Image(systemName: "chevron.right").font(.footnote.weight(.bold)).foregroundStyle(Theme.muted.opacity(0.6))
                .padding(.top, 4)
        }
        .padding(.vertical, 10)
        .contentShape(Rectangle())
        .accessibilityElement(children: .combine)
    }
}
