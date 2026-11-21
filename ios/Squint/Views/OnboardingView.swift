import PhotosUI
import SwiftUI

/// First launch: who you're caring for, connect the station, then add their medicines.
struct OnboardingView: View {
    @Environment(AppStore.self) private var store
    @State private var step = 0

    var body: some View {
        NavigationStack {
            Group {
                switch step {
                case 0: welcome
                case 1: PeopleStep { step = 2 }
                default: ConnectStep { store.onboarded = true }
                }
            }
            .animation(.default, value: step)
        }
    }

    private var welcome: some View {
        VStack(spacing: 24) {
            Spacer()
            Image(systemName: "heart.text.square.fill")
                .font(.system(size: 72)).foregroundStyle(Theme.accent)
            Text("Set up Squint for your parents")
                .font(.largeTitle.weight(.bold)).multilineTextAlignment(.center)
            Text("About five minutes, once. After that, Squint guides them through every dose and only tells you when something needs you.")
                .font(.title3).foregroundStyle(.secondary).multilineTextAlignment(.center)
            Spacer()
            Button { step = 1 } label: { Text("Get started").frame(maxWidth: .infinity) }
                .buttonStyle(.borderedProminent).controlSize(.large)
        }
        .padding(32)
    }
}

struct PeopleStep: View {
    @Environment(AppStore.self) private var store
    @State private var name = ""
    @State private var photoItem: PhotosPickerItem?
    @State private var photo: Data?
    let next: () -> Void

    var body: some View {
        Form {
            Section {
                ForEach(store.elders) { p in
                    HStack(spacing: 12) { Avatar(person: p, size: 40); Text(p.name).font(.headline) }
                }
            } header: {
                Text("Who are you caring for?")
            } footer: {
                Text("A clear face photo lets the avatar greet each of them by name, and tell their pills apart.")
            }

            Section("Add someone") {
                HStack(spacing: 12) {
                    PhotosPicker(selection: $photoItem, matching: .images) {
                        Group {
                            if let photo, let img = platformImage(photo) {
                                img.resizable().scaledToFill()
                            } else {
                                Image(systemName: "person.crop.circle.badge.plus").font(.title)
                            }
                        }
                        .frame(width: 48, height: 48).clipShape(Circle())
                    }
                    TextField("Name, e.g. Margaret", text: $name).wordsField()
                }
                Button("Add") {
                    let n = name.trimmingCharacters(in: .whitespaces)
                    let p = photo
                    name = ""; photo = nil; photoItem = nil
                    Task { await store.addPerson(name: n, photo: p) }
                }
                .disabled(name.trimmingCharacters(in: .whitespaces).isEmpty)
            }
        }
        .navigationTitle("Your parents")
        .toolbar {
            Button("Next", action: next).disabled(store.elders.isEmpty)
        }
        .onChange(of: photoItem) { _, item in
            Task { photo = try? await item?.loadTransferable(type: Data.self) }
        }
    }
}

struct ConnectStep: View {
    @Environment(AppStore.self) private var store
    @State private var testResult: String?
    @State private var testing = false
    let done: () -> Void

    var body: some View {
        @Bindable var store = store
        Form {
            Section {
                Toggle("Use demo data", isOn: $store.useDemoData)
                if !store.useDemoData {
                    TextField("Station address", text: $store.backendURL).urlField()
                }
            } header: {
                Text("Squint station")
            } footer: {
                Text(store.useDemoData ? "Try everything with Margaret and Robert's example data. Switch it off once the station is running."
                                       : "Shown on the station's screen, e.g. http://192.168.1.10:8000")
            }

            Section {
                TextField("Speaker address", text: $store.homeURL).urlField()
                Button {
                    testing = true
                    Task {
                        testResult = await store.announce("Hello! I'm Squint. I'll help with medicines from now on.")
                        testing = false
                    }
                } label: {
                    Label(testing ? "Saying hello…" : "Test the voice", systemImage: "speaker.wave.2.fill")
                }
                .disabled(testing)
                if let r = testResult { Text(r).font(.footnote).foregroundStyle(.secondary) }
            } header: {
                Text("Google Home")
            } footer: {
                Text("Squint uses your Google Home to call them over when it's time.")
            }
        }
        .navigationTitle("Connect")
        .toolbar { Button("Done") { Task { await store.refresh(); done() } } }
    }
}
