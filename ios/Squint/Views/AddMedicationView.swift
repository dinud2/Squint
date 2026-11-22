import PhotosUI
import SwiftUI

/// The one-time setup for a medicine: scan the label, confirm, pick times, done.
struct AddMedicationView: View {
    @Environment(AppStore.self) private var store
    @Environment(\.dismiss) private var dismiss

    @State private var med: Medication
    @State private var newTime = ClockTime.date("08:00")
    @State private var labelItem: PhotosPickerItem?
    @State private var bottleItems: [PhotosPickerItem] = []
    @State private var showCamera = false
    @State private var scanning = false
    @State private var scanNote: String?
    @State private var saving = false
    private let isNew: Bool

    init(existing: Medication? = nil) {
        isNew = existing == nil
        _med = State(initialValue: existing ?? Medication(id: "", name: "", strength: "", personID: "", times: []))
    }

    var body: some View {
        @Bindable var store = store
        NavigationStack {
            Form {
                if isNew { scanSection }

                Section("Medicine") {
                    TextField("Name, e.g. Warfarin", text: $med.name).wordsField()
                    TextField("Strength, e.g. 5 mg", text: $med.strength)
                    TextField("Notes, e.g. with food", text: $med.notes, axis: .vertical)
                }

                Section("Who takes it") {
                    Picker("For", selection: $med.personID) {
                        Text("Choose…").tag("")
                        ForEach(store.elders) { Text($0.name).tag($0.id) }
                    }
                }

                Section {
                    if !med.times.isEmpty { TimeChips(times: $med.times) }
                    HStack {
                        ForEach([("Morning", "08:00"), ("Noon", "12:00"), ("Evening", "18:00"), ("Bedtime", "21:00")], id: \.1) { label, t in
                            Button(label) { addTime(t) }
                                .buttonStyle(.bordered)
                                .font(.footnote)
                                .disabled(med.times.contains(t))
                        }
                    }
                    HStack {
                        DatePicker("Other time", selection: $newTime, displayedComponents: .hourAndMinute)
                        Button("Add") { addTime(ClockTime.from(newTime)) }
                    }
                } header: {
                    Text("When")
                }

                Section {
                    Toggle(isOn: Binding(get: { med.risk == .high }, set: { med.risk = $0 ? .high : .normal })) {
                        VStack(alignment: .leading) {
                            Text("Extra careful")
                            Text("Never allow a second dose the same day (blood thinners, opioids, insulin…)")
                                .font(.caption).foregroundStyle(.secondary)
                        }
                    }
                }

                Section {
                    PhotosPicker(selection: $bottleItems, maxSelectionCount: 4, matching: .images) {
                        Label(med.bottlePhotos.isEmpty ? "Add photos of the bottle" : "Change bottle photos",
                              systemImage: "camera.on.rectangle")
                    }
                    if !med.bottlePhotos.isEmpty {
                        ScrollView(.horizontal) {
                            HStack {
                                ForEach(med.bottlePhotos.indices, id: \.self) { i in
                                    platformImage(med.bottlePhotos[i])?.resizable().scaledToFill()
                                        .frame(width: 64, height: 64).clipShape(RoundedRectangle(cornerRadius: 10))
                                }
                            }
                        }
                    }
                } header: {
                    Text("Bottle")
                } footer: {
                    Text("A few photos from different sides help the avatar recognise this bottle.")
                }
            }
            .paperBackground()
            .navigationTitle(isNew ? "Add medicine" : med.name)
            .inlineTitle()
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button("Cancel") { dismiss() } }
                ToolbarItem(placement: .confirmationAction) {
                    Button(saving ? "Saving…" : "Save") { save() }.disabled(!canSave || saving)
                }
                if !isNew {
                    ToolbarItem(placement: .destructiveAction) {
                        Button("Delete", role: .destructive) {
                            Task { await store.delete(med); dismiss() }
                        }
                    }
                }
            }
            .onChange(of: labelItem) { _, item in Task { await readLabel(item) } }
            .onChange(of: bottleItems) { _, items in Task { await loadBottles(items) } }
            .onAppear { if med.personID.isEmpty, store.elders.count == 1 { med.personID = store.elders[0].id } }
            #if os(iOS)
            .sheet(isPresented: $showCamera) {
                CameraPicker { data in Task { await scan(data) } }.ignoresSafeArea()
            }
            #endif
        }
    }

    // MARK: - label scanning

    private var scanSection: some View {
        Section {
            #if os(iOS)
            if CameraPicker.isAvailable {
                Button { showCamera = true } label: { Label("Scan the pharmacy label", systemImage: "camera.viewfinder") }
            }
            #endif
            PhotosPicker(selection: $labelItem, matching: .images) {
                Label("Use a photo of the label", systemImage: "photo")
            }
            if scanning {
                HStack { ProgressView(); Text("Reading the label…") }
            } else if let note = scanNote {
                Text(note).font(.footnote).foregroundStyle(.secondary)
            }
        } footer: {
            Text("We fill in the name, strength and times for you. Check them before saving.")
        }
    }

    private func readLabel(_ item: PhotosPickerItem?) async {
        guard let item, let data = try? await item.loadTransferable(type: Data.self) else { return }
        await scan(data)
    }

    private func scan(_ data: Data) async {
        scanning = true
        defer { scanning = false }
        let lines = await LabelParser.readText(from: data)
        guard !lines.isEmpty else {
            scanNote = "Couldn't read any text. Try a sharper, closer photo."
            return
        }
        let p = LabelParser.parse(lines)
        if !p.name.isEmpty { med.name = p.name }
        if !p.strength.isEmpty { med.strength = p.strength }
        if !p.times.isEmpty { med.times = p.times }
        if !p.notes.isEmpty { med.notes = p.notes.joined(separator: ". ") }
        if med.bottlePhotos.isEmpty { med.bottlePhotos = [data] }
        scanNote = p.name.isEmpty ? "Read the label, but couldn't find the medicine name. Please type it."
                                  : "Filled in from the label. Please check."
    }

    private func loadBottles(_ items: [PhotosPickerItem]) async {
        var out: [Data] = []
        for i in items { if let d = try? await i.loadTransferable(type: Data.self) { out.append(d) } }
        if !out.isEmpty { med.bottlePhotos = out }
    }

    // MARK: - saving

    private var canSave: Bool { !med.name.trimmingCharacters(in: .whitespaces).isEmpty && !med.personID.isEmpty && !med.times.isEmpty }

    private func addTime(_ t: String) {
        if !med.times.contains(t) { med.times.append(t) }
        med.times.sort { ClockTime.minutes($0) < ClockTime.minutes($1) }
    }

    private func save() {
        saving = true
        Task {
            if await store.save(med) { dismiss() }
            saving = false
        }
    }
}

#if os(iOS)
import UIKit

/// The iPhone camera, for photographing a label. (Not available in the simulator: use a photo instead.)
struct CameraPicker: UIViewControllerRepresentable {
    static var isAvailable: Bool { UIImagePickerController.isSourceTypeAvailable(.camera) }
    let onPhoto: (Data) -> Void
    @Environment(\.dismiss) private var dismiss

    func makeUIViewController(context: Context) -> UIImagePickerController {
        let c = UIImagePickerController()
        c.sourceType = .camera
        c.delegate = context.coordinator
        return c
    }

    func updateUIViewController(_ c: UIImagePickerController, context: Context) {}
    func makeCoordinator() -> Coordinator { Coordinator(self) }

    final class Coordinator: NSObject, UIImagePickerControllerDelegate, UINavigationControllerDelegate {
        let parent: CameraPicker
        init(_ p: CameraPicker) { parent = p }

        func imagePickerController(_ picker: UIImagePickerController,
                                   didFinishPickingMediaWithInfo info: [UIImagePickerController.InfoKey: Any]) {
            if let img = info[.originalImage] as? UIImage, let data = img.jpegData(compressionQuality: 0.9) {
                parent.onPhoto(data)
            }
            parent.dismiss()
        }

        func imagePickerControllerDidCancel(_ picker: UIImagePickerController) { parent.dismiss() }
    }
}
#endif
