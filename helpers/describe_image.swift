#!/usr/bin/env swift
// describe_image.swift — On-device image analysis via Apple Vision framework.
// Usage: ./describe_image /path/to/image.heic
// Output: JSON {"description": "...", "ocr_text": "...", "labels": [...]}

import Foundation
import Vision
import CoreImage

guard CommandLine.arguments.count >= 2 else {
    let error: [String: Any] = ["error": "Usage: describe_image <image_file_path>"]
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

// Load image via CIImage (supports HEIC, JPEG, PNG, etc.)
guard let ciImage = CIImage(contentsOf: url) else {
    let error: [String: Any] = ["error": "Could not load image: \(filePath)"]
    let data = try! JSONSerialization.data(withJSONObject: error)
    FileHandle.standardError.write(data)
    exit(1)
}

let handler = VNImageRequestHandler(ciImage: ciImage, options: [:])
var outputJSON: [String: Any] = [:]
var ocrTexts: [String] = []
var labels: [String] = []

// --- OCR: Recognize text in image ---
let textRequest = VNRecognizeTextRequest { request, error in
    if let error = error {
        outputJSON["ocr_error"] = error.localizedDescription
        return
    }
    guard let observations = request.results as? [VNRecognizedTextObservation] else { return }
    for obs in observations {
        if let candidate = obs.topCandidates(1).first, candidate.confidence > 0.3 {
            ocrTexts.append(candidate.string)
        }
    }
}
textRequest.recognitionLevel = .accurate
textRequest.usesLanguageCorrection = true

// --- Classification: Scene labels ---
let classifyRequest = VNClassifyImageRequest { request, error in
    if let error = error {
        outputJSON["classify_error"] = error.localizedDescription
        return
    }
    guard let observations = request.results as? [VNClassificationObservation] else { return }
    for obs in observations {
        if obs.confidence > 0.3 {
            labels.append(obs.identifier)
        }
    }
    // Keep top 5 labels
    labels = Array(labels.prefix(5))
}

// Execute requests
var requests: [VNRequest] = [textRequest, classifyRequest]

do {
    try handler.perform(requests)
} catch {
    outputJSON["error"] = "Vision processing failed: \(error.localizedDescription)"
}

// Build description from available signals
var descParts: [String] = []
if !labels.isEmpty {
    descParts.append(labels.joined(separator: ", "))
}
let description = descParts.isEmpty ? "image" : descParts.joined(separator: "; ")

outputJSON["description"] = description
outputJSON["ocr_text"] = ocrTexts.joined(separator: " ")
outputJSON["labels"] = labels

let jsonData = try! JSONSerialization.data(withJSONObject: outputJSON, options: [.sortedKeys])
FileHandle.standardOutput.write(jsonData)
FileHandle.standardOutput.write("\n".data(using: .utf8)!)
