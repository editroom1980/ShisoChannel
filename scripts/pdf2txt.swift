// PDFの中の文章を取り出す（macOS用。市の手引き・しおり・時刻表をAIの資料にするため）。
// 使い方: swift pdf2txt.swift <入力.pdf>  → 文章を標準出力へ（無ければ空）
// GitHub Actions(Linux)では pdftotext（poppler）を使う。これは手元のMac用
import Foundation
import PDFKit

let args = CommandLine.arguments
guard args.count >= 2 else { print(""); exit(2) }
guard let doc = PDFDocument(url: URL(fileURLWithPath: args[1])) else { exit(1) }
var out = ""
for i in 0..<doc.pageCount {
    if let t = doc.page(at: i)?.string { out += t + "\n" }
    if out.count > 60000 { break }   // 異常に長い資料の保険
}
print(out)
