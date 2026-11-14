import AVFoundation
import AppKit

// usage: frames.swift <video> <outdir> <every_seconds> <max_width>
let a = CommandLine.arguments
let url = URL(fileURLWithPath: a[1])
let out = a[2]
let step = Double(a[3]) ?? 3.0
let maxW = CGFloat(Double(a[4]) ?? 600)
try? FileManager.default.createDirectory(atPath: out, withIntermediateDirectories: true)
let asset = AVURLAsset(url: url)
let dur = CMTimeGetSeconds(asset.duration)
let track = asset.tracks(withMediaType: .video).first
let size = track?.naturalSize ?? .zero
print("duration \(dur)s size \(size)")
let gen = AVAssetImageGenerator(asset: asset)
gen.appliesPreferredTrackTransform = true
gen.requestedTimeToleranceBefore = .zero
gen.requestedTimeToleranceAfter = .zero
gen.maximumSize = CGSize(width: maxW, height: maxW * 3)
var t = 0.0
var n = 0
while t < dur {
    let time = CMTime(seconds: t, preferredTimescale: 600)
    if let img = try? gen.copyCGImage(at: time, actualTime: nil) {
        let rep = NSBitmapImageRep(cgImage: img)
        if let data = rep.representation(using: .jpeg, properties: [.compressionFactor: 0.7]) {
            let name = String(format: "%@/f_%04d.jpg", out, Int(t))
            try? data.write(to: URL(fileURLWithPath: name))
            n += 1
        }
    }
    t += step
}
print("wrote \(n) frames")
