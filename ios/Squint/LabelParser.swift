import Foundation
import ImageIO
import Vision

/// What we could read off a pharmacy label. Everything is a suggestion: the caregiver confirms it.
nonisolated struct ParsedLabel: Equatable {
    var name = ""
    var strength = ""
    var times: [String] = []
    var notes: [String] = []
}

nonisolated enum LabelParser {
    /// Words that appear on labels but are never the drug name.
    private static let boilerplate = ["RX", "PHARMACY", "TAKE", "QTY", "REFILL", "DR", "DATE", "TABLET", "CAPSULE",
                                      "BY MOUTH", "ORALLY", "DISCARD", "CAUTION", "WARNING", "PATIENT", "PRESCRIBER",
                                      "DAILY", "MORNING", "EVENING", "BEDTIME", "FILLED", "EXP", "LOT", "DIN", "NDC"]
    private static let strengthRe = try! NSRegularExpression(
        pattern: #"(\d+(?:[.,]\d+)?)\s*(mg|mcg|µg|g|ml|iu|units?)\b"#, options: [.caseInsensitive])

    static func parse(_ lines: [String]) -> ParsedLabel {
        var out = ParsedLabel()
        let text = lines.joined(separator: "\n")
        let lower = text.lowercased()

        // strength: the first "5 mg" style match
        var strengthLine: String?
        for line in lines {
            let r = NSRange(line.startIndex..., in: line)
            if let m = strengthRe.firstMatch(in: line, range: r),
               let num = Range(m.range(at: 1), in: line), let unit = Range(m.range(at: 2), in: line) {
                let u = line[unit].lowercased()
                out.strength = "\(line[num].replacingOccurrences(of: ",", with: ".")) \(u == "iu" ? "IU" : u)"
                strengthLine = line
                break
            }
        }

        // name: the words before the strength on that line ("WARFARIN 5 MG"), else the first
        // mostly-letters line that isn't label boilerplate
        if let line = strengthLine, let m = strengthRe.firstMatch(in: line, range: NSRange(line.startIndex..., in: line)),
           let r = Range(m.range, in: line) {
            out.name = cleanName(String(line[..<r.lowerBound]))
        }
        if out.name.isEmpty {
            for line in lines {
                let up = line.uppercased()
                let letters = line.filter(\.isLetter).count
                if letters >= 4, Double(letters) / Double(max(line.count, 1)) > 0.7,
                   !boilerplate.contains(where: { up.contains($0) }) {
                    out.name = cleanName(line)
                    break
                }
            }
        }

        // how often -> suggested times
        func has(_ words: [String]) -> Bool { words.contains { lower.contains($0) } }
        if has(["four times", "4 times", "qid"]) {
            out.times = ["08:00", "12:00", "16:00", "20:00"]
        } else if has(["three times", "3 times", "tid"]) {
            out.times = ["08:00", "14:00", "20:00"]
        } else if has(["twice", "two times", "2 times", "bid", "every 12 hours"]) {
            out.times = ["08:00", "20:00"]
        } else if has(["bedtime", "at night", "before bed"]) {
            out.times = ["21:00"]
        } else if has(["every evening", "in the evening"]) {
            out.times = ["18:00"]
        } else if has(["once daily", "once a day", "every morning", "daily", "every day"]) {
            out.times = ["08:00"]
        }

        // notes worth keeping
        for (key, note) in [("with food", "With food"), ("with a meal", "With food"),
                            ("empty stomach", "On an empty stomach"), ("alcohol", "Avoid alcohol"),
                            ("do not crush", "Do not crush or chew"), ("drowsiness", "May cause drowsiness"),
                            ("plenty of water", "With a full glass of water")] where lower.contains(key) {
            if !out.notes.contains(note) { out.notes.append(note) }
        }
        return out
    }

    private static func cleanName(_ s: String) -> String {
        let words = s.split(whereSeparator: { !$0.isLetter && $0 != "-" })
            .filter { w in !boilerplate.contains(w.uppercased()) }
            .prefix(3)
        return words.map { $0.prefix(1).uppercased() + $0.dropFirst().lowercased() }.joined(separator: " ")
    }

    /// Read the text in a photo of a label (Apple's on-device text recognition; works in the simulator).
    static func readText(from imageData: Data) async -> [String] {
        guard let src = CGImageSourceCreateWithData(imageData as CFData, nil),
              let image = CGImageSourceCreateImageAtIndex(src, 0, nil) else { return [] }
        return await withCheckedContinuation { cont in
            DispatchQueue.global(qos: .userInitiated).async {
                let req = VNRecognizeTextRequest()
                req.recognitionLevel = .accurate
                req.usesLanguageCorrection = true
                try? VNImageRequestHandler(cgImage: image).perform([req])     // runs synchronously
                let lines = (req.results ?? [])
                    .sorted { $0.boundingBox.minY > $1.boundingBox.minY }      // top of the label first
                    .compactMap { $0.topCandidates(1).first?.string }
                cont.resume(returning: lines)
            }
        }
    }
}
