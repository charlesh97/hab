//
//  SettingsView.swift
//  Balloon Dashboard
//
//  Created by Charles Hood on 11/23/25.
//

import SwiftUI

struct SettingsView: View {
    @Environment(\.dismiss) private var dismiss
    
    // Placeholder settings state
    @State private var refreshRate: Double = 1.0
    @State private var enableNotifications: Bool = true
    @State private var showDebugConsole: Bool = true
    @State private var theme: String = "Dark"
    
    var body: some View {
        NavigationStack {
            ZStack {
                // Background
                Color.black
                    .ignoresSafeArea()
                
                ScrollView {
                    VStack(spacing: 20) {
                        // Settings Title
                        HStack {
                            Text("Settings")
                                .font(.system(size: 28, weight: .bold))
                                .foregroundColor(.white)
                            Spacer()
                        }
                        .padding(.horizontal, 30)
                        .padding(.top, 20)
                        
                        // General Settings Section
                        GlassCard {
                            VStack(alignment: .leading, spacing: 16) {
                                CardTitle(systemName: "gearshape.fill", text: "General")
                                
                                VStack(alignment: .leading, spacing: 16) {
                                    // Refresh Rate
                                    VStack(alignment: .leading, spacing: 8) {
                                        HStack {
                                            Text("Data Refresh Rate")
                                                .font(.system(size: 14, weight: .semibold))
                                                .foregroundColor(.white)
                                            Spacer()
                                            Text("\(String(format: "%.1f", refreshRate)) Hz")
                                                .font(.system(size: 14, weight: .semibold))
                                                .foregroundColor(.white.opacity(0.7))
                                        }
                                        Slider(value: $refreshRate, in: 0.5...5.0, step: 0.1)
                                            .tint(.blue)
                                    }
                                    
                                    Divider()
                                        .background(Color.white.opacity(0.3))
                                    
                                    // Enable Notifications
                                    HStack {
                                        Text("Enable Notifications")
                                            .font(.system(size: 14, weight: .semibold))
                                            .foregroundColor(.white)
                                        Spacer()
                                        Toggle("", isOn: $enableNotifications)
                                            .toggleStyle(.switch)
                                    }
                                    
                                    Divider()
                                        .background(Color.white.opacity(0.3))
                                    
                                    // Show Debug Console
                                    HStack {
                                        Text("Show Debug Console")
                                            .font(.system(size: 14, weight: .semibold))
                                            .foregroundColor(.white)
                                        Spacer()
                                        Toggle("", isOn: $showDebugConsole)
                                            .toggleStyle(.switch)
                                    }
                                }
                            }
                            .frame(maxWidth: .infinity, alignment: .leading)
                        }
                        .padding(.horizontal, 30)
                        
                        // Display Settings Section
                        GlassCard {
                            VStack(alignment: .leading, spacing: 16) {
                                CardTitle(systemName: "display", text: "Display")
                                
                                VStack(alignment: .leading, spacing: 16) {
                                    // Theme Selection
                                    VStack(alignment: .leading, spacing: 8) {
                                        Text("Theme")
                                            .font(.system(size: 14, weight: .semibold))
                                            .foregroundColor(.white)
                                        
                                        Picker("Theme", selection: $theme) {
                                            Text("Dark").tag("Dark")
                                            Text("Light").tag("Light")
                                            Text("Auto").tag("Auto")
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
                                    Text("Balloon Dashboard")
                                        .font(.system(size: 16, weight: .semibold))
                                        .foregroundColor(.white)
                                    
                                    Text("Version 1.0.0")
                                        .font(.system(size: 14))
                                        .foregroundColor(.white.opacity(0.7))
                                    
                                    Text("Real-time telemetry dashboard for high-altitude balloon missions.")
                                        .font(.system(size: 14))
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
            .frame(minWidth: 600, minHeight: 500)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Done") {
                        dismiss()
                    }
                    .foregroundColor(.white)
                }
            }
        }
    }
}

#Preview {
    SettingsView()
        .frame(width: 800, height: 600)
}

