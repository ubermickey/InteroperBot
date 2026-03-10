#!/usr/bin/env swift
// transcribe.swift — On-device audio transcription via Apple Speech framework.
// Usage: ./transcribe /path/to/audio.m4a [timeout_seconds]
// Output: JSON {"transcript": "...", "confidence": 0.85, "segments": [...]}

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

// Transcription function — builds result JSON from a final transcription result
func buildResult(_ result: SFSpeechRecognitionResult) -> [String: Any] {
    let transcript = result.bestTranscription.formattedString
    let segments = result.bestTranscription.segments
    let avgConfidence: Float = segments.isEmpty ? 0 :
        segments.reduce(0) { $0 + $1.confidence } / Float(segments.count)

    // Group word-level segments into sentence-like chunks
    // Split on: pauses > 0.5s, sentence-ending punctuation (. ? !)
    var chunks: [[String: Any]] = []
    var currentText = ""
    var chunkStart: Double = 0
    var lastEnd: Double = 0

    for (i, seg) in segments.enumerated() {
        let segStart = seg.timestamp
        let segEnd = seg.timestamp + seg.duration

        if i == 0 {
            chunkStart = segStart
            currentText = seg.substring
        } else {
            let gap = segStart - lastEnd
            let endsWithPunct = currentText.hasSuffix(".")
                || currentText.hasSuffix("?")
                || currentText.hasSuffix("!")

            if gap > 0.5 || endsWithPunct {
                // Flush current chunk
                chunks.append([
                    "text": currentText,
                    "start": round(chunkStart * 10) / 10,
                    "end": round(lastEnd * 10) / 10
                ])
                currentText = seg.substring
                chunkStart = segStart
            } else {
                currentText += " " + seg.substring
            }
        }
        lastEnd = segEnd
    }

    // Flush final chunk
    if !currentText.isEmpty {
        chunks.append([
            "text": currentText,
            "start": round(chunkStart * 10) / 10,
            "end": round(lastEnd * 10) / 10
        ])
    }

    // Word-level timing for subtitle animation
    var wordTimings: [[String: Any]] = []
    for seg in segments {
        wordTimings.append([
            "word": seg.substring,
            "start": round(seg.timestamp * 100) / 100,
            "end": round((seg.timestamp + seg.duration) * 100) / 100
        ])
    }

    return [
        "transcript": transcript,
        "confidence": round(Double(avgConfidence) * 100) / 100,
        "segments": chunks,
        "words": wordTimings
    ]
}

// Run recognition with a given on-device preference
func runRecognition(onDevice: Bool) -> [String: Any]? {
    let request = SFSpeechURLRecognitionRequest(url: url)
    request.requiresOnDeviceRecognition = onDevice

    var finished = false
    var result: [String: Any]? = nil

    recognizer.recognitionTask(with: request) { taskResult, error in
        if let error = error {
            result = ["error": error.localizedDescription, "transcript": ""]
            finished = true
            return
        }
        guard let taskResult = taskResult else { return }
        if taskResult.isFinal {
            result = buildResult(taskResult)
            finished = true
        }
    }

    let deadline = Date(timeIntervalSinceNow: Double(timeoutSeconds))
    while !finished && Date() < deadline {
        RunLoop.current.run(mode: .default, before: Date(timeIntervalSinceNow: 0.25))
    }

    if !finished { return nil }
    return result
}

// Strategy: try on-device first (fast, private), fall back to server-side
// if on-device returns empty or errors
var outputJSON: [String: Any] = [:]

if recognizer.supportsOnDeviceRecognition {
    if let result = runRecognition(onDevice: true) {
        let transcript = result["transcript"] as? String ?? ""
        if !transcript.isEmpty {
            outputJSON = result
        }
    }
}

// Fall back to server-side if on-device produced nothing
if outputJSON.isEmpty {
    if let result = runRecognition(onDevice: false) {
        outputJSON = result
    } else {
        outputJSON = ["error": "Transcription timed out after \(timeoutSeconds) seconds", "transcript": ""]
    }
}

writeResult(outputJSON)
