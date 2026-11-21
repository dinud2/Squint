import SwiftUI

/// The screen the caregiver opens: what is Squint seeing, and is everyone okay today?
struct TodayView: View {
    @Environment(AppStore.self) private var store
    @State private var demo: Task<Void, Never>?
    var openTrends: () -> Void = {}

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 22) {
                    header
                    squint
                    status
                    if !store.doses.isEmpty { DayStrip() }
                    if let r = store.routineAlert { RoutineNudge(insight: r, open: openTrends) }
                    if !store.attention.isEmpty {
                        VStack(alignment: .leading, spacing: 10) {
                            Eyebrow("Needs you")
                            ForEach(store.attention) { AttentionCard(dose: $0) }
                        }
                    }
                    VStack(alignment: .leading, spacing: 10) {
                        Eyebrow("Today, by person")
                        ForEach(store.elders) { PersonCard(person: $0) }
                    }
                    if let err = store.lastError {
                        Label(err, systemImage: "wifi.exclamationmark")
                            .font(.footnote).foregroundStyle(Theme.muted)
                    }
                }
                .padding(.horizontal, 20).padding(.bottom, 24)
            }
            .background(Theme.paper.ignoresSafeArea())
            .toolbar(.hidden, for: .navigationBar)
            .refreshable { await store.refresh() }
            .task {
                // keep it live: the station updates doses as they happen
                while !Task.isCancelled {
                    try? await Task.sleep(for: .seconds(15))
                    await store.refresh()
                }
            }
            .onDisappear { demo?.cancel() }
            .sensoryFeedback(trigger: store.squint) { _, new in
                switch new.mood {
                case .stop: .error
                case .wrong, .concerned: .warning
                case .happy: .success
                default: .impact(weight: .light)
                }
            }
        }
    }

    // MARK: pieces

    private var header: some View {
        VStack(alignment: .leading, spacing: 4) {
            Eyebrow(Date().formatted(.dateTime.weekday(.wide).month(.abbreviated).day()))
            Text(greeting).font(Theme.display(34)).foregroundStyle(Theme.ink)
        }
        .padding(.top, 12)
    }

    private var greeting: String {
        switch Calendar.current.component(.hour, from: Date()) {
        case 5..<12: "Good morning."
        case 12..<17: "Good afternoon."
        case 17..<22: "Good evening."
        default: "Quiet night."
        }
    }

    private var squint: some View {
        VStack(alignment: .leading, spacing: 12) {
            SquintCard(state: store.squint, badge: badge)
            HStack(alignment: .firstTextBaseline, spacing: 8) {
                Circle().fill(store.squint.mood == .sleep ? Theme.muted : Theme.ink).frame(width: 6, height: 6)
                    .offset(y: -2)
                Text(store.squint.mood.caption)
                    .font(.system(.subheadline, design: .rounded, weight: .medium))
                    .foregroundStyle(Theme.muted)
            }
            .padding(.horizontal, 6)
            if store.useDemoData {
                Button {
                    demo?.cancel()
                    demo = Task { await store.playDemo() }
                } label: {
                    Label(store.demoScene == nil ? "Watch Squint's morning" : "Playing…",
                          systemImage: store.demoScene == nil ? "play.fill" : "waveform")
                }
                .buttonStyle(InkButtonStyle(prominent: false))
                .disabled(store.demoScene != nil)
            }
        }
    }

    private var badge: String {
        if store.demoScene != nil || store.useDemoData { return "DEMO" }
        return store.liveConnected ? "LIVE" : "CONNECTING"
    }

    private var status: some View {
        let taken = store.doses.filter { $0.status == .taken || $0.status == .flagged }.count
        let issues = store.attention.count
        let names = store.elders.map(\.name).joined(separator: " & ")
        return HStack(alignment: .bottom) {
            VStack(alignment: .leading, spacing: 2) {
                Text(issues == 0 ? (names.isEmpty ? "All quiet" : "\(names) \(store.elders.count > 1 ? "are" : "is") on track")
                                 : issues == 1 ? "One thing needs you" : "\(issues) things need you")
                    .font(Theme.display(22, .bold))
                    .foregroundStyle(issues == 0 ? Theme.ink : Theme.flagged)
                Text("Doses taken today").font(.subheadline).foregroundStyle(Theme.muted)
            }
            Spacer()
            Text("\(taken)").font(Theme.display(44)).foregroundStyle(Theme.ink)
                + Text("/\(store.doses.count)").font(Theme.display(22, .bold)).foregroundStyle(Theme.muted)
        }
        .padding(.top, 4)
    }
}

// MARK: - The day strip: every dose as a capsule on a 6 am – midnight line

struct DayStrip: View {
    @Environment(AppStore.self) private var store
    private let start = 6 * 60.0, end = 24 * 60.0

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            ForEach(store.elders) { p in
                HStack(spacing: 12) {
                    Avatar(person: p, size: 28)
                    GeometryReader { g in
                        ZStack(alignment: .leading) {
                            Capsule().fill(Theme.line).frame(height: 2)
                            ForEach(store.doses(for: p)) { d in
                                PillGlyph(status: d.status, width: 20)
                                    .position(x: x(Double(ClockTime.minutes(d.due)), g.size.width), y: g.size.height / 2)
                            }
                        }
                    }
                    .frame(height: 26)
                }
            }
            HStack(spacing: 12) {
                Color.clear.frame(width: 28, height: 1)
                GeometryReader { g in
                    ForEach([6, 12, 18, 24], id: \.self) { h in
                        Text(h == 12 ? "noon" : h == 24 ? "12a" : "\(h % 12)\(h < 12 ? "a" : "p")")
                            .font(.system(size: 11, weight: .bold, design: .rounded))
                            .foregroundStyle(Theme.muted)
                            .position(x: x(Double(h * 60), g.size.width), y: 6)
                    }
                }
                .frame(height: 12)
            }
        }
        .overlay {
            // the "now" needle
            GeometryReader { g in
                let w = g.size.width - 40
                let now = Double(ClockTime.nowMinutes)
                if now >= start && now <= end {
                    let xx = 40 + x(now, w)
                    Path { p in
                        p.move(to: CGPoint(x: xx, y: 0))
                        p.addLine(to: CGPoint(x: xx, y: g.size.height - 18))
                    }
                    .stroke(Theme.ink.opacity(0.7), style: StrokeStyle(lineWidth: 2, lineCap: .round))
                    Circle().fill(Theme.ink).frame(width: 7, height: 7).position(x: xx, y: 0)
                }
            }
        }
        .paperCard()
        .accessibilityElement(children: .ignore)
        .accessibilityLabel("Today's doses on a timeline")
    }

    private func x(_ minutes: Double, _ width: CGFloat) -> CGFloat {
        let pad: CGFloat = 14
        return pad + (width - pad * 2) * CGFloat((min(max(minutes, start), end) - start) / (end - start))
    }
}

struct AttentionCard: View {
    @Environment(AppStore.self) private var store
    let dose: Dose

    var body: some View {
        let who = store.person(dose.personID)?.name ?? dose.personID
        let med = store.medication(dose.medID)?.name ?? dose.medID
        let c = Theme.color(dose.status)
        HStack(alignment: .center, spacing: 14) {
            SquintBadge(mood: dose.status == .missed ? .concerned : .wrong, size: 38)
            VStack(alignment: .leading, spacing: 3) {
                Text(dose.status == .missed ? "\(who) missed \(med)" : "\(who) · \(med)")
                    .font(Theme.display(17, .bold)).foregroundStyle(Theme.ink)
                Text(dose.reason ?? (dose.status == .missed ? "Was due at \(ClockTime.display(dose.due))" : "Squint flagged this dose"))
                    .font(.subheadline).foregroundStyle(Theme.muted)
                    .fixedSize(horizontal: false, vertical: true)
            }
            Spacer(minLength: 0)
        }
        .padding(16)
        .background(c.opacity(0.1), in: RoundedRectangle(cornerRadius: 22, style: .continuous))
        .overlay(alignment: .leading) {
            Capsule().fill(c).frame(width: 4).padding(.vertical, 16)
        }
        .overlay(RoundedRectangle(cornerRadius: 22, style: .continuous).strokeBorder(c.opacity(0.35)))
    }
}

struct PersonCard: View {
    @Environment(AppStore.self) private var store
    let person: Person

    var body: some View {
        let doses = store.doses(for: person)
        let done = doses.filter { $0.status == .taken || $0.status == .flagged }.count
        let frac = doses.isEmpty ? 0 : Double(done) / Double(doses.count)
        VStack(alignment: .leading, spacing: 14) {
            HStack(spacing: 14) {
                ZStack {
                    Circle().stroke(Theme.line, lineWidth: 4)
                    Circle().trim(from: 0, to: frac)
                        .stroke(Theme.taken, style: StrokeStyle(lineWidth: 4, lineCap: .round))
                        .rotationEffect(.degrees(-90))
                    Avatar(person: person, size: 44)
                }
                .frame(width: 56, height: 56)
                .animation(.spring, value: frac)
                VStack(alignment: .leading, spacing: 2) {
                    Text(person.name).font(Theme.display(22, .bold)).foregroundStyle(Theme.ink)
                    Text(doses.isEmpty ? "No medications yet" : "\(done) of \(doses.count) taken")
                        .font(.subheadline).foregroundStyle(Theme.muted)
                }
                Spacer()
            }
            VStack(spacing: 0) {
                ForEach(doses) { d in
                    let med = store.medication(d.medID)
                    HStack(spacing: 12) {
                        PillGlyph(status: d.status, width: 26)
                            .frame(width: 30)
                        VStack(alignment: .leading, spacing: 1) {
                            HStack(spacing: 6) {
                                Text(med?.name ?? d.medID).font(.body.weight(.semibold)).foregroundStyle(Theme.ink)
                                if med?.risk == .high {
                                    Image(systemName: "exclamationmark.shield.fill")
                                        .font(.caption).foregroundStyle(Theme.flagged)
                                        .accessibilityLabel("Extra careful")
                                }
                            }
                            Text([med?.strength, ClockTime.display(d.due)].compactMap { $0 }.filter { !$0.isEmpty }
                                    .joined(separator: " · "))
                                .font(.footnote).foregroundStyle(Theme.muted)
                        }
                        Spacer()
                        StatusLabel(dose: d)
                    }
                    .padding(.vertical, 10)
                    .accessibilityElement(children: .combine)
                    if d.id != doses.last?.id { Divider().overlay(Theme.line).padding(.leading, 42) }
                }
            }
        }
        .paperCard()
    }
}

/// One line on Today when someone's routine has changed; tapping opens Trends.
struct RoutineNudge: View {
    let insight: PersonInsight
    let open: () -> Void

    var body: some View {
        Button(action: open) {
            HStack(spacing: 14) {
                SquintBadge(mood: insight.level.mood, size: 34)
                VStack(alignment: .leading, spacing: 3) {
                    Text("ROUTINE · \(insight.level.label.uppercased())")
                        .font(.system(size: 11, weight: .heavy, design: .rounded)).kerning(1)
                        .foregroundStyle(insight.level.color)
                    Text(insight.headline).font(.subheadline.weight(.semibold)).foregroundStyle(Theme.ink)
                        .multilineTextAlignment(.leading)
                        .fixedSize(horizontal: false, vertical: true)
                }
                Spacer(minLength: 0)
                Image(systemName: "chevron.right").font(.footnote.weight(.bold)).foregroundStyle(Theme.muted)
            }
            .paperCard(22)
        }
        .buttonStyle(.plain)
        .accessibilityHint("Opens Trends")
    }
}
