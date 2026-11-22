import SwiftUI

struct SettingsView: View {
    @Environment(AppStore.self) private var store
    @State private var message = "Good morning! It's time for your morning pills. Take your time."
    @State private var result: String?
    @State private var sending = false
    @State private var notifyTaken = Notifier.shared.notifyTaken

    var body: some View {
        @Bindable var store = store
        NavigationStack {
            Form {
                Section {
                    HStack(spacing: 14) {
                        SquintBadge(mood: store.useDemoData ? .idle : (store.liveConnected ? store.squint.mood : .sleep), size: 40)
                        TitleBlock(title: "Squint",
                                   subtitle: store.useDemoData ? "Showing demo data" : store.liveConnected ? "Connected to the station" : "Looking for the station…")
                    }
                    .padding(.vertical, 6)
                }

                Section("People") {
                    ForEach(store.elders) { p in
                        HStack(spacing: 12) { Avatar(person: p, size: 34); Text(p.name) }
                            .padding(.vertical, 2)
                    }
                }

                Section {
                    Toggle(isOn: $notifyTaken) { SettingLabel("Every dose taken", symbol: "checkmark.circle.fill", tint: Theme.green) }
                        .onChange(of: notifyTaken) { Notifier.shared.notifyTaken = notifyTaken }
                } header: {
                    Text("Notifications")
                } footer: {
                    Text("Missed doses and anything Squint stops are always sent.")
                }

                Section {
                    Toggle(isOn: $store.useDemoData) { SettingLabel("Use demo data", symbol: "play.rectangle.fill", tint: Theme.green) }
                        .onChange(of: store.useDemoData) { Task { await store.refresh() } }
                    if !store.useDemoData {
                        HStack(spacing: 12) {
                            IconBubble(symbol: "antenna.radiowaves.left.and.right", tint: Theme.teal, size: 32)
                            TextField("Station address", text: $store.backendURL).urlField()
                                .onSubmit { Task { await store.refresh() } }
                        }
                    }
                } header: {
                    Text("Station")
                }

                Section {
                    HStack(spacing: 12) {
                        IconBubble(symbol: "hifispeaker.fill", tint: Theme.indigo, size: 32)
                        TextField("Speaker address", text: $store.homeURL).urlField()
                    }
                    HStack(alignment: .top, spacing: 12) {
                        IconBubble(symbol: "text.bubble.fill", size: 32)
                        TextField("Message", text: $message, axis: .vertical)
                            .padding(.top, 6)
                    }
                    Button {
                        sending = true
                        Task { result = await store.announce(message); sending = false }
                    } label: {
                        SettingLabel(sending ? "Sending…" : "Say it in Squint's voice", symbol: "speaker.wave.2.fill", tint: Theme.coral)
                    }
                    .disabled(sending || message.isEmpty)
                    if let r = result { Text(r).font(.footnote).foregroundStyle(.secondary) }
                } header: {
                    Text("Google Home")
                }

                Section {
                    Button { store.onboarded = false } label: {
                        SettingLabel("Run setup again", symbol: "arrow.counterclockwise", tint: Theme.muted)
                    }
                }
            }
            .navigationTitle("Settings")
            .inlineTitle()
            .toolbar {
                ToolbarItem(placement: .principal) {
                    Text("Settings").font(Theme.display(24, .semibold)).foregroundStyle(Theme.ink)
                }
            }
            .paperBackground()
        }
    }
}

/// A settings row: an icon bubble and a few words.
struct SettingLabel: View {
    let title: String
    let symbol: String
    var tint: Color = Theme.accent
    init(_ title: String, symbol: String, tint: Color = Theme.accent) {
        self.title = title; self.symbol = symbol; self.tint = tint
    }

    var body: some View {
        HStack(spacing: 12) {
            IconBubble(symbol: symbol, tint: tint, size: 32)
            Text(title).foregroundStyle(Theme.ink)
        }
    }
}
