import SwiftUI
#if canImport(UIKit)
import UIKit
#else
import AppKit
#endif

/// Squint's look: a soft, cool page, white rounded cards, and one light blue that carries
/// the app. Amber (check this) and red (STOP) appear only when something needs attention.
enum Theme {
    static let paper   = Color(light: 0xEEF2F7, dark: 0x0E1116)     // page
    static let surface = Color(light: 0xFFFFFF, dark: 0x1A1E25)     // cards
    static let ink     = Color(light: 0x14171C, dark: 0xF1F4F8)     // text
    static let line    = Color(light: 0x14171C, dark: 0xF1F4F8, opacity: 0.07)
    static let muted   = Color(light: 0x8A929E, dark: 0x8E97A3)

    // The page wash: sky at the top, aqua at the bottom, a light glow top-left.
    static let washTop    = Color(light: 0xDDEBFA, dark: 0x111A26)
    static let washBottom = Color(light: 0xE4F3F2, dark: 0x0F1719)
    static let washGlow   = Color(light: 0xFFFFFF, dark: 0x1B2A3D, opacity: 0.7)

    static let accent     = Color(light: 0x3D95EA, dark: 0x5AADF5)  // Squint blue: the primary colour
    static let accentSoft = Color(light: 0xE3EFFC, dark: 0x1C2E44)  // icon bubbles, soft fills
    static let bubble     = Color(light: 0xF1F4F8, dark: 0x252A33)  // neutral icon bubbles
    static let navBar     = Color(light: 0x14171C, dark: 0x252A33)  // the floating tab bar

    // A few soft category colours, so each kind of widget is easy to spot (like a health dashboard).
    // Blue stays the primary colour; these only tint small icons, avatars and gauges.
    static let teal    = Color(light: 0x1FA79B, dark: 0x3CC7BA)
    static let indigo  = Color(light: 0x5B6CF0, dark: 0x8190FF)
    static let green   = Color(light: 0x2FAE74, dark: 0x4CCB8E)
    static let coral   = Color(light: 0xEE7D5B, dark: 0xF59A7E)
    static let pink    = Color(light: 0xE0679B, dark: 0xEE8BB5)

    /// Each person gets their own colour (avatar, gauge, medicine icons), so they're easy to tell apart.
    static func personColor(_ id: String) -> Color {
        let palette = [coral, pink, indigo, green, teal]
        let n = id.unicodeScalars.reduce(0) { ($0 &* 31 &+ Int($1.value)) & 0xFFFF }
        return palette[n % palette.count]
    }

    static let taken   = green                                      // a taken dose: calm green
    static let missed  = Color(light: 0xE0912B, dark: 0xF0A030)     // Squint's amber, used sparingly
    static let flagged = Color(light: 0xE0484E, dark: 0xF0585D)     // Squint's red, only for STOP-type events
    static let due     = muted
    static let card    = surface

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

    /// Big rounded words, like on Squint's screen.
    /// Clean, rounded words. Heavy and bold are softened to semibold for the light, airy look.
    static func display(_ size: CGFloat, _ weight: Font.Weight = .semibold) -> Font {
        let w: Font.Weight = (weight == .heavy || weight == .black || weight == .bold) ? .semibold : weight
        return .system(size: size, weight: w, design: .rounded)
    }

    /// Big numbers on widgets ("5/7", "79%"): light and large, like a health dashboard.
    static func number(_ size: CGFloat) -> Font {
        .system(size: size, weight: .medium, design: .rounded)
    }
}

extension Color {
    /// One colour for light mode and one for dark, from hex.
    init(light: UInt32, dark: UInt32, opacity: Double = 1) {
        func comps(_ h: UInt32) -> (Double, Double, Double) {
            (Double((h >> 16) & 0xFF) / 255, Double((h >> 8) & 0xFF) / 255, Double(h & 0xFF) / 255)
        }
        let l = comps(light), d = comps(dark)
        #if canImport(UIKit)
        self.init(uiColor: UIColor { t in
            let c = t.userInterfaceStyle == .dark ? d : l
            return UIColor(red: c.0, green: c.1, blue: c.2, alpha: opacity)
        })
        #else
        self.init(nsColor: NSColor(name: nil) { a in
            let c = a.bestMatch(from: [.darkAqua, .aqua]) == .darkAqua ? d : l
            return NSColor(red: c.0, green: c.1, blue: c.2, alpha: opacity)
        })
        #endif
    }
}
