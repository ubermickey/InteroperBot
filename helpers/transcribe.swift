#!/usr/bin/env swift
// transcribe.swift — On-device audio transcription via Apple Speech framework.
// Usage: ./transcribe /path/to/audio.m4a [timeout_seconds]
// Output: JSON {"transcript": "...", "confidence": 0.85}

import Foundation
import Speech

guard CommandLine.arguments.count >= 2 else {
    let error: [String: Any] = ["error": "Usage: transcribe <audio_file_path> [timeout_seconds]"]
    let data = try! JSONSerialization.data(withJSONObject: error)
    FileHandle.standardError.write(data)
    exit(1)
}

let filePath = CommandLine.arguments[1]
let timeoutSeconds = CommandLine.arguments.count >= 3 ? (Int(CommandLine.arguments[2]) ?? 120) : 120
let url = URL(fileURLWithPath: filePath)

guard FileManager.default.fileExists(atPath: filePath) else {
    let error: [String: Any] = ["error": "File not found: \(filePath)"]
    let data = try! JSONSerialization.data(withJSONObject: error)
    FileHandle.standardError.write(data)
    exit(1)
}

func writeResult(_ dict: [String: Any]) {
    let jsonData = try! JSONSerialization.data(withJSONObject: dict, options: [.sortedKeys])
    FileHandle.standardOutput.write(jsonData)
    FileHandle.standardOutput.write("\n".data(using: .utf8)!)
}

// Check authorization status without blocking
let authStatus = SFSpeechRecognizer.authorizationStatus()
if authStatus == .notDetermined {
    // Request on the main queue so the RunLoop can process it
    var granted = false
    let group = DispatchGroup()
    group.enter()
    DispatchQueue.main.async {
        SFSpeechRecognizer.requestAuthorization { status in
            granted = (status == .authorized)
            group.leave()
        }
    }
    // Pump the RunLoop while waiting
    while group.wait(timeout: .now()) == .timedOut {
        RunLoop.current.run(mode: .default, before: Date(timeIntervalSinceNow: 0.1))
    }
    if !granted {
        writeResult(["error": "Speech recognition not authorized", "transcript": ""])
        exit(2)
    }
} else if authStatus != .authorized {
    writeResult(["error": "Speech recognition not authorized (status: \(authStatus.rawValue))", "transcript": ""])
    exit(2)
}

guard let recognizer = SFSpeechRecognizer(locale: Locale(identifier: "en-US")) else {
    writeResult(["error": "Could not create speech recognizer", "transcript": ""])
    exit(1)
}

let request = SFSpeechURLRecognitionRequest(url: url)
if recognizer.supportsOnDeviceRecognition {
    request.requiresOnDeviceRecognition = true
}

var done = false
var outputJSON: [String: Any] = [:]

recognizer.recognitionTask(with: request) { result, error in
    if let error = error {
        outputJSON = ["error": error.localizedDescription, "transcript": ""]
        done = true
        return
    }
    guard let result = result else { return }
    if result.isFinal {
        let transcript = result.bestTranscription.formattedString
        let segments = result.bestTranscription.segments
        let avgConfidence: Float = segments.isEmpty ? 0 :
            segments.reduce(0) { $0 + $1.confidence } / Float(segments.count)
        outputJSON = [
            "transcript": transcript,
            "confidence": round(Double(avgConfidence) * 100) / 100
        ]
        done = true
    }
}

// Pump the RunLoop until done or timeout
let deadline = Date(timeIntervalSinceNow: Double(timeoutSeconds))
while !done && Date() < deadline {
    RunLoop.current.run(mode: .default, before: Date(timeIntervalSinceNow: 0.25))
}

if !done {
    outputJSON = ["error": "Transcription timed out after \(timeoutSeconds) seconds", "transcript": ""]
}

writeResult(outputJSON)
