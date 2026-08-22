// PDFをページごとにPNGへ描き直す（macOS用。ごみカレンダー等をテレビで映すため）。
// 使い方: swift pdf2png.swift <入力.pdf> <出力の頭> [横幅px]
//   → 出力の頭_1.png, 出力の頭_2.png, … とページ数だけ作る。ページ数を標準出力に出す
// なぜ: テレビのWebViewはPDFを表示できない。sipsは1枚目しか変換できず72dpiで字が潰れる。
//       GitHub Actions(Linux)では pdftoppm を使う。これは手元のMac用
import Foundation
import CoreGraphics
import ImageIO
import UniformTypeIdentifiers

let args = CommandLine.arguments
guard args.count >= 3 else { print("使い方: swift pdf2png.swift 入力.pdf 出力の頭 [横幅px]"); exit(2) }
let 幅指定 = args.count >= 4 ? CGFloat(Double(args[3]) ?? 1600) : 1600

guard let doc = CGPDFDocument(URL(fileURLWithPath: args[1]) as CFURL) else {
    FileHandle.standardError.write("PDFが読めない: \(args[1])\n".data(using: .utf8)!); exit(1)
}
for i in 1...doc.numberOfPages {
    guard let page = doc.page(at: i) else { continue }
    let box = page.getBoxRect(.mediaBox)
    let 倍 = 幅指定 / box.width
    let w = Int(box.width * 倍), h = Int(box.height * 倍)
    guard let ctx = CGContext(data: nil, width: w, height: h, bitsPerComponent: 8, bytesPerRow: 0,
                              space: CGColorSpaceCreateDeviceRGB(),
                              bitmapInfo: CGImageAlphaInfo.noneSkipLast.rawValue) else { exit(1) }
    ctx.setFillColor(CGColor(red: 1, green: 1, blue: 1, alpha: 1))   // 下地は白（透過だと黒く映る）
    ctx.fill(CGRect(x: 0, y: 0, width: w, height: h))
    ctx.scaleBy(x: 倍, y: 倍)
    ctx.translateBy(x: -box.origin.x, y: -box.origin.y)
    ctx.drawPDFPage(page)
    guard let img = ctx.makeImage(),
          let dst = CGImageDestinationCreateWithURL(
              URL(fileURLWithPath: "\(args[2])_\(i).png") as CFURL, UTType.png.identifier as CFString, 1, nil)
    else { exit(1) }
    CGImageDestinationAddImage(dst, img, nil)
    CGImageDestinationFinalize(dst)
}
print(doc.numberOfPages)
