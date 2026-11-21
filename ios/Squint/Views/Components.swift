import SwiftUI
#if canImport(UIKit)
import UIKit
#else
import AppKit
#endif

enum Theme {
    static let accent = Color(red: 0.20, green: 0.52, blue: 0.56)       // calm teal
    static let taken = Color(red: 0.22, green: 0.6, blue: 0.36)
    static let due = Color.secondary
    static let missed = Color(red: 0.85, green: 0.45, blue: 0.1)
    static let flagged = Color(red: 0.82, green: 0.2, blue: 0.2)
    static let card = Color.gray.opacity(0.08)

    static func color(_ s: Dose.Status) -> Color {
        switch s {
        case .taken: taken
        case .due: due
        case .missed: missed
        case .flagged: flagged
        }
    }

    static func icon(_ s: Dose.Status) -> String {
        switch s {
        case .taken: "checkmark.circle.fill"
        case .due: "circle"
        case .missed: "exclamationmark.circle.fill"
        case .flagged: "hand.raised.circle.fill"
        }
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
                    .foregroundStyle(.white)
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
                    .background(Theme.accent.gradient)
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
            .labelStyle(.titleAndIcon)
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
                .background(Theme.accent.opacity(0.12), in: Capsule())
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
