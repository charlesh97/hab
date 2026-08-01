//
//  Models.swift
//  Balloon Dashboard
//
//  Created by Charles Hood on 11/23/25.
//

import Foundation

// MARK: - WebSocket Data Models

struct SpectrumData: Codable {
    let f: [Double]  // frequencies in Hz
    let p: [Double]  // power in dB
    let fc: Double   // center frequency in Hz
    let span: Double // frequency span in Hz
}

struct EngineStatus: Codable {
    let running: Bool
    let tx_active: Bool
    let device_connected: Bool
    let frequency: Double
    let symbol_rate: Double
    let uptime_sec: Double?
    let pipeline: PipelineStatus?
    let error_count: Int?
    let last_error: String?
}

struct PipelineStatus: Codable {
    let running: Bool
    let file_path: String
    let bitrate: Double
}

// MARK: - WebSocket Message Types

enum WsMessageType: String {
    case spectrum
    case status
}

struct WsIncomingMessage: Codable {
    let type: String
    let data: DataValue?
}

// Flexible data value - try both known types
enum DataValue: Codable {
    case spectrum(SpectrumData)
    case status(EngineStatus)
    
    init(from decoder: Decoder) throws {
        let container = try decoder.singleValueContainer()
        if let spectrum = try? container.decode(SpectrumData.self) {
            self = .spectrum(spectrum)
        } else if let status = try? container.decode(EngineStatus.self) {
            self = .status(status)
        } else {
            throw DecodingError.dataCorruptedError(in: container, debugDescription: "Unknown data type")
        }
    }
    
    func encode(to encoder: Encoder) throws {
        var container = encoder.singleValueContainer()
        switch self {
        case .spectrum(let s):
            try container.encode(s)
        case .status(let s):
            try container.encode(s)
        }
    }
}

// MARK: - Waterfall Buffer

class WaterfallBuffer: ObservableObject {
    @Published var lines: [[Double]] = []
    @Published var centerFrequency: Double = 915e6
    @Published var frequencySpan: Double = 2e6
    @Published var minPower: Double = -120
    @Published var maxPower: Double = -30
    
    let maxLines = 256
    let bins = 256
    private var cachedMinP: Double = -120
    private var cachedMaxP: Double = -30
    
    func addSpectrum(_ spectrum: SpectrumData) {
        // Interpolate the spectrum data to fixed bin count
        let interpolated = interpolate(frequencies: spectrum.f, powers: spectrum.p, bins: bins)
        
        // Track power range for dynamic scaling
        if let min = interpolated.min(), let max = interpolated.max() {
            cachedMinP = min(cachedMinP, min)
            cachedMaxP = max(cachedMaxP, max)
            // Smooth the range adaptation
            minPower = cachedMinP - 3
            maxPower = cachedMaxP + 3
        }
        
        centerFrequency = spectrum.fc
        frequencySpan = spectrum.span
        
        // Add to buffer (newest at index 0)
        lines.insert(interpolated, at: 0)
        if lines.count > maxLines {
            lines.removeLast()
        }
    }
    
    func reset() {
        lines.removeAll()
        cachedMinP = -120
        cachedMaxP = -30
    }
    
    private func interpolate(frequencies f: [Double], powers p: [Double], bins: Int) -> [Double] {
        guard f.count == p.count, f.count >= 2 else {
            return Array(repeating: cachedMinP, count: bins)
        }
        
        let fMin = f.first!
        let fMax = f.last!
        let fRange = fMax - fMin
        
        guard fRange > 0 else {
            return Array(repeating: p.first ?? cachedMinP, count: bins)
        }
        
        var result = [Double](repeating: cachedMinP, count: bins)
        for i in 0..<bins {
            let targetFreq = fMin + (Double(i) / Double(bins - 1)) * fRange
            
            // Find the two surrounding points for interpolation
            var lowerIdx = 0
            for j in 0..<(f.count - 1) {
                if f[j] <= targetFreq && f[j + 1] >= targetFreq {
                    lowerIdx = j
                    break
                }
            }
            
            // Linear interpolation
            if lowerIdx < f.count - 1 {
                let t = (targetFreq - f[lowerIdx]) / (f[lowerIdx + 1] - f[lowerIdx])
                result[i] = p[lowerIdx] + t * (p[lowerIdx + 1] - p[lowerIdx])
            } else {
                result[i] = p[lowerIdx]
            }
        }
        
        return result
    }
}
