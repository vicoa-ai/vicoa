// Applies the macOS app-icon shape to a full-bleed square master.
//
// macOS does NOT round app icons for you. macOS 26 (Tahoe) masks legacy .icns
// icons at render time, which makes a square master *look* correct there while
// rendering as a hard-cornered square on macOS 15 and earlier, and on any
// runtime-set dock icon (app.dock.setIcon). The shape has to be baked in.
//
// Apple's grid: on a 1024 canvas the icon body is 824x824 centred (100pt
// margin) with a 185.4pt corner radius, using continuous ("squircle")
// curvature rather than a circular arc — hence CALayer.cornerCurve, which is
// Apple's own implementation of that curve.
//
// Usage: swift icon-shape.swift <master.png> <out.png> <canvas> <inset> <radius>

import AppKit
import QuartzCore

let args = CommandLine.arguments
guard args.count == 6,
      let canvas = Int(args[3]),
      let inset = Double(args[4]),
      let radius = Double(args[5])
else {
    FileHandle.standardError.write(
        "usage: icon-shape.swift <master.png> <out.png> <canvas> <inset> <radius>\n".data(using: .utf8)!)
    exit(2)
}
let masterPath = args[1]
let outPath = args[2]

guard let master = NSImage(contentsOfFile: masterPath) else {
    FileHandle.standardError.write("icon-shape: cannot read \(masterPath)\n".data(using: .utf8)!)
    exit(3)
}
var proposed = CGRect(x: 0, y: 0, width: master.size.width, height: master.size.height)
guard let cgMaster = master.cgImage(forProposedRect: &proposed, context: nil, hints: nil) else {
    FileHandle.standardError.write("icon-shape: cannot decode \(masterPath)\n".data(using: .utf8)!)
    exit(3)
}

let side = Double(canvas) - inset * 2
let full = CGRect(x: 0, y: 0, width: canvas, height: canvas)
let body = CGRect(x: inset, y: inset, width: side, height: side)

func newCanvas() -> (NSBitmapImageRep, CGContext)? {
    guard let rep = NSBitmapImageRep(
        bitmapDataPlanes: nil, pixelsWide: canvas, pixelsHigh: canvas,
        bitsPerSample: 8, samplesPerPixel: 4, hasAlpha: true, isPlanar: false,
        colorSpaceName: .deviceRGB, bytesPerRow: canvas * 4, bitsPerPixel: 32)
    else { return nil }
    rep.size = NSSize(width: canvas, height: canvas)
    guard let ctx = NSGraphicsContext(bitmapImageRep: rep) else { return nil }
    ctx.cgContext.clear(full)
    return (rep, ctx.cgContext)
}

// 1. Bake the squircle into a mask. CALayer.render(in:) draws from the layer's
//    bounds at the context origin and ignores the frame origin, so the inset
//    comes from translating the CTM rather than from layer.frame.
guard let (maskRep, maskCg) = newCanvas() else { exit(4) }
let shape = CALayer()
shape.bounds = CGRect(x: 0, y: 0, width: side, height: side)
shape.backgroundColor = NSColor.white.cgColor
shape.cornerRadius = radius
shape.cornerCurve = .continuous
shape.masksToBounds = true
maskCg.saveGState()
maskCg.translateBy(x: inset, y: inset)
shape.render(in: maskCg)
maskCg.restoreGState()
guard let maskImage = maskRep.cgImage else { exit(4) }

// 2. Draw the master into the body rect, then keep only what the mask covers.
//    destinationIn multiplies destination alpha by source alpha.
guard let (rep, cg) = newCanvas() else { exit(4) }
cg.draw(cgMaster, in: body)
cg.setBlendMode(.destinationIn)
cg.draw(maskImage, in: full)

guard let png = rep.representation(using: .png, properties: [:]) else { exit(5) }
do {
    try png.write(to: URL(fileURLWithPath: outPath))
} catch {
    FileHandle.standardError.write("icon-shape: cannot write \(outPath): \(error)\n".data(using: .utf8)!)
    exit(6)
}
