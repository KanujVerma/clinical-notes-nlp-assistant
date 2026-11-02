import CoreGraphics
import CryptoKit
import Darwin
import Foundation
import ImageIO
import Vision

let campaignID = "ocr-c3-apple-vision-v1"
let candidateID = "V1_apple_vision_accurate_raw"
let schemaVersion = "ocr_c3_vision_result_v1"
let readingOrder = "vision_reading_order_v1"

enum ExitCode: Int32 {
    case ok = 0
    case usage = 2
    case visionFailed = 3
    case languageUnsupported = 4
    case revisionUnsupported = 5
    case imageDecodeFailed = 6
    case invalidConfig = 7
}

func fail(_ message: String, code: ExitCode) -> Never {
    FileHandle.standardError.write(Data((message + "\n").utf8))
    exit(code.rawValue)
}

func argument(_ name: String) -> String? {
    let args = CommandLine.arguments
    guard let index = args.firstIndex(of: name), index + 1 < args.count else { return nil }
    return args[index + 1]
}

func sha256Hex(_ data: Data) -> String {
    SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined()
}

func osBuild() -> String {
    var size = 0
    sysctlbyname("kern.osversion", nil, &size, nil, 0)
    var buffer = [CChar](repeating: 0, count: size)
    sysctlbyname("kern.osversion", &buffer, &size, nil, 0)
    return String(cString: buffer)
}

func machine() -> String {
    var system = utsname()
    uname(&system)
    return withUnsafePointer(to: &system.machine) {
        $0.withMemoryRebound(to: CChar.self, capacity: 1) { String(cString: $0) }
    }
}

func iso(_ date: Date) -> String {
    let formatter = ISO8601DateFormatter()
    formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
    return formatter.string(from: date)
}

func supportedLanguages(revision: Int) throws -> [String] {
    let request = VNRecognizeTextRequest()
    request.recognitionLevel = .accurate
    request.revision = revision
    return try request.supportedRecognitionLanguages()
}

func probe() -> Never {
    let revision = VNRecognizeTextRequest.currentRevision
    let supported = VNRecognizeTextRequest.supportedRevisions.map { Int($0) }
    let languages: [String]
    do {
        languages = try supportedLanguages(revision: revision).sorted()
    } catch {
        fail("language_probe_failed", code: .languageUnsupported)
    }
    let payload: [String: Any] = [
        "campaign_id": campaignID,
        "recognition_level": "accurate",
        "current_revision": revision,
        "supported_revisions": supported,
        "supported_languages": languages,
        "os_build": osBuild(),
        "arch": machine(),
        "model_weight_digest": NSNull(),
        "model_weight_digest_available": false,
    ]
    guard let data = try? JSONSerialization.data(withJSONObject: payload, options: [.sortedKeys]) else {
        fail("probe_encode_failed", code: .usage)
    }
    FileHandle.standardOutput.write(data)
    FileHandle.standardOutput.write(Data("\n".utf8))
    exit(ExitCode.ok.rawValue)
}

func loadConfig(_ path: String) -> [String: Any] {
    guard let data = FileManager.default.contents(atPath: path),
          let object = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else {
        fail("invalid_config", code: .invalidConfig)
    }
    return object
}

func requireMatch(_ config: [String: Any]) -> Int {
    guard config["campaign_id"] as? String == campaignID,
          config["candidate"] as? String == candidateID,
          config["recognition_level"] as? String == "accurate",
          config["uses_language_correction"] as? Bool == false,
          config["automatically_detects_language"] as? Bool == false,
          config["minimum_text_height"] as? Double == 0 || config["minimum_text_height"] as? Int == 0,
          config["recognition_languages"] as? [String] == ["en-US"],
          config["custom_words"] as? [String] == [] else {
        fail("config_does_not_match_v1", code: .invalidConfig)
    }
    guard let revision = config["revision"] as? Int else {
        fail("revision_missing", code: .invalidConfig)
    }
    if !VNRecognizeTextRequest.supportedRevisions.contains(revision) {
        fail("unsupported_revision", code: .revisionUnsupported)
    }
    return revision
}

func pixelBox(_ rect: CGRect, width: Int, height: Int) -> [String: Double] {
    let w = Double(width)
    let h = Double(height)
    return [
        "x": rect.origin.x * w,
        "y": (1.0 - rect.origin.y - rect.size.height) * h,
        "width": rect.size.width * w,
        "height": rect.size.height * h,
    ]
}

func geometryStatus(_ box: [String: Double], width: Int, height: Int) -> String {
    guard let x = box["x"], let y = box["y"], let w = box["width"], let h = box["height"] else {
        return "invalid"
    }
    let values = [x, y, w, h]
    if values.contains(where: { !$0.isFinite }) || w <= 0 || h <= 0 {
        return "invalid"
    }
    if x < -0.5 || y < -0.5 || x + w > Double(width) + 0.5 || y + h > Double(height) + 0.5 {
        return "invalid"
    }
    return "valid"
}

func verticalOverlap(_ left: [String: Double], _ right: [String: Double]) -> Double {
    let top = max(left["y"] ?? 0, right["y"] ?? 0)
    let bottom = min((left["y"] ?? 0) + (left["height"] ?? 0), (right["y"] ?? 0) + (right["height"] ?? 0))
    return bottom - top
}

func horizontalGap(_ left: [String: Double], _ right: [String: Double]) -> Double {
    let leftEnd = (left["x"] ?? 0) + (left["width"] ?? 0)
    let rightEnd = (right["x"] ?? 0) + (right["width"] ?? 0)
    if leftEnd <= (right["x"] ?? 0) { return (right["x"] ?? 0) - leftEnd }
    if rightEnd <= (left["x"] ?? 0) { return (left["x"] ?? 0) - rightEnd }
    return 0
}

func readingOrderUncertain(_ rows: [[String: Any]], width: Int) -> Bool {
    let boxes = rows.compactMap { row -> [String: Double]? in
        guard row["geometry_status"] as? String == "valid" else { return nil }
        return row["pixel_rectangle"] as? [String: Double]
    }
    for index in boxes.indices {
        for other in boxes.indices where other > index {
            let left = boxes[index]
            let right = boxes[other]
            let shorter = min(left["height"] ?? 0, right["height"] ?? 0)
            if verticalOverlap(left, right) >= 0.4 * shorter && horizontalGap(left, right) >= 0.15 * Double(width) {
                return true
            }
        }
    }
    return false
}

func assemble(_ rows: [[String: Any]]) -> String {
    let ordered = rows.sorted { left, right in
        let leftValid = (left["geometry_status"] as? String) == "valid"
        let rightValid = (right["geometry_status"] as? String) == "valid"
        if leftValid != rightValid { return leftValid && !rightValid }
        let leftBox = left["pixel_rectangle"] as? [String: Double] ?? [:]
        let rightBox = right["pixel_rectangle"] as? [String: Double] ?? [:]
        let leftY = leftBox["y"] ?? 0
        let rightY = rightBox["y"] ?? 0
        if leftY != rightY { return leftY < rightY }
        let leftX = leftBox["x"] ?? 0
        let rightX = rightBox["x"] ?? 0
        if leftX != rightX { return leftX < rightX }
        return (left["index"] as? Int ?? 0) < (right["index"] as? Int ?? 0)
    }
    let lines = ordered.compactMap { row -> String? in
        guard let text = row["top_candidate"] as? String, !text.isEmpty else { return nil }
        return text
    }
    return lines.joined(separator: "\n")
}

func writeAtomic(_ payload: [String: Any], to path: String) {
    guard let data = try? JSONSerialization.data(withJSONObject: payload, options: [.prettyPrinted, .sortedKeys]) else {
        fail("result_encode_failed", code: .usage)
    }
    let destination = URL(fileURLWithPath: path)
    let temporary = destination.appendingPathExtension("tmp")
    do {
        try data.write(to: temporary, options: .atomic)
        if FileManager.default.fileExists(atPath: path) {
            try FileManager.default.removeItem(at: destination)
        }
        try FileManager.default.moveItem(at: temporary, to: destination)
    } catch {
        fail("result_write_failed", code: .usage)
    }
}

func decodePreparedJPEG(_ path: String) -> (CGImage, Int, Int) {
    let url = URL(fileURLWithPath: path)
    guard let source = CGImageSourceCreateWithURL(url as CFURL, nil) else {
        fail("image_decode_failed", code: .imageDecodeFailed)
    }
    let properties = CGImageSourceCopyPropertiesAtIndex(source, 0, nil) as? [CFString: Any]
    if let orientation = properties?[kCGImagePropertyOrientation] as? Int, orientation != 1 {
        fail("unexpected_orientation", code: .imageDecodeFailed)
    }
    guard let image = CGImageSourceCreateImageAtIndex(source, 0, nil) else {
        fail("image_decode_failed", code: .imageDecodeFailed)
    }
    return (image, image.width, image.height)
}

if CommandLine.arguments.contains("--probe") {
    probe()
}

guard let imagePath = argument("--image"),
      let outputPath = argument("--output"),
      let requestID = argument("--request-id"),
      let configPath = argument("--config"),
      let sourceFingerprint = argument("--source-fingerprint"),
      let dataset = argument("--dataset"),
      let caseID = argument("--case-id"),
      let pageText = argument("--page-index"),
      let pageIndex = Int(pageText),
      let sourceSHA = argument("--source-sha256") else {
    fail("usage", code: .usage)
}

let started = Date()
let config = loadConfig(configPath)
let revision = requireMatch(config)
let languages: [String]
do {
    languages = try supportedLanguages(revision: revision)
} catch {
    fail("language_probe_failed", code: .languageUnsupported)
}
if !languages.contains("en-US") {
    fail("vision_language_unsupported", code: .languageUnsupported)
}

let fileData = FileManager.default.contents(atPath: imagePath) ?? Data()
if fileData.isEmpty {
    fail("image_decode_failed", code: .imageDecodeFailed)
}
let preparedSHA = sha256Hex(fileData)
let decoded = decodePreparedJPEG(imagePath)

let request = VNRecognizeTextRequest()
request.recognitionLevel = .accurate
request.usesLanguageCorrection = false
request.recognitionLanguages = ["en-US"]
request.automaticallyDetectsLanguage = false
request.customWords = []
request.minimumTextHeight = 0
request.revision = revision

let handler = VNImageRequestHandler(cgImage: decoded.0, options: [:])
do {
    try handler.perform([request])
} catch {
    let failed: [String: Any] = [
        "schema_version": schemaVersion,
        "campaign_id": campaignID,
        "request_id": requestID,
        "status": "vision_request_failed",
        "error_code": "vision_request_failed",
        "elapsed_seconds": Date().timeIntervalSince(started),
    ]
    writeAtomic(failed, to: outputPath)
    exit(ExitCode.visionFailed.rawValue)
}

let raw = request.results ?? []
var observations: [[String: Any]] = []
for (index, observation) in raw.enumerated() {
    let candidates = observation.topCandidates(3).prefix(3).map { candidate -> [String: Any] in
        ["text": candidate.string, "confidence": candidate.confidence]
    }
    let box = pixelBox(observation.boundingBox, width: decoded.1, height: decoded.2)
    let normalized: [String: Double] = [
        "x": observation.boundingBox.origin.x,
        "y": observation.boundingBox.origin.y,
        "width": observation.boundingBox.width,
        "height": observation.boundingBox.height,
    ]
    observations.append([
        "index": index,
        "candidates": candidates,
        "top_candidate": candidates.first?["text"] as? String ?? "",
        "confidence": Double((candidates.first?["confidence"] as? Float) ?? 0),
        "normalized_rectangle": normalized,
        "pixel_rectangle": box,
        "geometry_status": geometryStatus(box, width: decoded.1, height: decoded.2),
    ])
}

let transcript = assemble(observations)
let status = transcript.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty ? "empty_transcription" : "completed"
let finished = Date()
let payload: [String: Any] = [
    "schema_version": schemaVersion,
    "campaign_id": campaignID,
    "candidate": candidateID,
    "request_id": requestID,
    "dataset": dataset,
    "case_id": caseID,
    "page_index": pageIndex,
    "source_sha256": sourceSHA,
    "prepared_image_sha256": preparedSHA,
    "prepared_width": decoded.1,
    "prepared_height": decoded.2,
    "vision_request_revision": revision,
    "recognition_level": "accurate",
    "recognition_languages": ["en-US"],
    "uses_language_correction": false,
    "automatically_detects_language": false,
    "custom_words": [],
    "minimum_text_height": 0,
    "runtime_identity": [
        "os_build": osBuild(),
        "arch": machine(),
        "vision_revision": revision,
        "model_weight_digest": NSNull(),
        "model_weight_digest_available": false,
        "model_weight_limitation": "Vision does not expose an OCR weight hash. The OS build and request revision are the runtime identity.",
    ],
    "status": status,
    "error_code": status == "completed" ? NSNull() : status,
    "observations": observations,
    "assembled_transcription": transcript,
    "transcription_sha256": sha256Hex(Data(transcript.utf8)),
    "reading_order": readingOrder,
    "reading_order_uncertain": readingOrderUncertain(observations, width: decoded.1),
    "execution_started_utc": iso(started),
    "execution_completed_utc": iso(finished),
    "elapsed_seconds": finished.timeIntervalSince(started),
    "source_code_fingerprint": sourceFingerprint,
]
writeAtomic(payload, to: outputPath)
exit(status == "vision_request_failed" ? ExitCode.visionFailed.rawValue : ExitCode.ok.rawValue)
