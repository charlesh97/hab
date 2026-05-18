//
//  Balloon_DashboardApp.swift
//  Balloon Dashboard
//
//  Created by Charles Hood on 11/23/25.
//

import SwiftUI

@main
struct Balloon_DashboardApp: App {
    var body: some Scene {
        WindowGroup {
            ContentView()
        }
        .defaultSize(width: 1600, height: 1000)
        .windowResizability(.contentMinSize)
        .commands {
            CommandGroup(replacing: .newItem) { }
        }
    }
}
