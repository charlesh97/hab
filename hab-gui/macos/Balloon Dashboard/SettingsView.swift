//
//  SettingsView.swift
//  Balloon Dashboard
//
//  Created by Charles Hood on 11/23/25.
//

import SwiftUI

struct SettingsView: View {
    @Environment(\.dismiss) private var dismiss
    @ObservedObject var wsClient: WebSocketClient
    
    // Connection settings
    @State private var serverURL: String = "ws://localhost:8765"
    @State private var defaultFrequency: Double = 915.0       // MHz
    @State private var defaultSymbolRate: Double = 1.0        // Msps
    
    // Appearance
    @State private var theme: String = "Dark"
    
    var body: some View {
        NavigationStack {
            ZStack {
                Color.black.ignoresSafeArea()
                
                ScrollView {
                    VStack(spacing: 20) {
                        // Header
                        HStack {
                            Text("Settings")
                                .font(.system(size: 28, weight: .bold))
                                .foregroundColor(.white)
                            Spacer()
                        }
                        .padding(.horizontal, 30)
                        .padding(.top, 20)
                        
                        // Connection Section
                        GlassCard {
                            VStack(alignment: .leading, spacing: 16) {
                                CardTitle(systemName: "antenna.radiowaves.left.and.right", text: "Connection")
                                
                                VStack(alignment: .leading, spacing: 14) {
                                    // Server URL
                                    VStack(alignment: .leading, spacing: 6) {
                                        Text("WebSocket Server URL")
                                            .font(.system(size: 13, weight: .semibold))
                                            .foregroundColor(.white)
                                        TextField("ws://localhost:8765", text: $serverURL)
                                            .textFieldStyle(.plain)
                                            .font(.system(size: 13, design: .monospaced))
                                            .foregroundColor(.white)
                                            .padding(.horizontal, 12)
                                            .padding(.vertical, 8)
                                            .background(Color.white.opacity(0.1))
                                            .cornerRadius(8)
                                            .overlay(
                                                RoundedRectangle(cornerRadius: 8)
                                                    .stroke(Color.white.opacity(0.15), lineWidth: 1)
                                            )
                                    }
                                    
                                    Divider().background(Color.white.opacity(0.2))
                                    
                                    // Default Frequency
                                    VStack(alignment: .leading, spacing: 6) {
                                        HStack {
                                            Text("Default Frequency")
                                                .font(.system(size: 13, weight: .semibold))
                                                .foregroundColor(.white)
                                            Spacer()
                                            Text("\(String(format: "%.1f", defaultFrequency)) MHz")
                                                .font(.system(size: 13, weight: .semibold, design: .monospaced))
                                                .foregroundColor(.white.opacity(0.7))
                                        }
                                        Slider(value: $defaultFrequency, in: 100...6000, step: 0.1)
                                            .tint(.blue)
                                    }
                                    
                                    // Default Symbol Rate
                                    VStack(alignment: .leading, spacing: 6) {
                                        HStack {
                                            Text("Default Symbol Rate")
                                                .font(.system(size: 13, weight: .semibold))
                                                .foregroundColor(.white)
                                            Spacer()
                                            Text("\(String(format: "%.2f", defaultSymbolRate)) Msps")
                                                .font(.system(size: 13, weight: .semibold, design: .monospaced))
                                                .foregroundColor(.white.opacity(0.7))
                                        }
                                        Slider(value: $defaultSymbolRate, in: 0.01...10.0, step: 0.01)
                                            .tint(.blue)
                                    }
                                }
                            }
                            .frame(maxWidth: .infinity, alignment: .leading)
                        }
                        .padding(.horizontal, 30)
                        
                        // Display Section
                        GlassCard {
                            VStack(alignment: .leading, spacing: 16) {
                                CardTitle(systemName: "display", text: "Display")
                                
                                VStack(alignment: .leading, spacing: 14) {
                                    // Theme
                                    VStack(alignment: .leading, spacing: 6) {
                                        Text("Theme")
                                            .font(.system(size: 13, weight: .semibold))
                                            .foregroundColor(.white)
                                        Picker("Theme", selection: $theme) {
                                            Text("Dark").tag("Dark")
                                            Text("Light").tag("Light")
                                        }
                                        .pickerStyle(.segmented)
                                    }
                                }
                            }
                            .frame(maxWidth: .infinity, alignment: .leading)
                        }
                        .padding(.horizontal, 30)
                        
                        // About Section
                        GlassCard {
                            VStack(alignment: .leading, spacing: 16) {
                                CardTitle(systemName: "info.circle.fill", text: "About")
                                
                                VStack(alignment: .leading, spacing: 12) {
                                    Text("HAB Ground Station")
                                        .font(.system(size: 16, weight: .semibold))
                                        .foregroundColor(.white)
                                    Text("Version 1.0.0")
                                        .font(.system(size: 13))
                                        .foregroundColor(.white.opacity(0.7))
                                    Text("Real-time spectrum waterfall and telemetry dashboard for high-altitude balloon missions. Connects to the HabEngine Python backend via WebSocket.")
                                        .font(.system(size: 13))
                                        .foregroundColor(.white.opacity(0.7))
                                        .fixedSize(horizontal: false, vertical: true)
                                }
                            }
                            .frame(maxWidth: .infinity, alignment: .leading)
                        }
                        .padding(.horizontal, 30)
                        .padding(.bottom, 30)
                    }
                }
            }
            .frame(minWidth: 500, minHeight: 450)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Done") {
                        // Persist settings
                        wsClient.setServerURL(serverURL)
                        dismiss()
                    }
                    .foregroundColor(.white)
                }
            }
            .onAppear {
                serverURL = wsClient.getServerURL()
            }
        }
    }
}

// MARK: - Reusable Components (local copies to avoid circular references)

struct GlassCard<Content: View>: View {
    let content: Content
    
    init(@ViewBuilder content: () -> Content) {
        self.content = content()
    }
    
    var body: some View {
        content
            .padding(20)
            .background {
                RoundedRectangle(cornerRadius: 20)
                    .fill(.ultraThinMaterial)
                    .overlay(
                        RoundedRectangle(cornerRadius: 20)
                            .stroke(
                                LinearGradient(
                                    colors: [Color.white.opacity(0.4), Color.white.opacity(0.1)],
                                    startPoint: .topLeading,
                                    endPoint: .bottomTrailing
                                ),
                                lineWidth: 1
                            )
                    )
                    .shadow(color: .black.opacity(0.3), radius: 20, x: 0, y: 10)
            }
    }
}

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

#Preview {
    let client = WebSocketClient()
    return SettingsView(wsClient: client)
        .frame(width: 800, height: 600)
}
