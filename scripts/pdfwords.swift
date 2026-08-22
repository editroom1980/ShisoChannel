// PDFの文字を「座標つき」で取り出す（macOS用）。
// バス時刻表の表組みを復元するために使う：バス停の行と時刻の列は、
// 文字の並び順では崩れるが、紙の上の位置（座標）なら正確に分かる。
// 使い方: pdfwords <入力.pdf> <ページ番号>
// 出力: 1語1行のTSV「語 \t x \t y \t 幅 \t 高さ」（yは上から。単位pt）
import Foundation
import PDFKit

let args = CommandLine.arguments
guard args.count >= 3, let pageNo = Int(args[2]) else { print(""); exit(2) }
guard let doc = PDFDocument(url: URL(fileURLWithPath: args[1])),
      let page = doc.page(at: pageNo - 1) else { exit(1) }
let text = page.string ?? ""
let ns = text as NSString
let pageH = page.bounds(for: .mediaBox).height

var i = 0
while i < ns.length {
    // 空白を飛ばす
    while i < ns.length,
          let sc = Unicode.Scalar(ns.character(at: i)),
          CharacterSet.whitespacesAndNewlines.contains(sc) { i += 1 }
    if i >= ns.length { break }
    var j = i
    while j < ns.length {
        guard let sc = Unicode.Scalar(ns.character(at: j)) else { break }
        if CharacterSet.whitespacesAndNewlines.contains(sc) { break }
        j += 1
    }
    let range = NSRange(location: i, length: j - i)
    let word = ns.substring(with: range)
    if let sel = page.selection(for: range) {
        let b = sel.bounds(for: page)
        // PDFの座標は下が原点なので、上からのyに直す
        let yTop = pageH - b.origin.y - b.size.height
        print("\(word)\t\(Int(b.origin.x))\t\(Int(yTop))\t\(Int(b.size.width))\t\(Int(b.size.height))")
    }
    i = j
}
