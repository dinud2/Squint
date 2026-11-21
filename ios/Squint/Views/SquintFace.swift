import SwiftUI

/// Squint's moods: the same eight reactions the Tab5 shows (tab5-face/README.md),
/// with the same colour meaning: white = all good, amber = check this, red = STOP, blue = asleep.
enum SquintMood: String, CaseIterable {
    case sleep, idle, greet, remind, happy, concerned, stop, wrong

    static let white = Color.white
    static let amber = Color(red: 0.94, green: 0.63, blue: 0.16)
    static let red = Color(red: 0.91, green: 0.29, blue: 0.31)
    static let blue = Color(red: 0.36, green: 0.54, blue: 0.81)

    var color: Color {
        switch self {
        case .sleep: Self.blue
        case .concerned, .wrong: Self.amber
        case .stop: Self.red
        default: Self.white
        }
    }

    var defaultTitle: String {
        switch self {
        case .sleep, .idle: ""
        case .greet: "Hi there!"
        case .remind: "Pill time"
        case .happy: "Well done!"
        case .concerned: "Show me the label"
        case .stop: "STOP"
        case .wrong: "Not your pills"
        }
    }

    /// One line for the caregiver: what is Squint doing at home right now?
    var caption: String {
        switch self {
        case .sleep: "Squint is resting. Nobody is at the counter."
        case .idle: "Squint is awake and keeping an eye on the counter."
        case .greet: "Someone just came to the counter."
        case .remind: "Squint is guiding a dose right now."
        case .happy: "A dose was just taken."
        case .concerned: "Squint isn't sure about a bottle."
        case .stop: "Squint stopped a double dose."
        case .wrong: "Someone picked up another person's pills."
        }
    }

    /// The light Squint throws on the counter around it.
    var glow: Color {
        switch self {
        case .sleep: Self.blue
        case .concerned, .wrong: Self.amber
        case .stop: Self.red
        case .happy: Color(red: 0.42, green: 0.85, blue: 0.55)
        default: Color(white: 0.5)
        }
    }

    var spoken: String {
        switch self {
        case .sleep: "asleep"
        case .idle: "awake"
        case .greet: "happy to see someone"
        case .remind: "reminding"
        case .happy: "delighted"
        case .concerned: "unsure"
        case .stop: "alarmed"
        case .wrong: "worried"
        }
    }
}

/// Squint's eyes, drawn live the way the Tab5 draws them (tab5-face/OttoFace.h): just eyes,
/// coloured by meaning, no extra marks.
struct SquintFace: View {
    var mood: SquintMood
    var animated = true

    var body: some View {
        TimelineView(.animation(paused: !animated)) { tl in
            let t = animated ? tl.date.timeIntervalSinceReferenceDate : 0
            Canvas { ctx, size in draw(&ctx, size, t) }
        }
        .accessibilityElement()
        .accessibilityLabel("Squint looks \(mood.spoken)")
    }

    // MARK: drawing

    private func draw(_ ctx: inout GraphicsContext, _ size: CGSize, _ t: Double) {
        let w = size.width, h = size.height
        let r = min(w * 0.12, h * 0.26)
        let drift = mood == .idle ? sin(t * 0.6) * w * 0.025 : 0           // idle: looks around
        let L = CGPoint(x: w / 2 - r * 1.45 + drift, y: h / 2)
        let R = CGPoint(x: w / 2 + r * 1.45 + drift, y: h / 2)
        let col = mood.color
        let blink = blinkScale(t)

        switch mood {
        case .sleep:
            let breathe = sin(t * 2 * .pi * 0.22) * r * 0.06                  // closed eyes, breathing
            for c in [L, R] { stroke(&ctx, arc(CGPoint(x: c.x, y: c.y + breathe), r * 0.95, from: 20, to: 160), col, r * 0.32) }
        case .idle:
            for c in [L, R] { disc(&ctx, c, r, r * blink, col) }
        case .greet:
            for c in [L, R] { stroke(&ctx, arc(CGPoint(x: c.x, y: c.y + r * 0.45), r * 0.95, from: 200, to: 340), col, r * 0.55) }
        case .remind:
            disc(&ctx, L, r, r * blink, col)
            stroke(&ctx, arc(CGPoint(x: R.x, y: R.y + r * 0.35), r * 0.85, from: 210, to: 330), col, r * 0.3)
        case .happy:
            let beat = 1 + 0.07 * sin(t * 5)
            for c in [L, R] {
                var img = ctx.resolve(Image(systemName: "heart.fill"))
                img.shading = .color(col)
                let s = r * 2.3 * beat
                ctx.draw(img, in: CGRect(x: c.x - s / 2, y: c.y - s / 2, width: s, height: s))
            }
        case .concerned:
            disc(&ctx, L, r * 0.8, r * 1.05 * blink, col)
            halfDisc(&ctx, CGPoint(x: R.x, y: R.y + r * 0.1), r * 0.95, col)
        case .stop:
            let shake = sin(t * 40) * r * 0.03
            for c in [L, R] {
                let cc = CGPoint(x: c.x + shake, y: c.y)
                ctx.stroke(Path(ellipseIn: CGRect(x: cc.x - r * 0.8, y: cc.y - r, width: r * 1.6, height: r * 2)),
                           with: .color(col), lineWidth: r * 0.3)
                disc(&ctx, cc, r * 0.17, r * 0.17, col)
            }

        case .wrong:
            let glance = sin(t * 2 * .pi * 0.35) * r * 0.25                     // lowered eyes glancing away
            for c in [L, R] { halfDisc(&ctx, CGPoint(x: c.x + glance, y: c.y + r * 0.25), r * 0.85, col) }
        }
    }

    private func blinkScale(_ t: Double) -> CGFloat {
        let p = t.truncatingRemainder(dividingBy: 4.2)
        return p < 0.16 ? max(0.08, abs(p - 0.08) / 0.08) : 1
    }

    private func disc(_ ctx: inout GraphicsContext, _ c: CGPoint, _ rx: CGFloat, _ ry: CGFloat, _ col: Color) {
        ctx.fill(Path(ellipseIn: CGRect(x: c.x - rx, y: c.y - ry, width: rx * 2, height: ry * 2)), with: .color(col))
    }

    private func halfDisc(_ ctx: inout GraphicsContext, _ c: CGPoint, _ r: CGFloat, _ col: Color) {
        var p = arc(c, r, from: 0, to: 180)
        p.closeSubpath()
        ctx.fill(p, with: .color(col))
    }

    /// Arc through angles in degrees, y pointing down (0 = right, 90 = down).
    private func arc(_ c: CGPoint, _ r: CGFloat, from a0: Double, to a1: Double) -> Path {
        var p = Path()
        for (i, a) in stride(from: a0, through: a1, by: 4).enumerated() {
            let pt = CGPoint(x: c.x + r * cos(a * .pi / 180), y: c.y + r * sin(a * .pi / 180))
            i == 0 ? p.move(to: pt) : p.addLine(to: pt)
        }
        return p
    }

    private func stroke(_ ctx: inout GraphicsContext, _ p: Path, _ col: Color, _ width: CGFloat) {
        ctx.stroke(p, with: .color(col), style: StrokeStyle(lineWidth: width, lineCap: .round, lineJoin: .round))
    }

}

/// Squint as it looks on the counter: black screen, eyes, a few big words.
struct SquintCard: View {
    var state: SquintState
    var badge: String?

    var body: some View {
        VStack(spacing: 8) {
            SquintFace(mood: state.mood)
                .frame(height: 132)
            if !state.title.isEmpty || !state.detail.isEmpty {
                VStack(spacing: 2) {
                    if !state.title.isEmpty {
                        Text(state.title).font(.system(size: 30, weight: .heavy, design: .rounded))
                            .foregroundStyle(.white)
                    }
                    if !state.detail.isEmpty {
                        Text(state.detail).font(.system(.title3, design: .rounded, weight: .bold))
                            .foregroundStyle(.white.opacity(0.75))
                    }
                }
                .multilineTextAlignment(.center)
                .minimumScaleFactor(0.6)
                .lineLimit(2)
            }
        }
        .padding(.horizontal, 20).padding(.top, 34).padding(.bottom, 26)
        .frame(maxWidth: .infinity, minHeight: 280, maxHeight: 280, alignment: .top)
        .background {
            // the Tab5 in its shell: black glass, a soft bezel, a camera dot
            RoundedRectangle(cornerRadius: 34, style: .continuous)
                .fill(Color(white: 0.04))
                .overlay(RoundedRectangle(cornerRadius: 34, style: .continuous)
                    .strokeBorder(LinearGradient(colors: [.white.opacity(0.18), .white.opacity(0.03)],
                                                 startPoint: .top, endPoint: .bottom), lineWidth: 1.2))
                .overlay(alignment: .top) {
                    Circle().fill(Color(white: 0.16)).frame(width: 7, height: 7).padding(.top, 12)
                }
                .background(RoundedRectangle(cornerRadius: 40, style: .continuous)
                    .fill(Color(white: 0.13)).padding(-6))               // the 3D-printed shell
                .shadow(color: state.mood.glow.opacity(0.35), radius: 24, y: 10)
        }
        .overlay(alignment: .topLeading) {
            if let badge {
                HStack(spacing: 5) {
                    Circle().fill(badge.contains("LIVE") ? Color(red: 0.42, green: 0.85, blue: 0.55) : .white.opacity(0.5))
                        .frame(width: 6, height: 6)
                    Text(badge.replacingOccurrences(of: "● ", with: ""))
                }
                .font(.system(size: 10, weight: .heavy, design: .rounded)).kerning(1)
                .foregroundStyle(.white.opacity(0.7))
                .padding(.horizontal, 9).padding(.vertical, 5)
                .background(.white.opacity(0.1), in: Capsule())
                .padding(16)
            }
        }
        .padding(6)
        .animation(.easeInOut(duration: 0.25), value: state)
    }
}

/// A small Squint for list rows and alerts.
struct SquintBadge: View {
    var mood: SquintMood
    var size: CGFloat = 44

    var body: some View {
        SquintFace(mood: mood)
            .frame(width: size * 1.4, height: size)
            .background(Color(white: 0.04), in: RoundedRectangle(cornerRadius: size * 0.3, style: .continuous))
            .padding(3)
            .background(Color(white: 0.15), in: RoundedRectangle(cornerRadius: size * 0.3 + 3, style: .continuous))
    }
}

/// What Squint is showing: a mood, its big words, and when it started.
struct SquintState: Equatable {
    var mood: SquintMood
    var title: String = ""
    var detail: String = ""

    static let asleep = SquintState(mood: .sleep)

    /// One line from the station, in the Tab5's own format: `<reaction> [title][|detail][|clipId]`.
    init?(line: String) {
        let s = line.trimmingCharacters(in: .whitespaces)
        let word = String(s.prefix { $0 != " " })
        let rest = s.dropFirst(word.count).trimmingCharacters(in: .whitespaces)
        let parts = rest.split(separator: "|", omittingEmptySubsequences: false).map(String.init)
        switch word {
        case "presence":
            self.init(mood: .greet, title: rest.isEmpty ? "Hi there!" : "Hi \(rest)!")
        case "away":
            self.init(mood: .sleep)
        default:
            guard let m = SquintMood(rawValue: word) else { return nil }   // say, next, demo: not a face
            self.init(mood: m, title: parts.first.flatMap { $0.isEmpty ? nil : $0 } ?? m.defaultTitle,
                      detail: parts.count > 1 ? parts[1] : "")
        }
    }

    init(mood: SquintMood, title: String = "", detail: String = "") {
        self.mood = mood
        self.title = title
        self.detail = detail
    }
}
