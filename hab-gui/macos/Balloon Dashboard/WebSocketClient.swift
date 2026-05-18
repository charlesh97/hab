//
//  WebSocketClient.swift
//  Balloon Dashboard
//
//  Created by Charles Hood on 11/23/25.
//

import Foundation
import Network
import Combine

/// WebSocket client using NWConnection from the Network framework (no external dependencies).
actor WebSocketActor {
    private var connection: NWConnection?
    private let queue = DispatchQueue(label: "com.hab.websocket", qos: .userInitiated)
    
    func connect(to url: URL) -> AsyncStream<WebSocketEvent> {
        return AsyncStream { continuation in
            var wsOptions: NWProtocolWebSocket.Options? = nil
            var tls: NWProtocolTLS.Options? = nil
            
            if url.scheme == "wss" {
                tls = NWProtocolTLS.Options()
            }
            
            wsOptions = NWProtocolWebSocket.Options()
            wsOptions?.autoReplyPing = true
            
            let parameters = NWParameters(tls: tls)
            if let wsOpts = wsOptions {
                parameters.defaultProtocolStack.applicationProtocols.insert(wsOpts, at: 0)
            }
            
            let endpoint = NWEndpoint.url(url)
            let conn = NWConnection(to: endpoint, using: parameters)
            self.connection = conn
            
            conn.stateUpdateHandler = { state in
                switch state {
                case .ready:
                    continuation.yield(.connected)
                    self.receiveLoop(continuation: continuation, connection: conn)
                case .failed(let error):
                    continuation.yield(.disconnected(error.localizedDescription))
                    continuation.finish()
                case .cancelled:
                    continuation.yield(.disconnected("Connection cancelled"))
                    continuation.finish()
                default:
                    break
                }
            }
            
            conn.start(queue: queue)
        }
    }
    
    private func receiveLoop(continuation: AsyncStream<WebSocketEvent>.Continuation, connection: NWConnection) {
        connection.receiveMessage { [weak self] data, context, isComplete, error in
            guard let self = self else { return }
            
            if let error = error {
                continuation.yield(.error(error.localizedDescription))
                return
            }
            
            if let data = data, !data.isEmpty {
                if let message = String(data: data, encoding: .utf8) {
                    continuation.yield(.message(message))
                }
            }
            
            if isComplete {
                continuation.yield(.disconnected("Stream ended"))
                continuation.finish()
            } else {
                // Continue receiving
                self.receiveLoop(continuation: continuation, connection: connection)
            }
        }
    }
    
    func disconnect() {
        connection?.cancel()
        connection = nil
    }
    
    func send(text: String) {
        guard let data = text.data(using: .utf8) else { return }
        connection?.send(content: data, completion: .contentProcessed { _ in })
    }
    
    deinit {
        connection?.cancel()
    }
}

enum WebSocketEvent {
    case connected
    case disconnected(String)
    case message(String)
    case error(String)
}

@MainActor
class WebSocketClient: ObservableObject {
    @Published var isConnected = false
    @Published var connectionError: String?
    @Published var spectrumData: SpectrumData?
    @Published var engineStatus: EngineStatus?
    @Published var waterfallBuffer = WaterfallBuffer()
    
    private var serverURL = "ws://localhost:8765"
    private var actor: WebSocketActor?
    private var eventTask: Task<Void, Never>?
    
    func setServerURL(_ url: String) {
        serverURL = url.trimmingCharacters(in: .whitespacesAndNewlines)
    }
    
    func getServerURL() -> String {
        serverURL
    }
    
    func connect() {
        disconnect()
        
        guard let url = URL(string: serverURL) else {
            connectionError = "Invalid URL: \(serverURL)"
            isConnected = false
            return
        }
        
        connectionError = nil
        let actor = WebSocketActor()
        self.actor = actor
        
        eventTask = Task { [weak self] in
            guard let self = self else { return }
            
            let stream = await actor.connect(to: url)
            for await event in stream {
                if !Task.isCancelled {
                    await self.handleEvent(event)
                }
            }
        }
    }
    
    func disconnect() {
        eventTask?.cancel()
        eventTask = nil
        
        Task {
            await actor?.disconnect()
            actor = nil
        }
        
        isConnected = false
        connectionError = nil
    }
    
    private func handleEvent(_ event: WebSocketEvent) {
        switch event {
        case .connected:
            isConnected = true
            connectionError = nil
        case .disconnected(let reason):
            isConnected = false
            connectionError = reason
        case .message(let text):
            handleMessage(text)
        case .error(let err):
            connectionError = err
        }
    }
    
    private func handleMessage(_ text: String) {
        guard let data = text.data(using: .utf8),
              let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
              let type = json["type"] as? String else {
            return
        }
        
        guard let rawData = json["data"] else { return }
        
        switch type {
        case "spectrum":
            if let dictData = rawData as? [String: Any],
               let jsonData = try? JSONSerialization.data(withJSONObject: dictData),
               let spectrum = try? JSONDecoder().decode(SpectrumData.self, from: jsonData) {
                spectrumData = spectrum
                waterfallBuffer.addSpectrum(spectrum)
            }
        case "status":
            if let dictData = rawData as? [String: Any],
               let jsonData = try? JSONSerialization.data(withJSONObject: dictData),
               let status = try? JSONDecoder().decode(EngineStatus.self, from: jsonData) {
                engineStatus = status
            }
        default:
            break
        }
    }
    
    // MARK: - Command Sending
    
    func sendCommand(_ command: String, data: [String: Any] = [:]) {
        var payload: [String: Any] = ["command": command]
        if !data.isEmpty {
            payload["data"] = data
        }
        
        guard let jsonData = try? JSONSerialization.data(withJSONObject: payload),
              let jsonString = String(data: jsonData, encoding: .utf8) else {
            return
        }
        
        Task { [weak self] in
            await self?.actor?.send(text: jsonString)
        }
    }
    
    func startPipeline(filePath: String) {
        sendCommand("start_pipeline", data: ["file_path": filePath])
    }
    
    func stopPipeline() {
        sendCommand("stop_pipeline")
    }
    
    func startTX() {
        sendCommand("start_tx")
    }
    
    func stopTX() {
        sendCommand("stop_tx")
    }
}
