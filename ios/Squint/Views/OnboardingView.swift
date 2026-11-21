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
        VStack(alignment: .leading, spacing: 22) {
            Spacer(minLength: 8)
            SquintCard(state: SquintState(mood: .greet, title: "Hi! I'm Squint."))
            VStack(alignment: .leading, spacing: 10) {
                Eyebrow("For the people who worry")
                Text("I'll look after your parents' pills.")
                    .font(Theme.display(32)).foregroundStyle(Theme.ink)
                    .fixedSize(horizontal: false, vertical: true)
                Text("Set me up once: who takes what, and when. After that I greet them at the counter, check every bottle, and only bother you when something's wrong.")
                    .font(.body).foregroundStyle(Theme.muted)
                    .fixedSize(horizontal: false, vertical: true)
            }
            Spacer(minLength: 8)
            Button { step = 1 } label: { Label("Let's set up", systemImage: "arrow.right") }
                .buttonStyle(InkButtonStyle())
        }
        .padding(24)
        .background(Theme.paper.ignoresSafeArea())
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
        .paperBackground()
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
                                       : "Shown on the station's screen, e.g. http://172.20.10.9:8081")
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
        .paperBackground()
        .navigationTitle("Connect")
        .toolbar { Button("Done") { Task { await store.refresh(); done() } } }
    }
}
