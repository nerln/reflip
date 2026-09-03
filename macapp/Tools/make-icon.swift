// Draws the reflip mark at every size an .icns is packed from.
//
// A coin caught mid-flip: an ellipse foreshortened on its vertical axis, tilted, with
// its edge showing underneath and a thin bright rim. That is the whole tool in one
// shape. The watermark is a biased coin flipped once per token, and what reflip does is
// flip every one of them again; a picture of text, or of a shield, would say "document"
// or "security" and neither is what happens here.
//
// The drawing lives only in this file. If a site mark ever appears it has to be these
// same shapes, and it has to be changed here at the same time.
//
// Two things were tried and rejected. A full circle: it is a coin lying still, and the
// tool is about the flip rather than the coin. A pair of coins, one faint, to say
// motion: at sixteen pixels it reads as a loading indicator, which is a picture of
// waiting rather than of changing.
//
//   swiftc -O -parse-as-library make-icon.swift -o make-icon
//   ./make-icon <output-directory>

import AppKit
import CoreGraphics
import Foundation

struct Palette {
    /// The house near-black, with a little blue in it. A neutral black next to the gold
    /// reads as dead, the same way it does in rada and scriba.
    static let ink = CGColor(red: 0x0C / 255, green: 0x0E / 255, blue: 0x12 / 255, alpha: 1)
    /// The rim, and the brightest thing in the tile.
    static let paper = CGColor(red: 0xED / 255, green: 0xF1 / 255, blue: 0xF3 / 255, alpha: 1)
    static let coin = CGColor(red: 0xD9 / 255, green: 0xA4 / 255, blue: 0x41 / 255, alpha: 0.92)
    /// The edge of the coin, seen because it is turning.
    static let edge = CGColor(red: 0xD9 / 255, green: 0xA4 / 255, blue: 0x41 / 255, alpha: 0.34)
}

/// One tile. Coordinates are the mark's own 64 unit square, scaled up.
func draw(size: Int) -> CGImage? {
    let space = CGColorSpaceCreateDeviceRGB()
    guard let ctx = CGContext(data: nil, width: size, height: size, bitsPerComponent: 8,
                              bytesPerRow: 0, space: space,
                              bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue)
    else { return nil }

    // macOS insets its icons inside the tile rather than filling it edge to edge.
    let inset = CGFloat(size) * 0.09
    let side = CGFloat(size) - inset * 2
    let unit = side / 64.0

    ctx.setFillColor(Palette.ink)
    ctx.addPath(CGPath(roundedRect: CGRect(x: inset, y: inset, width: side, height: side),
                       cornerWidth: 14 * unit, cornerHeight: 14 * unit, transform: nil))
    ctx.fillPath()

    // Everything below is drawn about the centre of the plate, tilted. The tilt is what
    // makes it a coin in the air rather than a plate on a table, and it is small: past
    // about fifteen degrees the foreshortened ellipse starts to read as an eye.
    ctx.saveGState()
    ctx.translateBy(x: inset + 32 * unit, y: inset + 32 * unit)
    ctx.rotate(by: -0.22)

    // Wide and shallow: a circle seen from nearly edge on.
    let face = CGRect(x: -21 * unit, y: -8 * unit, width: 42 * unit, height: 16 * unit)

    // The thickness, peeking out below. Without it the shape is flat, and flat reads as
    // an ellipse rather than as a coin.
    ctx.setFillColor(Palette.edge)
    ctx.fillEllipse(in: face.offsetBy(dx: 0, dy: -3 * unit))

    ctx.setFillColor(Palette.coin)
    ctx.fillEllipse(in: face)

    // The rim last, so it sits on top of both. Thin: at two units it is an eighth of
    // the height of the ellipse it draws, and anything heavier stops being a rim and
    // starts being the border of a plate. It is the brightest colour in the tile so
    // that it still separates the coin from the ink at sixteen pixels.
    ctx.setStrokeColor(Palette.paper)
    ctx.setLineWidth(2.0 * unit)
    ctx.strokeEllipse(in: face)

    ctx.restoreGState()
    return ctx.makeImage()
}

func write(_ image: CGImage, to url: URL) throws {
    let rep = NSBitmapImageRep(cgImage: image)
    guard let data = rep.representation(using: .png, properties: [:]) else {
        throw NSError(domain: "make-icon", code: 1)
    }
    try data.write(to: url)
}

@main
struct Main {
    static func main() {
        guard CommandLine.arguments.count > 1 else {
            print("usage: make-icon <output-directory>"); exit(1)
        }
        let out = URL(fileURLWithPath: CommandLine.arguments[1])
        try? FileManager.default.createDirectory(at: out, withIntermediateDirectories: true)

        let tiles: [(String, Int)] = [
            ("icon_16x16", 16), ("icon_16x16@2x", 32),
            ("icon_32x32", 32), ("icon_32x32@2x", 64),
            ("icon_128x128", 128), ("icon_128x128@2x", 256),
            ("icon_256x256", 256), ("icon_256x256@2x", 512),
            ("icon_512x512", 512), ("icon_512x512@2x", 1024),
        ]
        for (name, size) in tiles {
            guard let image = draw(size: size) else { print("failed at \(size)"); exit(2) }
            do { try write(image, to: out.appendingPathComponent("\(name).png")) }
            catch { print("could not write \(name): \(error)"); exit(3) }
        }
        print("wrote \(tiles.count) tiles to \(out.path)")
    }
}
