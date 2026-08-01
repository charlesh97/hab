//
//  ContentView.swift
//  Balloon Dashboard
//
//  Created by Charles Hood on 11/23/25.
//

import SwiftUI

// MARK: - Content View (Mission Dashboard)

struct ContentView: View {
    @StateObject private var wsClient = WebSocketClient()
    @State private var showSettings = false
    @State private var serverURL = "ws://localhost:8765"
    @State private var filePath = ""
    @State private var isShowingFilePicker = false
    
    var body: some View {
        GeometryReader { geometry in
            ZStack {
                // Background
                Color.black.ignoresSafeArea()
                StarfieldView().ignoresSafeArea()
                
                VStack(spacing: 0) {
                    // 1. Connection Status Bar
                    connectionStatusBar
                    
                    // 2. Main content (Waterfall + Telemetry panel)
                    HStack(spacing: 16) {
                        // Spectrum Waterfall (~50% width)
                        waterfallSection
                            .frame(width: geometry.size.width * 0.55)
                        
                        // Telemetry Panel (~25% width)
                        telemetryPanel
                            .frame(width: geometry.size.width * 0.22)
                    }
                    .padding(.horizontal, 20)
                    .padding(.vertical, 12)
                    
                    // 3. Pipeline Controls (bottom)
                    pipelineControls
                        .padding(.horizontal, 20)
                        .padding(.bottom, 16)
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
                
                // Floating Settings button
                VStack {
                    HStack {
                        Spacer()
                        Button(action: { showSettings = true }) {
                            Image(systemName: "gearshape.fill")
                                .font(.system(size: 16))
                                .foregroundColor(.white)
                                .frame(width: 36, height: 36)
                                .background(Circle().fill(.ultraThinMaterial))
                                .shadow(color: .black.opacity(0.3), radius: 6)
                        }
                        .buttonStyle(.plain)
                        .padding(.top, 8)
                        .padding(.trailing, 24)
                    }
                    Spacer()
                }
            }
        }
        .preferredColorScheme(.dark)
        .sheet(isPresented: $showSettings) {
            SettingsView(wsClient: wsClient)
        }
        .onAppear {
            serverURL = wsClient.getServerURL()
        }
    }
    
    // MARK: - Connection Status Bar
    
    private var connectionStatusBar: some View {
        HStack(spacing: 12) {
            // Status indicator
            Circle()
                .fill(wsClient.isConnected ? Color.green : Color.red)
                .frame(width: 10, height: 10)
                .shadow(color: (wsClient.isConnected ? Color.green : Color.red).opacity(0.6), radius: 4)
            
            Text(wsClient.isConnected ? "Connected" : "Disconnected")
                .font(.system(size: 13, weight: .semibold, design: .monospaced))
                .foregroundColor(wsClient.isConnected ? .green : .red)
            
            // Server URL field
            TextField("ws://localhost:8765", text: $serverURL)
                .textFieldStyle(.plain)
                .font(.system(size: 12, design: .monospaced))
                .foregroundColor(.white)
                .frame(width: 200)
                .padding(.horizontal, 8)
                .padding(.vertical, 4)
                .background(Color.white.opacity(0.1))
                .cornerRadius(4)
            
            // Connect/Disconnect button
            Button(action: toggleConnection) {
                Text(wsClient.isConnected ? "Disconnect" : "Connect")
                    .font(.system(size: 12, weight: .semibold))
                    .foregroundColor(.white)
                    .padding(.horizontal, 14)
                    .padding(.vertical, 6)
                    .background(
                        RoundedRectangle(cornerRadius: 6)
                            .fill(wsClient.isConnected ? Color.red.opacity(0.7) : Color.green.opacity(0.7))
                    )
            }
            .buttonStyle(.plain)
            
            if let error = wsClient.connectionError {
                Text(error)
                    .font(.system(size: 11, design: .monospaced))
                    .foregroundColor(.red.opacity(0.8))
                    .lineLimit(1)
            }
            
            Spacer()
            
            // Uptime display
            if let status = wsClient.engineStatus, let uptime = status.uptime_sec {
                HStack(spacing: 4) {
                    Image(systemName: "clock.fill")
                        .font(.system(size: 10))
                    Text(formatUptime(uptime))
                }
                .font(.system(size: 11, design: .monospaced))
                .foregroundColor(.white.opacity(0.6))
            }
        }
        .padding(.horizontal, 20)
        .padding(.vertical, 10)
        .background(Color.white.opacity(0.05))
    }
    
    // MARK: - Waterfall Section
    
    private var waterfallSection: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(spacing: 8) {
                Image(systemName: "waveform.path.ecg")
                    .foregroundColor(.cyan)
                    .font(.system(size: 14))
                Text("Spectrum Waterfall")
                    .font(.system(size: 15, weight: .bold))
                    .foregroundColor(.white.opacity(0.9))
                Spacer()
                if let spectrum = wsClient.spectrumData {
                    let fcMHz = spectrum.fc / 1e6
                    let spanMHz = spectrum.span / 1e6
                    Text("\(String(format: "%.1f", fcMHz)) MHz ± \(String(format: "%.1f", spanMHz / 2)) MHz")
                        .font(.system(size: 11, design: .monospaced))
                        .foregroundColor(.white.opacity(0.5))
                }
            }
            
            WaterfallView(buffer: wsClient.waterfallBuffer)
                .frame(maxWidth: .infinity, maxHeight: .infinity)
        }
        .padding(16)
        .background {
            RoundedRectangle(cornerRadius: 16)
                .fill(.ultraThinMaterial)
                .overlay(
                    RoundedRectangle(cornerRadius: 16)
                        .stroke(Color.white.opacity(0.15), lineWidth: 1)
                )
        }
    }
    
    // MARK: - Telemetry Panel
    
    private var telemetryPanel: some View {
        let status = wsClient.engineStatus
        
        return VStack(alignment: .leading, spacing: 10) {
            // Header
            HStack(spacing: 8) {
                Image(systemName: "chart.bar.fill")
                    .foregroundColor(.blue)
                    .font(.system(size: 14))
                Text("Telemetry")
                    .font(.system(size: 15, weight: .bold))
                    .foregroundColor(.white.opacity(0.9))
                Spacer()
            }
            
            Divider().background(Color.white.opacity(0.15))
            
            ScrollView {
                VStack(alignment: .leading, spacing: 10) {
                    // Frequency
                    TelemetryRow(
                        label: "Frequency",
                        value: formatFrequency(status?.frequency ?? 0),
                        icon: "antenna.radiowaves.left.and.right",
                        color: .cyan
                    )
                    
                    // Symbol Rate
                    TelemetryRow(
                        label: "Symbol Rate",
                        value: formatSymbolRate(status?.symbol_rate ?? 0),
                        icon: "waveform",
                        color: .blue
                    )
                    
                    // TX Status
                    TelemetryRow(
                        label: "TX Status",
                        value: (status?.tx_active ?? false) ? "Running" : "Stopped",
                        icon: "antenna.radiowaves.left.and.right",
                        color: (status?.tx_active ?? false) ? .green : .red
                    )
                    
                    // Pipeline Status
                    TelemetryRow(
                        label: "Pipeline",
                        value: (status?.pipeline?.running ?? false) ? "Running" : "Stopped",
                        icon: "flowchart.fill",
                        color: (status?.pipeline?.running ?? false) ? .green : .red
                    )
                    
                    // SNR (from spectrum data if available, or from status)
                    if let spectrum = wsClient.spectrumData {
                        TelemetryRow(
                            label: "SNR",
                            value: formatSNR(spectrum: spectrum),
                            icon: "gauge.with.dots.needle.33percent",
                            color: .orange
                        )
                    } else {
                        TelemetryRow(
                            label: "SNR",
                            value: "-- dB",
                            icon: "gauge.with.dots.needle.33percent",
                            color: .white.opacity(0.4)
                        )
                    }
                    
                    // Bitrate
                    TelemetryRow(
                        label: "Bitrate",
                        value: formatBitrate(status?.pipeline?.bitrate ?? 0),
                        icon: "arrow.up.arrow.down",
                        color: .green
                    )
                    
                    // Uptime
                    if let uptime = status?.uptime_sec {
                        TelemetryRow(
                            label: "Uptime",
                            value: formatUptime(uptime),
                            icon: "clock.fill",
                            color: .white.opacity(0.8)
                        )
                    }
                    
                    // Device connected
                    if let devConnected = status?.device_connected {
                        TelemetryRow(
                            label: "Device",
                            value: devConnected ? "Connected" : "Disconnected",
                            icon: "memorychip.fill",
                            color: devConnected ? .green : .red
                        )
                    }
                    
                    // Error count
                    if let errCount = status?.error_count, errCount > 0 {
                        TelemetryRow(
                            label: "Errors",
                            value: "\(errCount)",
                            icon: "exclamationmark.triangle.fill",
                            color: .red
                        )
                    }
                }
            }
        }
        .padding(16)
        .background {
            RoundedRectangle(cornerRadius: 16)
                .fill(.ultraThinMaterial)
                .overlay(
                    RoundedRectangle(cornerRadius: 16)
                        .stroke(Color.white.opacity(0.15), lineWidth: 1)
                )
        }
    }
    
    // MARK: - Pipeline Controls
    
    private var pipelineControls: some View {
        VStack(spacing: 10) {
            HStack(spacing: 8) {
                Image(systemName: "flowchart")
                    .foregroundColor(.purple)
                    .font(.system(size: 14))
                Text("Pipeline Controls")
                    .font(.system(size: 15, weight: .bold))
                    .foregroundColor(.white.opacity(0.9))
                Spacer()
            }
            
            HStack(spacing: 12) {
                // File path field
                HStack(spacing: 6) {
                    Image(systemName: "doc.fill")
                        .foregroundColor(.white.opacity(0.5))
                        .font(.system(size: 12))
                    
                    TextField("File path...", text: $filePath)
                        .textFieldStyle(.plain)
                        .font(.system(size: 12, design: .monospaced))
                        .foregroundColor(.white)
                    
                    Button("Browse") {
                        isShowingFilePicker = true
                    }
                    .font(.system(size: 11, weight: .semibold))
                    .foregroundColor(.white)
                    .padding(.horizontal, 10)
                    .padding(.vertical, 4)
                    .background(Color.white.opacity(0.15))
                    .cornerRadius(4)
                    .buttonStyle(.plain)
                }
                .padding(.horizontal, 10)
                .padding(.vertical, 6)
                .background(Color.white.opacity(0.08))
                .cornerRadius(8)
                
                Spacer()
                
                // Pipeline buttons
                HStack(spacing: 8) {
                    // Start/Stop Pipeline
                    let isPipelineRunning = wsClient.engineStatus?.pipeline?.running ?? false
                    Button(action: {
                        if isPipelineRunning {
                            wsClient.stopPipeline()
                        } else {
                            wsClient.startPipeline(filePath: filePath)
                        }
                    }) {
                        HStack(spacing: 4) {
                            Image(systemName: isPipelineRunning ? "stop.fill" : "play.fill")
                                .font(.system(size: 10))
                            Text(isPipelineRunning ? "Stop Pipeline" : "Start Pipeline")
                                .font(.system(size: 12, weight: .semibold))
                        }
                        .foregroundColor(.white)
                        .padding(.horizontal, 14)
                        .padding(.vertical, 7)
                        .background(
                            RoundedRectangle(cornerRadius: 8)
                                .fill(isPipelineRunning ? Color.red.opacity(0.7) : Color.blue.opacity(0.7))
                        )
                    }
                    .buttonStyle(.plain)
                    .disabled(!wsClient.isConnected)
                    .opacity(wsClient.isConnected ? 1 : 0.4)
                    
                    // Start/Stop TX
                    let isTXActive = wsClient.engineStatus?.tx_active ?? false
                    Button(action: {
                        if isTXActive {
                            wsClient.stopTX()
                        } else {
                            wsClient.startTX()
                        }
                    }) {
                        HStack(spacing: 4) {
                            Image(systemName: isTXActive ? "stop.fill" : "antenna.radiowaves.left.and.right")
                                .font(.system(size: 10))
                            Text(isTXActive ? "Stop TX" : "Start TX")
                                .font(.system(size: 12, weight: .semibold))
                        }
                        .foregroundColor(.white)
                        .padding(.horizontal, 14)
                        .padding(.vertical, 7)
                        .background(
                            RoundedRectangle(cornerRadius: 8)
                                .fill(isTXActive ? Color.red.opacity(0.7) : Color.green.opacity(0.7))
                        )
                    }
                    .buttonStyle(.plain)
                    .disabled(!wsClient.isConnected)
                    .opacity(wsClient.isConnected ? 1 : 0.4)
                }
            }
        }
        .padding(16)
        .background {
            RoundedRectangle(cornerRadius: 16)
                .fill(.ultraThinMaterial)
                .overlay(
                    RoundedRectangle(cornerRadius: 16)
                        .stroke(Color.white.opacity(0.15), lineWidth: 1)
                )
        }
        .fileImporter(isPresented: $isShowingFilePicker, allowedContentTypes: [.data]) { result in
            if case .success(let url) = result {
                filePath = url.path
            }
        }
    }
    
    // MARK: - Actions
    
    private func toggleConnection() {
        if wsClient.isConnected {
            wsClient.disconnect()
        } else {
            wsClient.setServerURL(serverURL)
            wsClient.connect()
        }
    }
    
    // MARK: - Formatting Helpers
    
    private func formatFrequency(_ hz: Double) -> String {
        if hz >= 1e9 {
            return String(format: "%.4f GHz", hz / 1e9)
        } else if hz >= 1e6 {
            return String(format: "%.3f MHz", hz / 1e6)
        } else if hz >= 1e3 {
            return String(format: "%.1f kHz", hz / 1e3)
        } else {
            return String(format: "%.0f Hz", hz)
        }
    }
    
    private func formatSymbolRate(_ rate: Double) -> String {
        if rate >= 1e6 {
            return String(format: "%.2f Msps", rate / 1e6)
        } else if rate >= 1e3 {
            return String(format: "%.1f ksps", rate / 1e3)
        } else {
            return String(format: "%.0f sps", rate)
        }
    }
    
    private func formatBitrate(_ bps: Double) -> String {
        if bps >= 1e6 {
            return String(format: "%.1f Mbps", bps / 1e6)
        } else if bps >= 1e3 {
            return String(format: "%.1f kbps", bps / 1e3)
        } else {
            return String(format: "%.0f bps", bps)
        }
    }
    
    private func formatUptime(_ seconds: Double) -> String {
        let hrs = Int(seconds) / 3600
        let mins = (Int(seconds) % 3600) / 60
        let secs = Int(seconds) % 60
        if hrs > 0 {
            return String(format: "%dh %02dm %02ds", hrs, mins, secs)
        } else {
            return String(format: "%02dm %02ds", mins, secs)
        }
    }
    
    private func formatSNR(spectrum: SpectrumData) -> String {
        // Estimate SNR from spectrum: peak - noise floor
        guard !spectrum.p.isEmpty else { return "-- dB" }
        let sorted = spectrum.p.sorted()
        // Use bottom 25% as noise floor estimate
        let noiseIdx = max(sorted.count / 4, 1)
        let noiseFloor = sorted[noiseIdx]
        let peak = sorted.last ?? noiseFloor
        let snr = peak - noiseFloor
        return String(format: "%.1f dB", snr)
    }
}

// MARK: - Telemetry Row Component

struct TelemetryRow: View {
    let label: String
    let value: String
    let icon: String
    let color: Color
    
    var body: some View {
        HStack(spacing: 8) {
            Image(systemName: icon)
                .foregroundColor(color)
                .font(.system(size: 12))
                .frame(width: 16)
            
            Text(label)
                .font(.system(size: 11))
                .foregroundColor(.white.opacity(0.6))
            
            Spacer()
            
            Text(value)
                .font(.system(size: 12, weight: .semibold, design: .monospaced))
                .foregroundColor(.white)
        }
        .padding(.vertical, 2)
    }
}

// MARK: - Starfield Background

struct StarfieldView: View {
    let starCount = 300
    let globalSpeedMultiplier: Double = 0.25
    
    @State private var stars: [Star] = []
    
    struct Star {
        var id = UUID()
        var x: Double
        var y: Double
        var size: Double
        var opacity: Double
        var velocityX: Double
        var velocityY: Double
    }
    
    var body: some View {
        TimelineView(.animation) { timeline in
            Canvas { context, size in
                let timeInterval = timeline.date.timeIntervalSinceReferenceDate
                
                for star in stars {
                    let xPos = (star.x + (star.velocityX * timeInterval * globalSpeedMultiplier)).truncatingRemainder(dividingBy: 1.0)
                    let yPos = (star.y + (star.velocityY * timeInterval * globalSpeedMultiplier)).truncatingRemainder(dividingBy: 1.0)
                    
                    let finalX = xPos < 0 ? 1 + xPos : xPos
                    let finalY = yPos < 0 ? 1 + yPos : yPos
                    
                    let rect = CGRect(
                        x: finalX * size.width,
                        y: finalY * size.height,
                        width: star.size,
                        height: star.size
                    )
                    
                    let twinkleSpeed = star.size * 2.0
                    let twinkle = abs(sin(timeInterval * twinkleSpeed)) * 0.4 + 0.6
                    
                    context.opacity = star.opacity * twinkle
                    context.fill(Path(ellipseIn: rect), with: .color(.white))
                }
            }
        }
        .background(Color.black)
        .onAppear { createStars() }
    }
    
    func createStars() {
        stars.removeAll()
        for _ in 0..<starCount {
            let depth = Double.random(in: 0.1...1.0)
            let calculatedSize = 1.0 + (depth * 3.0)
            let directionX = Double.random(in: -0.5...0.5)
            let directionY = Double.random(in: -0.5...0.5)
            let calculatedVelX = directionX * depth
            let calculatedVelY = directionY * depth
            let calculatedOpacity = 0.3 + (depth * 0.7)
            
            stars.append(Star(
                x: Double.random(in: 0...1),
                y: Double.random(in: 0...1),
                size: calculatedSize,
                opacity: calculatedOpacity,
                velocityX: calculatedVelX,
                velocityY: calculatedVelY
            ))
        }
    }
}

#Preview {
    ContentView()
        .frame(width: 1600, height: 1000)
}
