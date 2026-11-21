// Draws Squint's app icon: the Tab5's screen with Squint's wink (one round eye, one happy squint).
//   swift tools/make-icon.swift      (from ios/) -> writes the PNGs into the AppIcon asset
import AppKit

let out = "Squint/Assets.xcassets/AppIcon.appiconset"
let size = 1024.0

func hex(_ h: UInt32, _ a: Double = 1) -> NSColor {
    NSColor(srgbRed: Double((h >> 16) & 0xFF) / 255, green: Double((h >> 8) & 0xFF) / 255,
            blue: Double(h & 0xFF) / 255, alpha: a)
}

/// background: the page behind the screen. bezel: the screen's rim.
func icon(background: NSColor?, bezel: NSColor, eyes: NSColor, file: String) {
    let rep = NSBitmapImageRep(bitmapDataPlanes: nil, pixelsWide: Int(size), pixelsHigh: Int(size),
                               bitsPerSample: 8, samplesPerPixel: 4, hasAlpha: true, isPlanar: false,
                               colorSpaceName: .deviceRGB, bytesPerRow: 0, bitsPerPixel: 0)!
    NSGraphicsContext.current = NSGraphicsContext(bitmapImageRep: rep)
    let c = size / 2

    if let background {                                   // the dark/tinted icons stay transparent
        background.setFill()
        NSRect(x: 0, y: 0, width: size, height: size).fill()
    }

    // the screen, like the Tab5 sitting on the counter
    let screen = NSRect(x: c - 400, y: c - 310, width: 800, height: 620)
    let rim = NSBezierPath(roundedRect: screen.insetBy(dx: -22, dy: -22), xRadius: 190, yRadius: 190)
    bezel.setFill(); rim.fill()
    hex(0x0B0B0D).setFill()
    NSBezierPath(roundedRect: screen, xRadius: 170, yRadius: 170).fill()

    // the camera dot above the eyes
    hex(0x3A383C).setFill()
    NSBezierPath(ovalIn: NSRect(x: c - 18, y: screen.maxY - 70, width: 36, height: 36)).fill()

    // left eye: wide open
    eyes.setFill()
    let r = 112.0, eyeY = c - 20
    NSBezierPath(ovalIn: NSRect(x: c - 160 - r, y: eyeY - r, width: 2 * r, height: 2 * r)).fill()

    // right eye: the happy squint, an upside-down U
    let squint = NSBezierPath()
    squint.appendArc(withCenter: NSPoint(x: c + 160, y: eyeY - 40), radius: 98, startAngle: 20, endAngle: 160)
    squint.lineWidth = 58
    squint.lineCapStyle = .round
    eyes.setStroke(); squint.stroke()

    NSGraphicsContext.current = nil
    try! rep.representation(using: .png, properties: [:])!.write(to: URL(fileURLWithPath: "\(out)/\(file)"))
    print("wrote \(out)/\(file)")
}

try! FileManager.default.createDirectory(atPath: out, withIntermediateDirectories: true)
icon(background: hex(0xF4EFE6), bezel: hex(0x17161A), eyes: .white, file: "icon.png")          // paper
icon(background: nil, bezel: hex(0x2C2A2E), eyes: .white, file: "icon-dark.png")               // dark mode
icon(background: nil, bezel: hex(0x6E6A66), eyes: .white, file: "icon-tinted.png")             // tinted
