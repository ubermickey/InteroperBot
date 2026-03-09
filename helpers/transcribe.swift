#!/usr/bin/env swift
// transcribe.swift — On-device audio transcription via Apple Speech framework.
// Usage: ./transcribe /path/to/audio.m4a
// Output: JSON {"transcript": "...", "confidence": 0.85}

import Foundation
import Speech

guard CommandLine.arguments.count >= 2 else {
    let error: [String: Any] = ["error": "Usage: transcribe <audio_file_path>"]
    let data = try! JSONSerialization.data(withJSONObject: error)
    FileHandle.standardError.write(data)
    exit(1)
}

let filePath = CommandLine.arguments[1]
let url = URL(fileURLWithPath: filePath)

guard FileManager.default.fileExists(atPath: filePath) else {
    let error: [String: Any] = ["error": "File not found: \(filePath)"]
    let data = try! JSONSerialization.data(withJSONObject: error)
    FileHandle.standardError.write(data)
    exit(1)
}

let semaphore = DispatchSemaphore(value: 0)

SFSpeechRecognizer.requestAuthorization { status in
    guard status == .authorized else {
        let error: [String: Any] = ["error": "Speech recognition not authorized (status: \(status.rawValue))"]
        let data = try! JSONSerialization.data(withJSONObject: error)
        FileHandle.standardError.write(data)
        exit(2)
    }
    semaphore.signal()
}
semaphore.wait()

guard let recognizer = SFSpeechRecognizer(locale: Locale(identifier: "en-US")) else {
    let error: [String: Any] = ["error": "Could not create speech recognizer"]
    let data = try! JSONSerialization.data(withJSONObject: error)
    FileHandle.standardError.write(data)
    exit(1)
}

let request = SFSpeechURLRecognitionRequest(url: url)
if recognizer.supportsOnDeviceRecognition {
    request.requiresOnDeviceRecognition = true
}

let taskSemaphore = DispatchSemaphore(value: 0)
var outputJSON: [String: Any] = [:]

recognizer.recognitionTask(with: request) { result, error in
    if let error = error {
        outputJSON = ["error": error.localizedDescription, "transcript": ""]
        taskSemaphore.signal()
        return
    }
    guard let result = result else { return }
    if result.isFinal {
        let transcript = result.bestTranscription.formattedString
        // Average confidence across segments
        let segments = result.bestTranscription.segments
        let avgConfidence: Float = segments.isEmpty ? 0 :
            segments.reduce(0) { $0 + $1.confidence } / Float(segments.count)
        outputJSON = [
            "transcript": transcript,
            "confidence": round(Double(avgConfidence) * 100) / 100
        ]
        taskSemaphore.signal()
    }
}

// Wait with timeout (30 seconds)
let timeout = DispatchTime.now() + .seconds(30)
if taskSemaphore.wait(timeout: timeout) == .timedOut {
    outputJSON = ["error": "Transcription timed out after 30 seconds", "transcript": ""]
}

let jsonData = try! JSONSerialization.data(withJSONObject: outputJSON, options: [.sortedKeys])
FileHandle.standardOutput.write(jsonData)
FileHandle.standardOutput.write("\n".data(using: .utf8)!)
