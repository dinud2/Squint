import SwiftUI
#if canImport(UIKit)
import UIKit
#else
import AppKit
#endif

// MARK: - The capsule: one dose, drawn as a two-tone pill

struct PillGlyph: View {
    var status: Dose.Status
    var width: CGFloat = 30
    var upright = false

    var body: some View {
        let c = Theme.color(status)
        let h = width * 0.42
        ZStack {
            switch status {
            case .due:
                Capsule().strokeBorder(Theme.ink.opacity(0.45), style: StrokeStyle(lineWidth: 1.6, dash: [3, 2.5]))
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

/// The ink button: a black capsule with paper text.
struct InkButtonStyle: ButtonStyle {
    var prominent = true
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(Theme.display(17, .bold))
            .foregroundStyle(prominent ? Theme.paper : Theme.ink)
            .padding(.vertical, 15).padding(.horizontal, 22)
            .frame(maxWidth: .infinity)
            .background(prominent ? Theme.ink : Theme.line, in: Capsule())
            .scaleEffect(configuration.isPressed ? 0.97 : 1)
            .animation(.spring(duration: 0.2), value: configuration.isPressed)
    }
}

/// A small uppercase label above a group, like on a pharmacy label.
struct Eyebrow: View {
    let text: String
    init(_ text: String) { self.text = text }
    var body: some View {
        Text(text.uppercased())
            .font(.system(size: 12, weight: .heavy, design: .rounded))
            .kerning(1.4)
            .foregroundStyle(Theme.muted)
    }
}

extension View {
    /// A card on the paper.
    func paperCard(_ radius: CGFloat = 26) -> some View {
        padding(18)
            .background(Theme.surface, in: RoundedRectangle(cornerRadius: radius, style: .continuous))
            .overlay(RoundedRectangle(cornerRadius: radius, style: .continuous).strokeBorder(Theme.line))
    }

    /// Forms and lists on paper instead of iOS grey.
    func paperBackground() -> some View {
        scrollContentBackground(.hidden).background(Theme.paper.ignoresSafeArea())
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
                Text(person.initials)
                    .font(.system(size: size * 0.4, weight: .semibold, design: .rounded))
                    .foregroundStyle(Theme.paper)
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
                    .background(Theme.ink)
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
            .font(.subheadline.weight(.medium))
            .foregroundStyle(Theme.color(dose.status))
            .labelStyle(.titleOnly)
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
                .padding(.horizontal, 12).padding(.vertical, 8)
                .background(Theme.surface, in: Capsule())
                .overlay(Capsule().strokeBorder(Theme.line))
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
