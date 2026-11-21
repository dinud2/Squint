import SwiftUI

struct SettingsView: View {
    @Environment(AppStore.self) private var store
    @State private var message = "Good morning! It's time for your morning pills. Take your time."
    @State private var result: String?
    @State private var sending = false

    var body: some View {
        @Bindable var store = store
        NavigationStack {
            Form {
                Section {
                    HStack(spacing: 14) {
                        SquintBadge(mood: store.useDemoData ? .idle : (store.liveConnected ? store.squint.mood : .sleep), size: 40)
                        VStack(alignment: .leading, spacing: 2) {
                            Text("Squint").font(Theme.display(20, .bold))
                            Text(store.useDemoData ? "Showing demo data" : store.liveConnected ? "Connected to the station" : "Looking for the station…")
                                .font(.subheadline).foregroundStyle(Theme.muted)
                        }
                    }
                    .padding(.vertical, 4)
                }

                Section("People") {
                    ForEach(store.elders) { p in
                        HStack(spacing: 12) { Avatar(person: p, size: 32); Text(p.name) }
                    }
                }

                Section {
                    Toggle("Use demo data", isOn: $store.useDemoData)
                        .onChange(of: store.useDemoData) { Task { await store.refresh() } }
                    if !store.useDemoData {
                        TextField("Station address", text: $store.backendURL).urlField()
                            .onSubmit { Task { await store.refresh() } }
                    }
                    if let t = store.lastRefresh {
                        Text("Last updated \(t.formatted(date: .omitted, time: .shortened))")
                            .font(.footnote).foregroundStyle(.secondary)
                    }
                } header: {
                    Text("Station")
                }

                Section {
                    TextField("Speaker address", text: $store.homeURL).urlField()
                    TextField("Message", text: $message, axis: .vertical)
                    Button {
                        sending = true
                        Task { result = await store.announce(message); sending = false }
                    } label: {
                        Label(sending ? "Sending…" : "Say it in Squint's voice", systemImage: "speaker.wave.2.fill")
                    }
                    .disabled(sending || message.isEmpty)
                    if let r = result { Text(r).font(.footnote).foregroundStyle(.secondary) }
                } header: {
                    Text("Google Home")
                }

                Section {
                    Button("Run setup again") { store.onboarded = false }
                }
            }
            .navigationTitle("Settings")
            .paperBackground()
        }
    }
}
