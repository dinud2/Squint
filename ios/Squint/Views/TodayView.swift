import SwiftUI

/// The screen the caregiver opens: what is Squint seeing, and is everyone okay today?
/// Layout: a greeting, Squint's screen as the hero, an overlapping "Doses today" card,
/// then small icon widgets. Blue carries the page; amber and red appear only on alerts.
struct TodayView: View {
    @Environment(AppStore.self) private var store
    @State private var demo: Task<Void, Never>?
    var openTrends: () -> Void = {}

    var body: some View {
        NavigationStack {
            ScrollViewReader { proxy in
                ScrollView {
                    VStack(alignment: .leading, spacing: Space.section) {
                        header(proxy)
                        hero
                        if !store.attention.isEmpty {
                            VStack(alignment: .leading, spacing: Space.group) {
                                Eyebrow("Needs you")
                                ForEach(store.attention) { AlertWidget(dose: $0) }
                            }
                            .id("needs")
                        }
                        if let r = store.routineAlert { RoutineNudge(insight: r, open: openTrends) }
                        if !store.elders.isEmpty { PeopleGrid() }
                        if !store.doses.isEmpty { ScheduleWidget() }
                        if let err = store.lastError {
                            Label(err, systemImage: "wifi.exclamationmark")
                                .font(.footnote).foregroundStyle(Theme.muted)
                        }
                    }
                    .padding(.horizontal, 20).padding(.bottom, 24)
                }
            }
            .statusBarFade()
            .background(PageBackground())
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

    // MARK: header: "Good evening / Margaret & Robert" and two round buttons

    private func header(_ proxy: ScrollViewProxy) -> some View {
        HStack(spacing: 12) {
            SquintBadge(mood: store.squint.mood, size: 30)
            TitleBlock(title: names, subtitle: greeting, subtitleOnTop: true)
            Spacer(minLength: 8)
            HStack(spacing: 6) {
                if store.useDemoData {
                    Button {
                        demo?.cancel()
                        demo = Task { await store.playDemo() }
                    } label: {
                        Image(systemName: store.demoScene == nil ? "play.fill" : "waveform")
                            .font(.system(size: 15, weight: .semibold))
                            .foregroundStyle(Theme.accent)
                            .frame(width: 44, height: 44)
                    }
                    .buttonStyle(.plain)
                    .disabled(store.demoScene != nil)
                    .accessibilityLabel("Watch Squint's morning")
                }
                Button {
                    withAnimation(.snappy) { proxy.scrollTo("needs", anchor: .top) }
                } label: {
                    Image(systemName: store.attention.isEmpty ? "bell" : "bell.badge")
                        .font(.system(size: 16, weight: .semibold))
                        .symbolRenderingMode(.palette)
                        .foregroundStyle(store.attention.isEmpty ? Color.white : Theme.flagged, Color.white)
                        .frame(width: 44, height: 44)
                        .background(Theme.navBar, in: Circle())
                }
                .buttonStyle(.plain)
                .accessibilityLabel(store.attention.isEmpty ? "Nothing needs you" : "\(store.attention.count) things need you")
            }
            .padding(4)
            .background(Capsule().fill(Theme.surface).shadow(color: .black.opacity(0.05), radius: 12, y: 4))
        }
        .padding(.top, 8)
    }

    private var greeting: String {
        switch Calendar.current.component(.hour, from: Date()) {
        case 5..<12: "Good morning"
        case 12..<17: "Good afternoon"
        case 17..<22: "Good evening"
        default: "Quiet night"
        }
    }

    private var names: String {
        let n = store.elders.map(\.name)
        return n.isEmpty ? "Squint" : n.count == 1 ? n[0] : n.dropLast().joined(separator: ", ") + " & " + n.last!
    }

    // MARK: hero: Squint's screen, a blue callout, and the overlapping "Doses today" card

    private var hero: some View {
        VStack(spacing: 0) {
            SquintCard(state: store.squint, badge: badge, bottomInset: 44)
                .overlay(alignment: .topTrailing) { callout }
            DosesTodayCard(open: openTrends)
                .padding(.top, -64)
                .padding(.horizontal, 10)
        }
    }

    /// A blue bubble tied to Squint's screen with a thin line, like a product callout.
    private var callout: some View {
        ZStack(alignment: .topTrailing) {
            Path { p in
                p.move(to: CGPoint(x: 90, y: 30))
                p.addLine(to: CGPoint(x: 56, y: 64))
            }
            .stroke(Color.white.opacity(0.85), lineWidth: 1.5)
            .frame(width: 120, height: 90)
            Circle()
                .fill(Color.white)
                .frame(width: 12, height: 12)
                .overlay(Circle().stroke(Theme.accent, lineWidth: 3))
                .offset(x: -58, y: 58)
            IconBubble(symbol: "eye.fill", size: 52, filled: true)
                .overlay(Circle().stroke(Color.white, lineWidth: 3))
                .offset(x: 8, y: -14)
        }
        .allowsHitTesting(false)
    }

    private var badge: String {
        if store.demoScene != nil || store.useDemoData { return "DEMO" }
        return store.liveConnected ? "LIVE" : "CONNECTING"
    }
}

// MARK: - "Doses today": the big number and the day strip

struct DosesTodayCard: View {
    @Environment(AppStore.self) private var store
    var open: () -> Void

    var body: some View {
        let taken = store.doses.filter { $0.status == .taken || $0.status == .flagged }.count
        VStack(alignment: .leading, spacing: 18) {
            WidgetHeader(symbol: "pills.fill", title: "Doses today", action: open)
            HStack(alignment: .firstTextBaseline, spacing: 4) {
                Text("\(taken)").font(Theme.number(60)).foregroundStyle(Theme.ink)
                Text("/ \(store.doses.count)").font(Theme.number(24)).foregroundStyle(Theme.muted)
            }
            .accessibilityElement(children: .combine)
            .accessibilityLabel("\(taken) of \(store.doses.count) doses taken today")
            if !store.doses.isEmpty { DayStrip() }
        }
        .paperCard()
    }
}

// MARK: - The day strip: every dose as a capsule on a 6 am – midnight line

struct DayStrip: View {
    @Environment(AppStore.self) private var store
    private let start = 6 * 60.0, end = 24 * 60.0

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            ForEach(store.elders) { p in
                HStack(spacing: 12) {
                    Avatar(person: p, size: 28)
                    GeometryReader { g in
                        ZStack(alignment: .leading) {
                            Capsule().fill(Theme.line).frame(height: 2)
                            ForEach(store.doses(for: p)) { d in
                                PillGlyph(status: d.status, width: 20, tint: Theme.personColor(p.id))
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
                            .font(.system(size: 11, weight: .medium, design: .rounded))
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
                    .stroke(Theme.accent.opacity(0.6), style: StrokeStyle(lineWidth: 2, lineCap: .round, dash: [3, 4]))
                    Circle().fill(Theme.accent).frame(width: 9, height: 9)
                        .overlay(Circle().stroke(Color.white, lineWidth: 2))
                        .position(x: xx, y: 0)
                }
            }
        }
        .accessibilityElement(children: .ignore)
        .accessibilityLabel("Today's doses on a timeline")
    }

    private func x(_ minutes: Double, _ width: CGFloat) -> CGFloat {
        let pad: CGFloat = 14
        return pad + (width - pad * 2) * CGFloat((min(max(minutes, start), end) - start) / (end - start))
    }
}

// MARK: - An alert: icon, who and what. Colour only on the icon.

struct AlertWidget: View {
    @Environment(AppStore.self) private var store
    let dose: Dose

    var body: some View {
        let who = store.person(dose.personID)?.name ?? dose.personID
        let med = store.medication(dose.medID)?.name ?? dose.medID
        let missed = dose.status == .missed
        HStack(alignment: .center, spacing: 14) {
            IconBubble(symbol: missed ? "clock.badge.exclamationmark" : "exclamationmark.triangle.fill",
                       tint: Theme.color(dose.status), size: 46)
            VStack(alignment: .leading, spacing: 4) {
                Text(missed ? "\(who) missed \(med)" : "\(who) · \(med)")
                    .font(Theme.display(20, .semibold)).foregroundStyle(Theme.ink)
                // A missed dose says it all in its title. A flagged one needs its reason.
                if !missed {
                    Text(dose.reason ?? "Squint flagged this dose")
                        .font(.subheadline).foregroundStyle(Theme.muted)
                        .lineSpacing(4)
                        .lineLimit(3)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
            Spacer(minLength: 0)
        }
        .paperCard()
    }
}

// MARK: - People: one small tile each, a big count and a half-ring

struct PeopleGrid: View {
    @Environment(AppStore.self) private var store

    var body: some View {
        VStack(alignment: .leading, spacing: Space.group) {
            Eyebrow("People")
            LazyVGrid(columns: [GridItem(.flexible(), spacing: 14), GridItem(.flexible(), spacing: 14)], spacing: 14) {
                ForEach(store.elders) { PersonTile(person: $0) }
            }
        }
    }
}

struct PersonTile: View {
    @Environment(AppStore.self) private var store
    let person: Person

    var body: some View {
        let doses = store.doses(for: person)
        let done = doses.filter { $0.status == .taken || $0.status == .flagged }.count
        let frac = doses.isEmpty ? 0 : Double(done) / Double(doses.count)
        VStack(alignment: .leading, spacing: 14) {
            HStack(spacing: 10) {
                Avatar(person: person, size: 36)
                Text(person.name).font(Theme.display(19, .semibold)).foregroundStyle(Theme.ink).lineLimit(1)
            }
            ZStack(alignment: .bottom) {
                HalfRing(fraction: frac, color: Theme.personColor(person.id))
                    .frame(height: 76)
                HStack(alignment: .firstTextBaseline, spacing: 2) {
                    Text("\(done)").font(Theme.number(42)).foregroundStyle(Theme.ink)
                    Text("/\(doses.count)").font(Theme.number(18)).foregroundStyle(Theme.muted)
                }
            }
            .frame(maxWidth: .infinity)
        }
        .padding(18)
        .frame(maxWidth: .infinity, alignment: .leading)
        .widgetBackground(26)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel("\(person.name): \(done) of \(doses.count) taken")
    }
}

/// A half circle gauge, like a step counter.
struct HalfRing: View {
    var fraction: Double
    var color: Color = Theme.accent

    var body: some View {
        GeometryReader { g in
            let d = min(g.size.width, g.size.height * 2)
            ZStack {
                Circle().trim(from: 0.5, to: 1)
                    .stroke(color.opacity(0.14), style: StrokeStyle(lineWidth: 8, lineCap: .round))
                Circle().trim(from: 0.5, to: 0.5 + 0.5 * max(0.001, min(fraction, 1)))
                    .stroke(color, style: StrokeStyle(lineWidth: 8, lineCap: .round))
            }
            .frame(width: d, height: d)
            .position(x: g.size.width / 2, y: g.size.height)
        }
        .animation(.spring, value: fraction)
    }
}

// MARK: - Schedule: every dose today, in time order

struct ScheduleWidget: View {
    @Environment(AppStore.self) private var store

    var body: some View {
        let doses = store.doses.sorted { ClockTime.minutes($0.due) < ClockTime.minutes($1.due) }
        VStack(alignment: .leading, spacing: 8) {
            WidgetHeader(symbol: "clock.fill", title: "Schedule", tint: Theme.indigo)
                .padding(.bottom, 4)
            ForEach(doses) { d in
                let med = store.medication(d.medID)
                HStack(spacing: 14) {
                    PillGlyph(status: d.status, width: 26, tint: Theme.personColor(d.personID)).frame(width: 30)
                    VStack(alignment: .leading, spacing: 2) {
                        HStack(spacing: 6) {
                            Text(med?.name ?? d.medID).font(Theme.display(19, .semibold)).foregroundStyle(Theme.ink)
                            if med?.risk == .high {
                                Image(systemName: "exclamationmark.shield.fill")
                                    .font(.caption).foregroundStyle(Theme.flagged)
                                    .accessibilityLabel("Extra careful")
                            }
                        }
                        // The person's name in their own colour, so each person's doses stand out.
                        Text(store.person(d.personID)?.name ?? "")
                            .font(.system(size: 13, weight: .medium, design: .rounded))
                            .foregroundStyle(Theme.personColor(d.personID))
                    }
                    Spacer()
                    StatusLabel(dose: d)
                }
                .padding(.vertical, 12)
                .accessibilityElement(children: .combine)
                if d.id != doses.last?.id { Divider().overlay(Theme.line).padding(.leading, 44) }
            }
        }
        .paperCard()
    }
}

/// One widget on Today when someone's routine has changed; tapping opens Trends.
struct RoutineNudge: View {
    let insight: PersonInsight
    let open: () -> Void

    var body: some View {
        Button(action: open) {
            VStack(alignment: .leading, spacing: 16) {
                HStack(spacing: 12) {
                    IconBubble(symbol: "chart.line.uptrend.xyaxis", tint: Theme.teal)
                    Text("Routine").font(Theme.display(21, .semibold)).foregroundStyle(Theme.ink)
                    Spacer(minLength: 0)
                    ArrowBubble()
                }
                Text(insight.headline).font(Theme.display(22, .medium)).foregroundStyle(Theme.ink)
                    .lineSpacing(4)
                    .multilineTextAlignment(.leading)
                    .fixedSize(horizontal: false, vertical: true)
            }
            .paperCard()
        }
        .buttonStyle(.plain)
        .accessibilityHint("Opens Trends")
    }
}
