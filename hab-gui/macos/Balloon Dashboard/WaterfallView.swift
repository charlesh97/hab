//
//  WaterfallView.swift
//  Balloon Dashboard
//
//  Created by Charles Hood on 11/23/25.
//

import SwiftUI

/// Real-time spectrum waterfall display using Canvas for performance.
struct WaterfallView: View {
    @ObservedObject var buffer: WaterfallBuffer
    
    var body: some View {
        Canvas { context, size in
            drawWaterfall(context: &context, size: size)
            drawOverlay(context: &context, size: size)
        }
        .background(Color.black.opacity(0.3))
        .clipShape(RoundedRectangle(cornerRadius: 12))
        .overlay(
            RoundedRectangle(cornerRadius: 12)
                .stroke(Color.white.opacity(0.15), lineWidth: 1)
        )
        .overlay(alignment: .topLeading) {
            // Color bar legend
            colorBar
                .padding(8)
        }
    }
    
    // MARK: - Waterfall Drawing
    
    private func drawWaterfall(context: inout GraphicsContext, size: CGSize) {
        guard !buffer.lines.isEmpty else {
            // Draw "Waiting for data" text
            let text = Text("Waiting for spectrum data...")
                .font(.system(size: 14, design: .monospaced))
                .foregroundColor(.white.opacity(0.4))
            context.draw(text, at: CGPoint(x: size.width / 2, y: size.height / 2))
            return
        }
        
        let lineCount = buffer.lines.count
        let rowHeight = size.height / CGFloat(max(lineCount, 1))
        let binCount = buffer.bins
        let colWidth = size.width / CGFloat(max(binCount, 1))
        
        // Draw each pixel as a tiny rect (waterfall scrolls: newest at top)
        for row in 0..<lineCount {
            let powerLine = buffer.lines[row]
            for col in 0..<min(powerLine.count, binCount) {
                let power = powerLine[col]
                let color = colorForPower(power, minP: buffer.minPower, maxP: buffer.maxPower)
                let rect = CGRect(
                    x: CGFloat(col) * colWidth,
                    y: CGFloat(row) * rowHeight,
                    width: colWidth + 0.5, // slight overlap to avoid gaps
                    height: rowHeight + 0.5
                )
                context.fill(Path(rect), with: .color(color))
            }
        }
    }
    
    // MARK: - Overlay (axis labels, grid)
    
    private func drawOverlay(context: inout GraphicsContext, size: CGSize) {
        let fc = buffer.centerFrequency
        let span = buffer.frequencySpan
        let fMin = (fc - span / 2) / 1e6  // MHz
        let fMax = (fc + span / 2) / 1e6  // MHz
        
        // Frequency labels on X axis
        let freqSteps = 4
        for i in 0...freqSteps {
            let fraction = CGFloat(i) / CGFloat(freqSteps)
            let freqMHz = fMin + Double(fraction) * (fMax - fMin)
            let x = fraction * size.width
            
            let text: Text
            if freqMHz >= 1000 {
                text = Text(String(format: "%.1fG", freqMHz / 1000))
                    .font(.system(size: 10, design: .monospaced))
                    .foregroundColor(.white.opacity(0.5))
            } else {
                text = Text(String(format: "%.1fM", freqMHz))
                    .font(.system(size: 10, design: .monospaced))
                    .foregroundColor(.white.opacity(0.5))
            }
            
            let textSize = text.measure(in: CGSize(width: 80, height: 20))
            context.draw(text, at: CGPoint(x: x, y: size.height - 12))
            
            // Grid line
            var gridPath = Path()
            gridPath.move(to: CGPoint(x: x, y: 0))
            gridPath.addLine(to: CGPoint(x: x, y: size.height - 20))
            context.stroke(gridPath, with: .color(.white.opacity(0.08)), lineWidth: 0.5)
        }
        
        // Time labels on Y axis (right side)
        let timeSteps = min(buffer.lines.count / 8, 4)
        if timeSteps > 0 {
            for i in 0...timeSteps {
                let fraction = CGFloat(i) / CGFloat(timeSteps)
                let y = size.height - fraction * (size.height - 20)
                let lineIndex = Int(Double(buffer.lines.count) * Double(i) / Double(timeSteps))
                
                if lineIndex < buffer.lines.count {
                    let seconds = Double(lineIndex) * 0.1 // assuming ~10Hz update rate or use elapsed
                    let text = Text(String(format: "-%.1fs", seconds))
                        .font(.system(size: 9, design: .monospaced))
                        .foregroundColor(.white.opacity(0.4))
                    context.draw(text, at: CGPoint(x: size.width - 5, y: y), anchor: .trailing)
                }
            }
        }
    }
    
    // MARK: - Color Mapping
    
    /// Maps a power level (dB) to a color: dark blue → cyan → green → yellow → red
    private func colorForPower(_ power: Double, minP: Double, maxP: Double) -> Color {
        let range = maxP - minP
        guard range > 0 else { return .black }
        
        let t = (power - minP) / range
        let clamped = min(max(t, 0), 1)
        
        // Five-stop color gradient
        switch clamped {
        case ..<0.25:
            // Dark blue to blue
            let t2 = clamped / 0.25
            return Color(
                red: 0,
                green: t2 * 0.1,
                blue: 0.1 + t2 * 0.4
            )
        case ..<0.5:
            // Blue to cyan
            let t2 = (clamped - 0.25) / 0.25
            return Color(
                red: 0,
                green: 0.1 + t2 * 0.5,
                blue: 0.5 + t2 * 0.3
            )
        case ..<0.75:
            // Cyan to green/yellow
            let t2 = (clamped - 0.5) / 0.25
            return Color(
                red: t2 * 0.5,
                green: 0.6 + t2 * 0.3,
                blue: 0.8 * (1 - t2)
            )
        default:
            // Yellow/green to red
            let t2 = (clamped - 0.75) / 0.25
            return Color(
                red: 0.5 + t2 * 0.5,
                green: 0.9 * (1 - t2 * 0.7),
                blue: 0
            )
        }
    }
    
    // MARK: - Color Bar Legend
    
    private var colorBar: some View {
        VStack(alignment: .leading, spacing: 2) {
            Text("dB")
                .font(.system(size: 8, design: .monospaced))
                .foregroundColor(.white.opacity(0.5))
            
            HStack(spacing: 0) {
                // Color gradient strip
                ForEach(0..<20, id: \.self) { i in
                    let fraction = Double(i) / 19.0
                    // Reverse: high at top
                    let power = buffer.maxPower - fraction * (buffer.maxPower - buffer.minPower)
                    RoundedRectangle(cornerRadius: 0)
                        .fill(colorForPower(power, minP: buffer.minPower, maxP: buffer.maxPower))
                        .frame(width: 6, height: 80)
                }
            }
            .overlay(
                RoundedRectangle(cornerRadius: 2)
                    .stroke(Color.white.opacity(0.2), lineWidth: 0.5)
            )
            
            Text(String(format: "%.0f", buffer.maxPower))
                .font(.system(size: 7, design: .monospaced))
                .foregroundColor(.white.opacity(0.4))
            Text(String(format: "%.0f", buffer.minPower))
                .font(.system(size: 7, design: .monospaced))
                .foregroundColor(.white.opacity(0.4))
        }
    }
}
