import Foundation
import Vision
import AppKit

guard CommandLine.arguments.count > 1,
      let image = NSImage(contentsOfFile: CommandLine.arguments[1]),
      let cg = image.cgImage(forProposedRect: nil, context: nil, hints: nil) else {
    fputs("Bild konnte nicht geöffnet werden\n", stderr); exit(1)
}
let request = VNRecognizeTextRequest()
request.recognitionLevel = .accurate
request.recognitionLanguages = ["de-DE", "en-US"]
request.usesLanguageCorrection = true
do {
    try VNImageRequestHandler(cgImage: cg).perform([request])
    print((request.results ?? []).compactMap { $0.topCandidates(1).first?.string }.joined(separator: "\n"))
} catch {
    fputs("\(error)\n", stderr); exit(1)
}
