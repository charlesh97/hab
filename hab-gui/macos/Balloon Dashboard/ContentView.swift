//
//  ContentView.swift
//  Balloon Dashboard
//
//  Created by Charles Hood on 11/23/25.
//

import Charts
import MapKit
import SwiftUI

struct ContentView: View {
    // Dummy telemetry data
    @State private var altitude: Double = 34.9  // km ASL
    @State private var latitude: Double = 35.169389
    @State private var longitude: Double = -80.895919
    @State private var temperature: Double = -54.5  // Celsius
    @State private var internalTemp: Double = 22.3  // Celsius
    @State private var batteryPercent: Int = 82
    @State private var batteryVoltage: Double = 12.4  // volts
    @State private var powerConsumption: Double = 8.5  // watts
    @State private var cpuPercent: Int = 31
    @State private var cpuTemp: Double = 45.2  // Celsius
    @State private var ascentRate: Double = 4.7  // m/s
    @State private var speed: Double = 73.0  // km/h
    @State private var heading: Double = 69.0  // degrees
    @State private var barometricPressure: Double = 8.5  // hPa
    @State private var frequency: String = "436.500 MHz"
    @State private var rssi: Double = -91.0  // dBm
    @State private var snr: Double = 29.7  // dB
    @State private var noiseFloor: Double = -120.0  // dBm
    @State private var downlink: String = "2.3 Mbps"
    @State private var uplink: String = "512 kbps"

    // Timer for 1Hz updates
    @State private var updateTimer: Timer?
    
    // Mission timer
    @State private var missionStartTime: Date = Date()
    @State private var missionTime: String = "T+ 00:00:00"
    
    // Link status
    @State private var linkStatus: String = "Nominal"
    
    // Animation trigger for REC indicator
    @State private var recPulse: Bool = false
    
    // GPS track history for drawing path
    @State private var gpsTrack: [CLLocationCoordinate2D] = []
    
    // Settings sheet presentation
    @State private var showSettings = false



    // Signal bar heights (simulated varying signal)
    private var signalBarHeights: [CGFloat] {
        let baseHeight: CGFloat = 5
        let maxHeight: CGFloat = 35
        let rssiRange: Double = -120.0 - (-40.0) // -120 to -40 dBm
        let normalizedRssi = (rssi - (-120.0)) / rssiRange // 0.0 to 1.0
        
        return (0..<20).map { index in
            let position = Double(index) / 19.0
            let variation = Double.random(in: -0.1...0.1)
            let height = baseHeight + (maxHeight - baseHeight) * CGFloat(normalizedRssi + variation * (1.0 - position))
            return max(baseHeight, min(maxHeight, height))
        }
    }

    // Update all telemetry data with realistic random variations
    private func updateTelemetry() {
        // Altitude - gradually increasing with small variations
        altitude = max(0, altitude + Double.random(in: -0.1...0.3))

        // GPS coordinates - small random drift
        latitude += Double.random(in: 0.0001...0.0010)
        longitude += Double.random(in: -0.0001...0.0010)
        
        // Add current position to GPS track
        let currentPosition = CLLocationCoordinate2D(latitude: latitude, longitude: longitude)
        gpsTrack.append(currentPosition)
        
        // Limit track history to last 1000 points to prevent memory issues
        if gpsTrack.count > 1000 {
            gpsTrack.removeFirst()
        }

        // Temperature - varies with altitude, small fluctuations
        temperature = -54.5 - (altitude - 34.9) * 0.5 + Double.random(in: -0.5...0.5)

        // Internal temperature - more stable, slight variations
        internalTemp = 22.3 + Double.random(in: -0.3...0.3)

        // Battery - gradually decreasing with small variations
        batteryPercent = max(0, min(100, batteryPercent + Int.random(in: -1...0)))
        batteryVoltage =
            12.4 - (82 - Double(batteryPercent)) * 0.015 + Double.random(in: -0.02...0.02)

        // Power consumption - varies with system load
        powerConsumption = 8.5 + Double.random(in: -0.3...0.5)

        // CPU - varies with activity
        cpuPercent = max(0, min(100, cpuPercent + Int.random(in: -2...3)))
        cpuTemp = 45.2 + Double(cpuPercent - 31) * 0.1 + Double.random(in: -0.5...0.5)

        // Ascent rate - varies with atmospheric conditions
        ascentRate = max(0, ascentRate + Double.random(in: -0.2...0.2))

        // Speed - varies with wind
        speed = max(0, speed + Double.random(in: -2...2))

        // Heading - gradual changes
        heading = (heading + Double.random(in: -20...20)).truncatingRemainder(dividingBy: 360)
        if heading < 0 { heading += 360 }

        // Barometric pressure - decreases with altitude
        barometricPressure = 1013.25 * exp(-altitude / 8.5) + Double.random(in: -0.1...0.1)

        // Signal metrics - varies with distance and conditions
        rssi = max(-120, min(-40, rssi + Double.random(in: -2...2)))
        snr = max(0, min(50, snr + Double.random(in: -1...1)))
        noiseFloor = -120.0 + Double.random(in: -2...2)

        // Data rates - varies slightly
        let downlinkValue = 2.3 + Double.random(in: -0.1...0.1)
        downlink = String(format: "%.1f Mbps", downlinkValue)

        let uplinkValue = 512.0 + Double.random(in: -10...10)
        uplink = String(format: "%.0f kbps", uplinkValue)
        
        // Update mission timer
        let elapsed = Date().timeIntervalSince(missionStartTime)
        let hours = Int(elapsed) / 3600
        let minutes = (Int(elapsed) % 3600) / 60
        let seconds = Int(elapsed) % 60
        missionTime = String(format: "T+ %02d:%02d:%02d", hours, minutes, seconds)
        
        // Update link status based on signal quality
        if rssi > -85 && snr > 25 {
            linkStatus = "Nominal"
        } else if rssi > -95 && snr > 15 {
            linkStatus = "Degraded"
        } else {
            linkStatus = "Poor"
        }
    }

    // Calculate number of columns based on width
    private func columnsForWidth(_ width: CGFloat) -> [GridItem] {
        let minCardWidth: CGFloat = 350
        let spacing: CGFloat = 20
        let padding: CGFloat = 60  // 30 on each side

        let availableWidth = width - padding
        let columns = max(1, Int(availableWidth / (minCardWidth + spacing)))
        let actualColumns = min(columns, 3)  // Max 3 columns

        return Array(repeating: GridItem(.flexible(), spacing: spacing), count: actualColumns)
    }

    var body: some View {
        GeometryReader { geometry in
            ZStack {
                // Background image
                StarfieldView()
                    .ignoresSafeArea()
                //Color.black
                    
                ScrollView {
                    VStack(alignment: .leading, spacing: 0) {
                        // Header
                        HStack {
                            Text("Balloon Dashboard")
                                .font(.system(size: 24, weight: .bold))
                                .foregroundColor(.white)
                            
                            Spacer()
                            
                            // Mission Timer
                            HStack(spacing: 8) {
                                Image(systemName: "clock.fill")
                                    .foregroundColor(.white.opacity(0.8))
                                Text(missionTime)
                                    .font(.system(size: 16, weight: .semibold, design: .monospaced))
                                    .foregroundColor(.white)
                            }
                            .padding(.horizontal, 12)
                            .padding(.vertical, 6)
                            .background(Color.white.opacity(0.1))
                            .cornerRadius(8)
                            
                            // Status Indicators
                            HStack(spacing: 12) {
                                // Live Status
                                HStack(spacing: 6) {
                                    Circle()
                                        .fill(Color.green)
                                        .frame(width: 8, height: 8)
                                        .shadow(color: Color.green.opacity(0.6), radius: 4)
                                    Text("Live")
                                        .font(.system(size: 14, weight: .semibold))
                                        .foregroundColor(.white)
                                }
                                .padding(.horizontal, 10)
                                .padding(.vertical, 6)
                                .background(Color.green.opacity(0.2))
                                .cornerRadius(6)
                                
                                // Link Status
                                HStack(spacing: 6) {
                                    Image(systemName: "antenna.radiowaves.left.and.right")
                                        .foregroundColor(linkStatus == "Nominal" ? .green : linkStatus == "Degraded" ? .yellow : .red)
                                    Text("Link: \(linkStatus)")
                                        .font(.system(size: 14, weight: .semibold))
                                        .foregroundColor(.white)
                                }
                                .padding(.horizontal, 10)
                                .padding(.vertical, 6)
                                .background(
                                    (linkStatus == "Nominal" ? Color.green : linkStatus == "Degraded" ? Color.yellow : Color.red).opacity(0.2)
                                )
                                .cornerRadius(6)
                            }
                        }
                        .padding(.horizontal, 30)
                        .padding(.top, 20)
                        .padding(.bottom, 20)
                        .frame(height: 60)

                        // Main content area - Two columns
                        HStack(alignment: .top, spacing: 20) {
                            // Left Column
                            VStack(spacing: 20) {
                                // Flight Data Card (expanded)
                                GlassCard {
                                    VStack(alignment: .leading, spacing: 16) {
                                        CardTitle(systemName: "paperplane.fill", text: "Flight Data")
                                          
                                        VStack(alignment: .leading, spacing: 16) {
                                            // First section - Sensors
                                            VStack(alignment: .leading, spacing: 12) {
                                                
                                                // Altitude Ascent and Ground Speed in one row
                                                HStack(spacing: 20){
                                                    VStack(alignment: .leading, spacing: 6){
                                                        // Altitude
                                                        Text("Altitude")
                                                            .font(.caption)
                                                            .foregroundColor(.white.opacity(0.7))
                                                        HStack(alignment: .bottom) {
                                                            VerticalProgressBar(value: altitude, maxValue: 100.0, color: .blue, width: 20, height: 50, showPercentage: false)
                                                            Text("\(String(format: "%.1f", altitude)) KM")
                                                                .font(.system(size: 14, weight: .semibold))
                                                                .foregroundColor(.white)
                                                        }.frame(width: 100)
                                                    }
                                                    VStack(alignment: .leading, spacing: 6){
                                                        // Ascent Rate
                                                        Text("Ascent")
                                                            .font(.caption)
                                                            .foregroundColor(.white.opacity(0.7))
                                                        HStack(alignment: .bottom) {
                                                            VerticalProgressBar(value: ascentRate, maxValue: 10.0, color: .green, width: 20, height: 50, showPercentage: false)
                                                            Text("\(String(format: "%.1f", ascentRate)) M/S")
                                                                .font(.system(size: 14, weight: .semibold))
                                                                .foregroundColor(.white)
                                                        }.frame(width: 100)
                                                    }
                                                    VStack(alignment: .leading, spacing: 6){
                                                        // Speed with circular gauge
                                                        Text("Ground Speed")
                                                            .font(.caption)
                                                            .foregroundColor(.white.opacity(0.7))
                                                        // Simple circular gauge representation
                                                        HStack {
                                                            ZStack {
                                                                Circle()
                                                                    .stroke(Color.white.opacity(0.2), lineWidth: 8)
                                                                    .frame(width: 50, height: 50)
                                                                Circle()
                                                                    .trim(from: 0, to: min(speed / 150.0, 1.0))
                                                                    .stroke(Color.orange, style: StrokeStyle(lineWidth: 8, lineCap: .round))
                                                                    .frame(width: 50, height: 50)
                                                                    .rotationEffect(.degrees(-90))
                                                                Text("\(Int(speed)) \nMPH")
                                                                    .font(.system(size: 10, weight: .bold))
                                                                    .foregroundColor(.white)
                                                            }
                                                            Spacer()
                                                        }.frame(width: 100)
                                                    }
                                                }
                                                
                                                // Heading with rotating compass
                                                HStack {
                                                    Text("Heading")
                                                        .font(.caption)
                                                        .foregroundColor(.white.opacity(0.7))
                                                    Spacer()
                                                    HStack(spacing: 6) {
                                                        Image(systemName: "arrow.up")
                                                            .foregroundColor(.blue)
                                                            .font(.system(size: 16, weight: .bold))
                                                            .rotationEffect(.degrees(heading))
                                                        Text("\(Int(heading))°")
                                                            .font(.system(size: 14, weight: .semibold))
                                                            .foregroundColor(.white)
                                                    }
                                                }
                                                
                                                // External Temperature with icon
                                                DataRow(
                                                    label: "External Temperature",
                                                    value:
                                                        "\(String(format: "%.1f", temperature))°C")
                                                
                                                
                                                // Barometric Pressure with icon
                                                DataRow(
                                                    label: "Barometric Pressure",
                                                    value:
                                                        "\(String(format: "%.2f", barometricPressure)) hPa"
                                                )
                                            }

                                            Divider()
                                                .background(Color.white.opacity(0.3))

                                            // Second section - Hardware
                                            VStack(alignment: .leading, spacing: 12) {

                                                // Battery Status
                                                VStack(alignment: .leading, spacing: 6){
                                                    HStack {
                                                        Image(systemName: "bolt.fill")
                                                            .foregroundColor(.yellow)
                                                            .font(.system(size: 14))
                                                        Text("Battery Status")
                                                            .font(.caption)
                                                            .foregroundColor(.white.opacity(0.7))
                                                        Spacer()
                                                        Text("\(batteryVoltage) V")
                                                            .font(.system(size: 14, weight: .semibold))
                                                            .foregroundColor(.white)
                                                    }   
                                                    ProgressView(value: Double(batteryPercent), total: 100)
                                                        .tint(batteryPercent > 70 ? .green : batteryPercent > 30 ? .orange : .red)
                                                }
                                                
                                                // Power Consumption
                                                HStack {
                                                    Image(systemName: "bolt.circle.fill")
                                                        .foregroundColor(.yellow)
                                                        .font(.system(size: 14))
                                                    DataRow(
                                                        label: "Power Consumption (W)",
                                                        value:
                                                            "\(String(format: "%.1f", powerConsumption)) W"
                                                    )
                                                }
                                                
                                                // CPU with progress bar
                                                VStack(alignment: .leading, spacing: 6) {
                                                    HStack {
                                                        Image(systemName: "cpu")
                                                            .foregroundColor(.blue)
                                                            .font(.system(size: 14))
                                                        Text("CPU")
                                                            .font(.caption)
                                                            .foregroundColor(.white.opacity(0.7))
                                                        Spacer()
                                                        Text("\(cpuPercent)%")
                                                            .font(.system(size: 14, weight: .semibold))
                                                            .foregroundColor(.white)
                                                    }
                                                    ProgressView(value: Double(cpuPercent), total: 100)
                                                        .tint(cpuPercent > 80 ? .red : cpuPercent > 50 ? .yellow : .blue)
                                                        //.background(Color.white.opacity(0.2))
                                                }
                                                
                                                // CPU Temperature
                                                HStack {
                                                    Image(systemName: "thermometer.medium")
                                                        .foregroundColor(.green)
                                                        .font(.system(size: 14))
                                                    DataRow(
                                                        label: "CPU Temperature",
                                                        value: "\(String(format: "%.1f", cpuTemp))°C")
                                                }

                                                // Internal Temperature
                                                HStack {
                                                    Image(systemName: "thermometer.medium")
                                                        .foregroundColor(.green)
                                                        .font(.system(size: 14))
                                                    DataRow(
                                                        label: "Internal Temperature",
                                                        value:
                                                            "\(String(format: "%.1f", internalTemp))°C")
                                                }
                                            }                      
                                        }
                                    }
                                    .frame(maxWidth: .infinity, alignment: .leading)
                                }

                                // Signal Connection Card
                                GlassCard {
                                    VStack(alignment: .leading, spacing: 16) {
                                        CardTitle(systemName: "antenna.radiowaves.left.and.right", text: "RF Connection")

                                        // RX Spectrum Graph
                                        SpectrumView()
                                            .frame(height: 200)
                                            .clipShape(RoundedRectangle(cornerRadius: 12))

                                        // Signal strength bars visualization
                                        VStack(alignment: .leading, spacing: 8) {
                                            HStack(spacing: 6) {
                                                Image(systemName: "chart.bar.fill")
                                                    .foregroundColor(.cyan)
                                                    .font(.system(size: 12))
                                                Text("Signal Strength")
                                                    .font(.system(size: 12, weight: .semibold))
                                                    .foregroundColor(.white.opacity(0.8))
                                            }
                                            HStack(alignment: .bottom, spacing: 3) {
                                                ForEach(0..<20, id: \.self) { index in
                                                    RoundedRectangle(cornerRadius: 2)
                                                        .fill(
                                                            index < Int((rssi + 120) / 4) ?
                                                            (rssi > -85 ? Color.green : rssi > -95 ? Color.yellow : Color.red) :
                                                            Color.blue.opacity(0.3)
                                                        )
                                                        .frame(width: 8, height: signalBarHeights[index])
                                                        .animation(.easeInOut(duration: 0.3), value: signalBarHeights[index])
                                                }
                                            }
                                            .frame(height: 40)
                                        }
                                        .padding(.vertical, 8)
                                        
                                        // 2x2 Grid of metrics with icons
                                        VStack(spacing: 12) {
                                            HStack(spacing: 12) {
                                                MetricBox(
                                                    label: "SNR",
                                                    value: "\(String(format: "%.1f", snr)) dB",
                                                    icon: "waveform.path",
                                                    iconColor: .green
                                                )
                                                MetricBox(
                                                    label: "Downlink speed",
                                                    value: downlink,
                                                    icon: "arrow.down.circle.fill",
                                                    iconColor: .blue
                                                )
                                            }
                                            HStack(spacing: 12) {
                                                MetricBox(
                                                    label: "RSSI",
                                                    value: "\(String(format: "%.0f", rssi)) dBm",
                                                    icon: "antenna.radiowaves.left.and.right",
                                                    iconColor: .cyan
                                                )
                                                MetricBox(
                                                    label: "Uplink speed",
                                                    value: uplink,
                                                    icon: "arrow.up.circle.fill",
                                                    iconColor: .green
                                                )
                                            }
                                        }
                                    }
                                    .frame(maxWidth: .infinity, alignment: .leading)
                                }
                            }
                            .frame(width: geometry.size.width * 0.4)
                            .padding(.leading, 30)

                            // Right Column
                            VStack(spacing: 20) {
                                // Live Video Feed
                                GlassCard {
                                    VStack(alignment: .leading, spacing: 12) {
                                        CardTitle(systemName: "video.fill", text: "Live Video Feed")

                                        // Add the video feed here. For now, just a placeholder image
                                        ZStack {
                                            // Placeholder image for the video feed
                                            VStack {
                                                Image("space_background")
                                                    .resizable()
                                                    .aspectRatio(contentMode: .fill)
                                                    .clipped()
                                                    .overlay {
                                                        // Grid overlay for video feed
                                                        Path { path in
                                                            for i in 0...8 {
                                                                let y = CGFloat(i) * 50
                                                                path.move(to: CGPoint(x: 0, y: y))
                                                                path.addLine(to: CGPoint(x: 1000, y: y))
                                                                path.move(to: CGPoint(x: CGFloat(i) * 125, y: 0))
                                                                path.addLine(to: CGPoint(x: CGFloat(i) * 125, y: 400))
                                                            }
                                                        }
                                                        .stroke(Color.white.opacity(0.15), lineWidth: 0.5)
                                                    }
                                            }
                                            .frame(maxHeight: 400)

                                            // Overlays positioned with VStack
                                            VStack {
                                                // "REC" overlay in the top right with pulsing animation
                                                HStack {
                                                    Spacer()
                                                    HStack(spacing: 6) {
                                                        Circle()
                                                            .fill(Color.red)
                                                            .frame(width: 12, height: 12)
                                                            .shadow(
                                                                color: Color.red.opacity(0.6),
                                                                radius: 4, x: 0, y: 0)
                                                            .opacity(recPulse ? 1.0 : 0.6)
                                                            .scaleEffect(recPulse ? 1.0 : 0.9)
                                                            .animation(
                                                                Animation.easeInOut(duration: 1.0).repeatForever(autoreverses: true),
                                                                value: recPulse
                                                            )
                                                            .onAppear {
                                                                recPulse = true
                                                            }
                                                        Text("REC")
                                                            .font(.caption)
                                                            .fontWeight(.bold)
                                                            .foregroundColor(.white)
                                                    }
                                                    .padding(10)
                                                    .background(Color.black.opacity(0.3))
                                                    .cornerRadius(8)
                                                }
                                                .padding([.top, .trailing], 12)

                                                Spacer()

                                                // Video resolution and fps in the bottom right
                                                HStack {
                                                    Spacer()
                                                    Text("1920x1080 • 30 FPS")
                                                        .font(.caption)
                                                        .foregroundColor(.white.opacity(0.8))
                                                        .padding(10)
                                                        .background(Color.black.opacity(0.25))
                                                        .cornerRadius(8)
                                                }
                                                .padding([.bottom, .trailing], 12)
                                            }
                                            .frame(maxWidth: .infinity, maxHeight: .infinity)
                                        }
                                        .frame(maxWidth: .infinity, maxHeight: 400)
                                        .clipShape(RoundedRectangle(cornerRadius: 12))
                                    }
                                    .frame(maxWidth: .infinity)
                                }

                                // Live Map View
                                GlassCard {
                                    VStack(alignment: .leading, spacing: 12) {
                                        CardTitle(systemName: "map.fill", text: "Live Map")

                                        ZStack {
                                            if #available(macOS 14.0, *) {
                                                let currentLocation = CLLocationCoordinate2D(
                                                    latitude: latitude, longitude: longitude)
                                                let region = MKCoordinateRegion(
                                                    center: currentLocation,
                                                    span: MKCoordinateSpan(
                                                        latitudeDelta: 0.08, longitudeDelta: 0.08)
                                                )

                                                Map(initialPosition: .region(region)) {
                                                    // GPS track path (dotted line)
                                                    if gpsTrack.count > 1 {
                                                        MapPolyline(coordinates: gpsTrack)
                                                            .stroke(Color.blue.opacity(0.6), style: StrokeStyle(lineWidth: 2, dash: [5, 5]))
                                                    }
                                                    
                                                    // Current position marker
                                                    Annotation(
                                                        "Balloon", coordinate: currentLocation
                                                    ) {
                                                        ZStack {
                                                            Circle()
                                                                .fill(Color.blue)
                                                                .frame(width: 18, height: 18)
                                                            Circle()
                                                                .stroke(Color.white, lineWidth: 3)
                                                                .frame(width: 26, height: 26)
                                                        }
                                                    }
                                                }
                                                .mapStyle(.standard)
                                                .cornerRadius(12)
                                            } else {
                                                ZStack {
                                                    RoundedRectangle(cornerRadius: 12)
                                                        .fill(Color.gray.opacity(0.2))
                                                    Text("Map unavailable (macOS < 12).")
                                                        .foregroundColor(.white.opacity(0.5))
                                                }
                                            }

                                            // Adding the coordinates to map view
                                            VStack {
                                                Spacer()
                                                HStack {
                                                    Spacer()
                                                    HStack(spacing: 4) {
                                                        Image(systemName: "location.fill")
                                                            .foregroundColor(.white.opacity(0.8))
                                                        Text(
                                                            "\(String(format: "%.4f", latitude))° N, \(String(format: "%.4f", longitude))°"
                                                        )
                                                        .font(.system(size: 12, weight: .medium, design: .monospaced))
                                                        .foregroundColor(.white.opacity(0.9))
                                                    }
                                                    .padding(8)
                                                    .background(Color.black.opacity(0.3))
                                                    .cornerRadius(6)
                                                }
                                                .padding(12)
                                            }
                                        }
                                        .frame(height: 300)
                                    }
                                    .frame(maxWidth: .infinity, alignment: .leading)
                                }

                            }
                            .frame(width: geometry.size.width * 0.55)
                            .padding(.trailing, 30)
                        }
                        .padding(.top, 20)

                        // Footer - Debug Console (full width)
                        GlassCard {
                            VStack(alignment: .leading, spacing: 12) {
                                CardTitle(systemName: "terminal.fill", text: "Debug Console")

                                ZStack {
                                    RoundedRectangle(cornerRadius: 12)
                                        .fill(Color.black.opacity(0.4))

                                    ScrollView {
                                        VStack(alignment: .leading, spacing: 6) {
                                            LogEntry(level: "INFO", message: "System initialized", color: .green)
                                            LogEntry(level: "INFO", message: "GPS lock acquired: 12 satellites", color: .green)
                                            LogEntry(level: "INFO", message: "Telemetry link established", color: .green)
                                            LogEntry(level: "DEBUG", message: "Battery voltage: \(String(format: "%.2f", batteryVoltage))V", color: .blue)
                                            LogEntry(level: "DEBUG", message: "CPU usage: \(cpuPercent)%", color: .blue)
                                            LogEntry(level: "INFO", message: "Altitude: \(String(format: "%.1f", altitude)) KM ASL", color: .cyan)
                                            LogEntry(level: "INFO", message: "Link status: \(linkStatus)", color: linkStatus == "Nominal" ? .green : linkStatus == "Degraded" ? .yellow : .red)
                                        }
                                        .frame(maxWidth: .infinity, alignment: .leading)
                                        .padding(10)
                                    }
                                }
                                .frame(height: 150)
                            }
                            .frame(maxWidth: .infinity, alignment: .leading)
                        }
                        .padding(.horizontal, 30)
                        .padding(.top, 20)
                        .padding(.bottom, 30)
                    }
                    .frame(maxWidth: .infinity)
                    .padding(.bottom, 30)
                }
                .frame(maxWidth: .infinity)
                
                // Floating Settings Button
                VStack {
                    HStack {
                        Spacer()
                        Button(action: {
                            showSettings = true
                        }) {
                            Image(systemName: "gearshape.fill")
                                .font(.system(size: 18, weight: .semibold))
                                .foregroundColor(.white)
                                .frame(width: 44, height: 44)
                                .background {
                                    ZStack {
                                        Circle()
                                            .fill(.ultraThinMaterial)
                                        Circle()
                                            .stroke(
                                                LinearGradient(
                                                    colors: [
                                                        Color.white.opacity(0.4),
                                                        Color.white.opacity(0.1),
                                                    ],
                                                    startPoint: .topLeading,
                                                    endPoint: .bottomTrailing
                                                ),
                                                lineWidth: 1
                                            )
                                    }
                                    .shadow(color: .black.opacity(0.3), radius: 10, x: 0, y: 5)
                                }
                        }
                        .buttonStyle(.plain)
                        .padding(.top, 20)
                        .padding(.trailing, 30)
                    }
                    Spacer()
                }
            }
            .frame(maxWidth: .infinity)
        }
        .frame(maxWidth: .infinity)
        .sheet(isPresented: $showSettings) {
            SettingsView()
        }
        .onAppear {       
            // Start timer for 1Hz updates
            updateTimer = Timer.scheduledTimer(withTimeInterval: 1.0, repeats: true) { _ in
                updateTelemetry()
            }
        }
        .onDisappear {
            // Stop timer when view disappears
            updateTimer?.invalidate()
            updateTimer = nil
        }
    }
}

// Glass morphism card component
struct GlassCard<Content: View>: View {
    let content: Content

    init(@ViewBuilder content: () -> Content) {
        self.content = content()
    }

    var body: some View {
        content
            .padding(20)
            .background {
                ZStack {
                    // Gradient background layer
                    // RoundedRectangle(cornerRadius: 20)
                    //     .fill(
                    //         LinearGradient(
                    //             colors: [
                    //                 Color.white.opacity(0.25),
                    //                 Color.white.opacity(0.05),
                    //             ],
                    //             startPoint: .topLeading,
                    //             endPoint: .bottomTrailing
                    //         )
                    //     )
                    
                    // Glassmorphism material layer
                    RoundedRectangle(cornerRadius: 20)
                        .fill(.ultraThinMaterial)
                    
                    // Border overlay
                    RoundedRectangle(cornerRadius: 20)
                        .stroke(
                            LinearGradient(
                                colors: [
                                    Color.white.opacity(0.4),
                                    Color.white.opacity(0.1),
                                ],
                                startPoint: .topLeading,
                                endPoint: .bottomTrailing
                            ),
                            lineWidth: 1
                        )
                }
                .shadow(color: .black.opacity(0.3), radius: 20, x: 0, y: 10)
            }
    }
}

// Helper view that shows both label and value in a row
struct DataRow: View {
    let label: String
    let value: String

    var body: some View {
        HStack {
            Text(label)
                .font(.caption)
                .foregroundColor(.white.opacity(0.7))
            Spacer()
            Text(value)
                .font(.system(size: 14, weight: .semibold))
                .foregroundColor(.white)
        }
    }
}

// Helper view for log entries
struct LogEntry: View {
    let level: String
    let message: String
    let color: Color
    
    var body: some View {
        HStack(spacing: 6) {
            Text("[\(level)]")
                .font(.system(.caption, design: .monospaced))
                .foregroundColor(color.opacity(0.9))
                .frame(width: 55, alignment: .leading)
            Text(message)
                .font(.system(.caption, design: .monospaced))
                .foregroundColor(.white.opacity(0.9))
        }
    }
}

// Helper view for metric boxes in 2x2 grid
struct MetricBox: View {
    let label: String
    let value: String
    let icon: String?
    let iconColor: Color?
    
    init(label: String, value: String, icon: String? = nil, iconColor: Color? = nil) {
        self.label = label
        self.value = value
        self.icon = icon
        self.iconColor = iconColor
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack(spacing: 6) {
                if let icon = icon, let iconColor = iconColor {
                    Image(systemName: icon)
                        .foregroundColor(iconColor)
                        .font(.system(size: 12))
                }
                Text(label)
                    .font(.caption2)
                    .foregroundColor(.white.opacity(0.7))
            }
            Text(value)
                .font(.system(size: 14, weight: .semibold))
                .foregroundColor(.white)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(12)
        .background(
            RoundedRectangle(cornerRadius: 8)
                .fill(Color.white.opacity(0.1))
                .overlay(
                    RoundedRectangle(cornerRadius: 8)
                        .stroke(Color.white.opacity(0.2), lineWidth: 1)
                )
        )
    }
}

// Spectrum Analyzer View using Swift Charts
struct SpectrumView: View {
    // Frequency range: 2.3 - 2.4 GHz
    private let minFrequency: Double = 2.3
    private let maxFrequency: Double = 2.4

    // Generate dummy spectrum data
    private var spectrumData: [SpectrumDataPoint] {
        var data: [SpectrumDataPoint] = []
        let numPoints = 500
        let noiseFloor = -110.0

        for i in 0..<numPoints {
            let frequency =
                minFrequency + (Double(i) / Double(numPoints - 1)) * (maxFrequency - minFrequency)

            // Base noise with variation
            var power = noiseFloor + Double.random(in: -5...5)

            // Peak around 2.35 GHz (main signal)
            let peak1Freq = 2.35
            let peak1Power = -65.0
            let distance1 = abs(frequency - peak1Freq)
            if distance1 < 0.01 {
                power = max(power, peak1Power - (distance1 * 1000))
            }

            // Smaller peak around 2.37 GHz
            let peak2Freq = 2.37
            let peak2Power = -75.0
            let distance2 = abs(frequency - peak2Freq)
            if distance2 < 0.008 {
                power = max(power, peak2Power - (distance2 * 1200))
            }

            // Another peak around 2.32 GHz
            let peak3Freq = 2.32
            let peak3Power = -80.0
            let distance3 = abs(frequency - peak3Freq)
            if distance3 < 0.006 {
                power = max(power, peak3Power - (distance3 * 1500))
            }

            data.append(SpectrumDataPoint(frequency: frequency, power: power))
        }

        return data
    }

    var body: some View {
        ZStack {
            // Dark background
            RoundedRectangle(cornerRadius: 12)
                .fill(Color.black.opacity(0.3))

            Chart(spectrumData) { point in
                // Trace line
                LineMark(
                    x: .value("Frequency", point.frequency),
                    y: .value("Power", point.power)
                )
                .foregroundStyle(Color.cyan)
                .lineStyle(StrokeStyle(lineWidth: 2.5))
            }
            .chartXScale(domain: minFrequency...maxFrequency)
            .chartYScale(domain: -120...(-40))
            .chartXAxis {
                AxisMarks(values: .stride(by: 0.02)) { value in
                    AxisGridLine()
                        .foregroundStyle(Color.white.opacity(0.15))
                    AxisValueLabel {
                        if let freq = value.as(Double.self) {
                            Text(String(format: "%.2f", freq))
                                .font(.system(size: 9, design: .monospaced))
                                .foregroundStyle(Color.white.opacity(0.6))
                        }
                    }
                }
            }
            .chartYAxis {
                AxisMarks(values: .stride(by: 20)) { value in
                    AxisGridLine()
                        .foregroundStyle(Color.white.opacity(0.15))
                    AxisValueLabel {
                        if let dbm = value.as(Double.self) {
                            Text("\(Int(dbm))")
                                .font(.system(size: 9, design: .monospaced))
                                .foregroundStyle(Color.white.opacity(0.6))
                        }
                    }
                }
            }
            .chartXAxisLabel {
                Text("Frequency (GHz)")
                    .foregroundStyle(Color.white.opacity(0.6))
                    .font(.system(size: 10, weight: .semibold))
            }
            .chartYAxisLabel {
                Text("dBm")
                    .foregroundStyle(Color.white.opacity(0.6))
                    .font(.system(size: 10, weight: .semibold))
            }
            .chartPlotStyle { plotArea in
                plotArea
                    .background(Color.clear)
            }
            .padding(.horizontal, 50)
            .padding(.vertical, 30)
        }
    }
}

// Vertical Progress Bar
struct VerticalProgressBar: View {
    let value: Double
    let maxValue: Double
    let color: Color
    let width: CGFloat
    let height: CGFloat
    let showPercentage: Bool
    
    init(
        value: Double,
        maxValue: Double = 10.0,
        color: Color = .green,
        width: CGFloat = 20,
        height: CGFloat = 50,
        showPercentage: Bool = true
    ) {
        self.value = value
        self.maxValue = maxValue
        self.color = color
        self.width = width
        self.height = height
        self.showPercentage = showPercentage
    }
    
    var body: some View {
        VStack(spacing: 4) {
            GeometryReader { geometry in
                ZStack(alignment: .bottom) {
                    // Background
                    RoundedRectangle(cornerRadius: 4)
                        .fill(Color.white.opacity(0.2))
                        .frame(width: width)
                    
                    // Filled portion
                    RoundedRectangle(cornerRadius: 4)
                        .fill(color)
                        .frame(
                            width: width,
                            height: geometry.size.height * min(value / maxValue, 1.0)
                        )
                }
            }
            .frame(width: width, height: height)
            
            if showPercentage {
                Text("\(Int((value / maxValue) * 100))%")
                    .font(.caption2)
                    .foregroundColor(.white.opacity(0.6))
            }
        }
    }
}

// Helper Spectrum Data Point
struct SpectrumDataPoint: Identifiable {
    let id = UUID()
    let frequency: Double  // GHz
    let power: Double  // dBm
}

// Reusable Card Title Component
struct CardTitle: View {
    let systemName: String
    let text: String
    
    var body: some View {
        HStack(spacing: 8) {
            Image(systemName: systemName)
                .foregroundColor(.white.opacity(0.9))
                .font(.system(size: 16))
            Text(text)
                .font(.system(size: 18, weight: .bold))
                .foregroundColor(.white.opacity(0.9))
        }
    }
}

struct StarfieldView: View {
    // Configuration
    let starCount = 500
    let globalSpeedMultiplier: Double = 0.25 // Adjust overall speed of the universe
    
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
                    // 1. Move the star
                    // We multiply by globalSpeedMultiplier to tune the whole system
                    let xPos = (star.x + (star.velocityX * timeInterval * globalSpeedMultiplier)).truncatingRemainder(dividingBy: 1.0)
                    let yPos = (star.y + (star.velocityY * timeInterval * globalSpeedMultiplier)).truncatingRemainder(dividingBy: 1.0)
                    
                    // Wrap logic (handle negative movement)
                    let finalX = xPos < 0 ? 1 + xPos : xPos
                    let finalY = yPos < 0 ? 1 + yPos : yPos
                    
                    // 2. Draw the star
                    let rect = CGRect(
                        x: finalX * size.width,
                        y: finalY * size.height,
                        width: star.size,
                        height: star.size
                    )
                    
                    // Twinkle effect:
                    // Faster moving stars (closer) twinkle more rapidly
                    let twinkleSpeed = star.size * 2.0 
                    let twinkle = abs(sin(timeInterval * twinkleSpeed)) * 0.4 + 0.6
                    
                    context.opacity = star.opacity * twinkle
                    context.fill(Path(ellipseIn: rect), with: .color(.white))
                }
            }
        }
        .background(Color.black)
        .onAppear {
            createStars()
        }
    }
    
    func createStars() {
        stars.removeAll()
        for _ in 0..<starCount {
            
            // --- PARALLAX LOGIC ---
            
            // 1. Generate a random "Depth" (Z-axis)
            // 0.1 = Far away, 1.0 = Very close
            let depth = Double.random(in: 0.1...1.0)
            
            // 2. Link Size to Depth
            // Distant stars are 1pt, Close stars are up to 4pt
            let calculatedSize = 1.0 + (depth * 3.0)
            
            // 3. Link Speed to Depth
            // Distant stars move slowly, Close stars move quickly
            // We allow random directions (-1 to 1), but scale the magnitude by depth
            let directionX = Double.random(in: -0.5...0.5)
            let directionY = Double.random(in: -0.5...0.5)
            
            let calculatedVelX = directionX * depth
            let calculatedVelY = directionY * depth
            
            // 4. Link Opacity to Depth (optional)
            // Distant stars are slightly dimmer
            let calculatedOpacity = 0.3 + (depth * 0.7)
            
            let newStar = Star(
                x: Double.random(in: 0...1),
                y: Double.random(in: 0...1),
                size: calculatedSize,
                opacity: calculatedOpacity,
                velocityX: calculatedVelX,
                velocityY: calculatedVelY
            )
            stars.append(newStar)
        }
    }
}

// Helper struct for Map annotation
struct DummyBalloonLocation: Identifiable {
    let id = UUID()
    let coordinate = CLLocationCoordinate2D(latitude: 35.165565, longitude: -80.887293)
}

#Preview {
    ContentView()
        .frame(width: 2000, height: 1400)
}
