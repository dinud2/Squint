import SwiftUI
#if canImport(UIKit)
import UIKit
#else
import AppKit
#endif

/// Squint's look: warm paper, black ink, and Squint's own signal colours
/// (sage = taken, amber = check this, red = STOP). Everything else stays monochrome.
enum Theme {
    static let paper   = Color(light: 0xF4EFE6, dark: 0x0F0E10)     // page
    static let surface = Color(light: 0xFFFCF6, dark: 0x1B1A1D)     // cards
    static let ink     = Color(light: 0x17161A, dark: 0xF4EFE6)     // text, buttons
    static let line    = Color(light: 0x17161A, dark: 0xF4EFE6, opacity: 0.09)
    static let muted   = Color(light: 0x6E6A66, dark: 0x9C978F)

    static let taken   = Color(light: 0x3F8F5E, dark: 0x6CC08A)     // sage
    static let missed  = Color(light: 0xD9861C, dark: 0xF0A030)     // Squint's amber
    static let flagged = Color(light: 0xD93F45, dark: 0xF0585D)     // Squint's red
    static let due     = muted
    static let accent  = ink
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
    static func display(_ size: CGFloat, _ weight: Font.Weight = .heavy) -> Font {
        .system(size: size, weight: weight, design: .rounded)
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
