// PDFの各ページを画像にして、macOSのVisionで文字を読む（画像だけのPDF用）
// 使い方: pdfocr <pdf> [開始頁] [終了頁]
import Foundation
import PDFKit
import Vision
import CoreGraphics

let 引 = CommandLine.arguments
guard 引.count >= 2, let 書 = PDFDocument(url: URL(fileURLWithPath: 引[1])) else {
    FileHandle.standardError.write("PDFが開けない\n".data(using: .utf8)!)
    exit(1)
}
let 始 = 引.count >= 3 ? (Int(引[2]) ?? 1) : 1
let 終 = 引.count >= 4 ? (Int(引[3]) ?? 書.pageCount) : 書.pageCount
var 出 = ""
for i in (始 - 1)..<min(終, 書.pageCount) {
    guard let 頁 = 書.page(at: i) else { continue }
    let 枠 = 頁.bounds(for: .mediaBox)
    let 倍: CGFloat = 2.0        // 小さい字を読むために拡大する
    let w = Int(枠.width * 倍), h = Int(枠.height * 倍)
    guard let 場 = CGContext(data: nil, width: w, height: h, bitsPerComponent: 8,
                             bytesPerRow: 0, space: CGColorSpaceCreateDeviceRGB(),
                             bitmapInfo: CGImageAlphaInfo.premultipliedFirst.rawValue) else { continue }
    場.setFillColor(CGColor(red: 1, green: 1, blue: 1, alpha: 1))
    場.fill(CGRect(x: 0, y: 0, width: w, height: h))
    場.scaleBy(x: 倍, y: 倍)
    頁.draw(with: .mediaBox, to: 場)
    guard let 絵 = 場.makeImage() else { continue }
    let 頼 = VNRecognizeTextRequest()
    頼.recognitionLevel = .accurate
    頼.recognitionLanguages = ["ja-JP", "en-US"]
    頼.usesLanguageCorrection = true
    let 係 = VNImageRequestHandler(cgImage: 絵, options: [:])
    do { try 係.perform([頼]) } catch { continue }
    guard let 結 = 頼.results else { continue }
    // ★読んだ場所（y座標）の順に並べる。Visionは信頼度順で返すことがある
    let 並 = 結.sorted { a, b in
        if abs(a.boundingBox.midY - b.boundingBox.midY) > 0.01 {
            return a.boundingBox.midY > b.boundingBox.midY
        }
        return a.boundingBox.minX < b.boundingBox.minX
    }
    for o in 並 {
        if let c = o.topCandidates(1).first { 出 += c.string + "\n" }
    }
}
print(出)
