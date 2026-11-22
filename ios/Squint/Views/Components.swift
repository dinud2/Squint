import SwiftUI
#if canImport(UIKit)
import UIKit
#else
import AppKit
#endif

// MARK: - The capsule: one dose, drawn as a two-tone pill

/// One colour rule for doses, everywhere in the app:
/// - the pill's colour says whose it is (the person's colour, passed as `tint`);
/// - only a problem overrides it: amber = missed, red = flagged (double dose, wrong bottle);
/// - a dose still to come is a dashed outline.
struct PillGlyph: View {
    var status: Dose.Status
    var width: CGFloat = 30
    var upright = false
    var tint: Color?          // the person's colour

    var body: some View {
        let problem = status == .missed || status == .flagged
        let c = problem ? Theme.color(status) : (tint ?? Theme.color(status))
        let h = width * 0.42
        ZStack {
            switch status {
            case .due:
                Capsule().strokeBorder((tint ?? Theme.ink).opacity(0.6), style: StrokeStyle(lineWidth: 1.6, dash: [3, 2.5]))
            default:
                Capsule().fill(c.opacity(0.22))
                Capsule().fill(c).mask(alignment: .leading) { Rectangle().frame(width: width / 2) }
                Capsule().strokeBorder(c, lineWidth: 1.4)
            }
        }
        .frame(width: width, height: h)
        .rotationEffect(upright ? .degrees(-90) : .degrees(-28))
        .frame(width: upright ? h : width, height: upright ? width : width * 0.62)
        .accessibilityHidden(true)
    }
}

/// The main button: a blue capsule with white text (or a soft blue one for secondary actions).
struct InkButtonStyle: ButtonStyle {
    var prominent = true
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(Theme.display(17, .semibold))
            .foregroundStyle(prominent ? Color.white : Theme.accent)
            .padding(.vertical, 16).padding(.horizontal, 22)
            .frame(maxWidth: .infinity)
            .background(prominent ? Theme.accent : Theme.accentSoft, in: Capsule())
            .scaleEffect(configuration.isPressed ? 0.97 : 1)
            .animation(.spring(duration: 0.2), value: configuration.isPressed)
    }
}

/// A round icon that says what a widget is about (pills, clock, chart…).
struct IconBubble: View {
    let symbol: String
    var tint: Color = Theme.accent
    var size: CGFloat = 42
    var filled = false        // solid tint with a white icon, for the one thing to look at

    var body: some View {
        Image(systemName: symbol)
            .font(.system(size: size * 0.42, weight: .semibold))
            .foregroundStyle(filled ? Color.white : tint)
            .frame(width: size, height: size)
            .background(filled ? tint : (tint == Theme.accent ? Theme.accentSoft : tint.opacity(0.12)), in: Circle())
            .accessibilityHidden(true)
    }
}

/// A title with a small, quiet line above or below it ("Good evening / Margaret & Robert").
/// One size pairing everywhere: 13 pt muted, a 2 pt gap, a 22 pt semibold title (a strong ratio).
struct TitleBlock: View {
    let title: String
    var subtitle: String?
    var subtitleOnTop = false
    var subtitleColor: Color = Theme.muted

    var body: some View {
        VStack(alignment: .leading, spacing: 2) {
            if subtitleOnTop, let subtitle { sub(subtitle) }
            Text(title).font(Theme.display(22, .semibold)).foregroundStyle(Theme.ink)
                .lineLimit(1).minimumScaleFactor(0.8)
            if !subtitleOnTop, let subtitle { sub(subtitle) }
        }
        .accessibilityElement(children: .combine)
    }

    private func sub(_ s: String) -> some View {
        Text(s).font(.system(size: 13, weight: .regular, design: .rounded)).foregroundStyle(subtitleColor)
    }
}

/// The page: a very soft sky-to-aqua wash with a light glow at the top, for a bit of depth.
struct PageBackground: View {
    var body: some View {
        ZStack {
            LinearGradient(colors: [Theme.washTop, Theme.paper, Theme.washBottom],
                           startPoint: .top, endPoint: .bottom)
            RadialGradient(colors: [Theme.washGlow, .clear], center: .topLeading, startRadius: 0, endRadius: 420)
        }
        .ignoresSafeArea()
    }
}

/// The round ↗ button in a widget's corner: "open this".
struct ArrowBubble: View {
    var body: some View {
        Image(systemName: "arrow.up.right")
            .font(.system(size: 15, weight: .semibold))
            .foregroundStyle(Theme.ink)
            .frame(width: 42, height: 42)
            .background(Theme.bubble, in: Circle())
    }
}

/// A widget's top row: icon, title, and an optional ↗.
struct WidgetHeader: View {
    let symbol: String
    let title: String
    var tint: Color = Theme.accent
    var action: (() -> Void)?

    var body: some View {
        HStack(spacing: 12) {
            IconBubble(symbol: symbol, tint: tint)
            Text(title).font(Theme.display(21, .semibold)).foregroundStyle(Theme.ink)
            Spacer(minLength: 0)
            if let action {
                Button(action: action) { ArrowBubble() }
                    .buttonStyle(.plain)
                    .accessibilityLabel("Open \(title)")
            }
        }
    }
}

/// A quiet label above a group, in sentence case so it reads easily.
struct Eyebrow: View {
    let text: String
    init(_ text: String) { self.text = text }
    var body: some View {
        Text(text.prefix(1).uppercased() + text.dropFirst())
            .font(.system(size: 20, weight: .semibold, design: .rounded))
            .foregroundStyle(Theme.ink)
    }
}

/// Spacing used across the app, so every screen breathes the same way.
enum Space {
    static let section: CGFloat = 32   // between sections and cards on a page
    static let group: CGFloat = 16     // between cards in one group, and label to content
    static let lines: CGFloat = 6      // between a title and its subtitle
    static let row: CGFloat = 16       // above and below each row in a list
    static let rowMinHeight: CGFloat = 64
    static let card: CGFloat = 24      // inside a card
}

extension View {
    /// A white, very rounded widget card with a soft shadow.
    func paperCard(_ radius: CGFloat = 30) -> some View {
        padding(Space.card).widgetBackground(radius)
    }

    /// The white rounded card shape with a soft shadow. The shadow sits on the shape only,
    /// so the text inside stays crisp.
    func widgetBackground(_ radius: CGFloat = 30) -> some View {
        background(
            RoundedRectangle(cornerRadius: radius, style: .continuous)
                .fill(Theme.surface)
                .shadow(color: Color.black.opacity(0.05), radius: 18, y: 8)
        )
    }

    /// A soft fade under the status bar, so scrolled content doesn't collide with the clock.
    func statusBarFade() -> some View {
        overlay(alignment: .top) {
            LinearGradient(colors: [Theme.washTop, Theme.washTop.opacity(0)], startPoint: .top, endPoint: .bottom)
                .frame(height: 64)
                .ignoresSafeArea(edges: .top)
                .allowsHitTesting(false)
        }
    }

    /// Forms and lists on the soft page gradient instead of iOS grey.
    func paperBackground() -> some View {
        scrollContentBackground(.hidden).background(PageBackground())
    }
}

/// A photo from Data, on iPhone and (for checking the code on a Mac) macOS.
func platformImage(_ data: Data) -> Image? {
    #if canImport(UIKit)
    UIImage(data: data).map { Image(uiImage: $0) }
    #else
    NSImage(data: data).map { Image(nsImage: $0) }
    #endif
}

struct Avatar: View {
    let person: Person
    var size: CGFloat = 44

    var body: some View {
        Group {
            if let data = person.photo, let img = platformImage(data) {
                img.resizable().scaledToFill()
            } else {
                let c = Theme.personColor(person.id)
                Text(person.initials)
                    .font(.system(size: size * 0.4, weight: .semibold, design: .rounded))
                    .foregroundStyle(c)
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
                    .background(c.opacity(0.14))
            }
        }
        .frame(width: size, height: size)
        .clipShape(Circle())
    }
}

struct StatusLabel: View {
    let dose: Dose

    var body: some View {
        Label(text, systemImage: Theme.icon(dose.status))
            .font(.system(size: 15, weight: .medium, design: .rounded))
            .foregroundStyle(color)
            .labelStyle(.titleOnly)
    }

    /// Calm unless it needs you: grey when taken or later, blue when due now, amber / red for problems.
    private var color: Color {
        switch dose.status {
        case .taken: Theme.muted
        case .due: ClockTime.minutes(dose.due) > ClockTime.nowMinutes ? Theme.muted : Theme.accent
        case .missed, .flagged: Theme.color(dose.status)
        }
    }

    private var text: String {
        switch dose.status {
        case .taken: "Taken \(ClockTime.display(dose.at ?? dose.due))"
        case .due: ClockTime.minutes(dose.due) > ClockTime.nowMinutes ? "Due \(ClockTime.display(dose.due))" : "Due now"
        case .missed: "Missed"
        case .flagged: dose.at.map { "Taken \(ClockTime.display($0))" } ?? "Check"
        }
    }
}

/// Chip-style row of times, each removable.
struct TimeChips: View {
    @Binding var times: [String]

    var body: some View {
        FlowRow {
            ForEach(times.sorted { ClockTime.minutes($0) < ClockTime.minutes($1) }, id: \.self) { t in
                HStack(spacing: 6) {
                    Text(ClockTime.display(t)).font(.body.weight(.medium))
                    Button { times.removeAll { $0 == t } } label: { Image(systemName: "xmark.circle.fill") }
                        .buttonStyle(.plain)
                        .foregroundStyle(.secondary)
                }
                .padding(.horizontal, 14).padding(.vertical, 10)
                .background(Theme.surface, in: Capsule())
            }
        }
    }
}

/// Lays children out left to right, wrapping onto new lines.
struct FlowRow: Layout {
    var spacing: CGFloat = 8

    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
        arrange(proposal.width ?? 320, subviews).size
    }

    func placeSubviews(in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) {
        for (i, p) in arrange(bounds.width, subviews).points.enumerated() {
            subviews[i].place(at: CGPoint(x: bounds.minX + p.x, y: bounds.minY + p.y), proposal: .unspecified)
        }
    }

    private func arrange(_ width: CGFloat, _ subviews: Subviews) -> (points: [CGPoint], size: CGSize) {
        var pts: [CGPoint] = [], x: CGFloat = 0, y: CGFloat = 0, row: CGFloat = 0, maxX: CGFloat = 0
        for s in subviews {
            let sz = s.sizeThatFits(.unspecified)
            if x > 0 && x + sz.width > width { x = 0; y += row + spacing; row = 0 }
            pts.append(CGPoint(x: x, y: y))
            x += sz.width + spacing
            row = max(row, sz.height)
            maxX = max(maxX, x)
        }
        return (pts, CGSize(width: maxX, height: y + row))
    }
}

extension View {
    /// iOS-only modifiers, so the same files also type-check on a Mac.
    func inlineTitle() -> some View {
        #if os(iOS)
        navigationBarTitleDisplayMode(.inline)
        #else
        self
        #endif
    }

    func urlField() -> some View {
        #if os(iOS)
        keyboardType(.URL).textInputAutocapitalization(.never).autocorrectionDisabled()
        #else
        self
        #endif
    }

    func wordsField() -> some View {
        #if os(iOS)
        textInputAutocapitalization(.words)
        #else
        self
        #endif
    }
}
