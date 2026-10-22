import CryptoKit
import Foundation

// Compiled with the real native catalog; no Swift-source parsing or model execution.
private let modelPhones = [
  "B", "P", "M", "T", "D", "N", "K", "G", "F", "V", "S", "Z", "SH", "CH", "JH", "L", "R", "W", "Y",
  "HH", "TH", "DH", "NG",
]
private let packIDs = [
  "r-beginning-rabbit", "r-middle-bread", "r-end-door",
  "b-beginning-baby", "b-middle-baby", "n-middle-banana",
  "k-middle-backpack", "k-end-backpack", "s-beginning-sky",
  "v-beginning-vase", "y-beginning-yo-yo", "th-beginning-thumb",
  "voiced-th-middle-feather", "ng-end-ring", "zh-middle-treasure",
]

struct AuditFailure: Error, CustomStringConvertible { let description: String }
func require(_ value: @autoclosure () -> Bool, _ message: String) throws {
  if !value() { throw AuditFailure(description: message) }
}
func indexes(_ phones: [String], target: String, position: PracticeTargetPosition? = nil) -> [Int] {
  phones.indices.filter { index in
    guard phones[index] == target else { return false }
    guard let position else { return true }
    switch position {
    case .beginning: return index == 0
    case .middle: return index > 0 && index < phones.count - 1
    case .end: return index == phones.count - 1
    }
  }
}
func keys(_ phones: [String]) -> Set<String> {
  Set(
    PracticeLibrary.targetPhones.flatMap { sound, target in
      PracticeTargetPosition.allCases.compactMap { position in
        indexes(phones, target: target, position: position).isEmpty
          ? nil : "\(sound):\(position.rawValue)"
      }
    })
}
func row(_ entry: PracticeLibraryEntry) -> [String: Any] {
  let variants = entry.prompt.pronunciationVariants
  let selected = variants.map { indexes($0, target: entry.targetPhone, position: entry.position) }
  let all = variants.map { indexes($0, target: entry.targetPhone) }
  return [
    "id": entry.id, "word": entry.prompt.word,
    "sourceWord": entry.prompt.sourceWord ?? "", "soundID": entry.soundID,
    "targetPhone": entry.targetPhone, "position": entry.position.rawValue,
    "modelTargetID": modelPhones.firstIndex(of: entry.targetPhone) as Any? ?? NSNull(),
    "modelInventorySupported": modelPhones.contains(entry.targetPhone),
    "pronunciationVariants": variants, "targetIndexesByVariant": all,
    "selectedPositionIndexesByVariant": selected,
    "repeatedTargetInAnyVariant": all.contains { $0.count > 1 },
    "multipleOccurrencesAtSelectedPosition": selected.contains { $0.count > 1 },
    "selectedIndexesDifferAcrossVariants": Set(selected).count > 1,
    "variantCount": variants.count,
  ]
}
func json(_ object: Any) throws -> Data {
  let data = try JSONSerialization.data(
    withJSONObject: object, options: [.prettyPrinted, .sortedKeys, .withoutEscapingSlashes])
  return data + Data([10])
}
func hash(_ url: URL) throws -> String {
  SHA256.hash(data: try Data(contentsOf: url)).map { String(format: "%02x", $0) }.joined()
}
func tests(_ entries: [PracticeLibraryEntry]) throws -> [String] {
  let byID = Dictionary(uniqueKeysWithValues: entries.map { ($0.id, $0) })
  func expect(
    _ id: String, _ target: String, _ position: PracticeTargetPosition, _ phones: [String]
  ) throws {
    guard let entry = byID[id] else { throw AuditFailure(description: "Missing oracle \(id)") }
    try require(
      entry.targetPhone == target && entry.position == position && entry.prompt.phones == phones,
      "Independent oracle mismatch \(id)")
  }
  try expect("s-beginning-sky", "S", .beginning, ["S", "K", "AY"])
  try expect("k-middle-sky", "K", .middle, ["S", "K", "AY"])
  try require(byID["k-beginning-sky"] == nil, "Clusters must not become first phones")
  try expect("r-middle-bread", "R", .middle, ["B", "R", "EH", "D"])
  try expect("r-end-door", "R", .end, ["D", "AO", "R"])
  try require(
    entries.filter { $0.prompt.word == "bird" }.allSatisfy { $0.targetPhone != "R" },
    "ER must not become R")
  try require(
    PracticeVocabulary.words.first { $0.word == "bird" }?.pronunciations == [["B", "ER", "D"]],
    "ER oracle")
  try require(
    byID["v-beginning-vase"]?.prompt.pronunciationVariants == [
      ["V", "EY", "S"], ["V", "AA", "Z"],
    ], "Vase variant oracle")
  try require(
    byID["s-end-vase"] == nil && byID["z-end-vase"] == nil,
    "Variant intersection must exclude alternate S/Z ends")
  try expect("n-middle-banana", "N", .middle, ["B", "AH", "N", "AE", "N", "AH"])
  try require(
    indexes(byID["n-middle-banana"]!.prompt.phones, target: "N", position: .middle) == [2, 4],
    "Repeated N occurrence oracle")
  try expect("y-beginning-yo-yo", "Y", .beginning, ["Y", "OW", "Y", "OW"])
  try require(byID["y-beginning-yo-yo"]?.prompt.sourceWord == "yoyo", "Source spelling alias")
  try require(
    !modelPhones.contains("ZH") && !modelPhones.contains("ER") && modelPhones.count == 23,
    "Independent fixed model inventory")
  try require(
    PracticeLibrary.entries(soundID: "ng", position: .beginning).isEmpty
      && PracticeLibrary.entries(soundID: "w", position: .end).isEmpty,
    "Unsupported positions stay empty")
  try require(PracticeLibrary.entries(soundID: "not-a-sound").isEmpty, "Unknown sound stays empty")
  return [
    "sky cluster positions", "bread interior R", "door final R", "bird ER exclusion",
    "vase alternate S/Z exclusion", "banana repeated interior N",
    "yo-yo source alias and repeated Y", "fixed 23-target inventory / ZH exclusion",
    "empty positions / unknown sound",
  ]
}

@main
struct CatalogAudit {
  static func main() {
    do { try run() } catch {
      FileHandle.standardError.write(Data("FAIL: \(error)\n".utf8))
      exit(1)
    }
  }

  static func run() throws {
    guard CommandLine.arguments.count == 3 else {
      throw AuditFailure(description: "Usage: catalog-audit REPOSITORY_ROOT OUTPUT_DIRECTORY")
    }
    let root = URL(fileURLWithPath: CommandLine.arguments[1], isDirectory: true)
    let output = URL(fileURLWithPath: CommandLine.arguments[2], isDirectory: true)
    let entries = PracticeLibrary.entries()
    try require(
      entries.count == 2398 && Set(entries.map { $0.prompt.word }).count == 892,
      "Catalog size drift: review scope before regenerating")
    try require(Set(entries.map(\.id)).count == entries.count, "Duplicate catalog IDs")
    try require(
      PracticeLibrary.sounds.count == 24 && PracticeVocabulary.words.count == 892, "Inventory drift"
    )
    try require(
      Set(PracticeLibrary.targetPhones.values) == Set(modelPhones + ["ZH"]), "Target mapping drift")
    for word in PracticeVocabulary.words {
      try require(
        !word.pronunciations.isEmpty && word.pronunciations.allSatisfy { !$0.isEmpty },
        "Empty pronunciation")
      let intersection = word.pronunciations.map(keys).dropFirst().reduce(
        keys(word.pronunciations[0])
      ) { $0.intersection($1) }
      try require(
        Set(word.targetKeys) == intersection && word.targetKeys.count == intersection.count,
        "Dictionary target mismatch for \(word.word)")
      let actual = Set(
        entries.filter { $0.prompt.word == word.word }.map {
          "\($0.soundID):\($0.position.rawValue)"
        })
      try require(actual == intersection, "Public catalog mismatch for \(word.word)")
    }
    for entry in entries {
      try require(
        entry.prompt.pronunciationSource == PracticeVocabulary.sourceID,
        "Unbound pronunciation source")
      try require(
        entry.prompt.phones == entry.prompt.pronunciationVariants.first, "Primary variant drift")
      try require(
        entry.prompt.pronunciationVariants.allSatisfy {
          !indexes($0, target: entry.targetPhone, position: entry.position).isEmpty
        }, "Unverified position \(entry.id)")
    }
    let passed = try tests(entries)
    let rows = entries.map(row)
    let supportedCount = entries.filter { modelPhones.contains($0.targetPhone) }.count
    let repeated = rows.filter { $0["repeatedTargetInAnyVariant"] as? Bool == true }.count
    let ambiguous = rows.filter { $0["multipleOccurrencesAtSelectedPosition"] as? Bool == true }
      .count
    let shifted = rows.filter { $0["selectedIndexesDifferAcrossVariants"] as? Bool == true }.count
    let sources = try [
      "apps/ios-learner/Sources/DirectPractice/PracticeLibrary.swift",
      "apps/ios-learner/Sources/DirectPractice/PracticeVocabulary.swift",
      "docs/consumer-assessment/catalog-audit.swift",
    ].map { path in
      ["path": path, "sha256": try hash(root.appendingPathComponent(path))]
    }
    let counts = PracticeLibrary.sounds.map { sound -> [String: Any] in
      [
        "soundID": sound.id, "phone": PracticeLibrary.targetPhones[sound.id]!,
        "modelInventorySupported": modelPhones.contains(PracticeLibrary.targetPhones[sound.id]!),
        "positions": Dictionary(
          uniqueKeysWithValues: PracticeTargetPosition.allCases.map {
            ($0.rawValue, PracticeLibrary.entries(soundID: sound.id, position: $0).count)
          }),
      ]
    }
    let report: [String: Any] = [
      "schemaVersion": 1,
      "scope":
        "Native dictionary metadata and model inventory only; no model inference, clinical validation or corpus overlap recomputation",
      "sourceID": PracticeVocabulary.sourceID, "sources": sources,
      "modelTargetPhonesInIDOrder": modelPhones,
      "distinctWords": 892, "entries": entries.count,
      "modelInventorySupportedEntries": supportedCount,
      "unsupportedZHEntries": entries.count - supportedCount, "ERIncludedAsR": false,
      "wordsWithMultipleDictionaryVariants": PracticeVocabulary.words.filter {
        $0.pronunciations.count > 1
      }.count,
      "entriesWithRepeatedTargetInAnyVariant": repeated,
      "entriesWithMultipleSelectedPositionOccurrences": ambiguous,
      "entriesWithSelectedIndexesDifferingAcrossVariants": shifted,
      "entryVariantPositionMemberships": rows.reduce(0) {
        $0 + ($1["pronunciationVariants"] as! [[String]]).count
      },
      "allPronunciationTargetOccurrences": rows.reduce(0) {
        $0 + ($1["selectedPositionIndexesByVariant"] as! [[Int]]).reduce(0) { $0 + $1.count }
      },
      "countsBySound": counts, "testsPassed": passed, "catalog": rows,
      "historical72PromptCohortOverlapAppliedToExpandedCatalog": false,
    ]
    let byID = Dictionary(uniqueKeysWithValues: entries.map { ($0.id, $0) })
    let pack = try packIDs.map { id -> [String: Any] in
      guard let entry = byID[id] else {
        throw AuditFailure(description: "Proposed prompt absent: \(id)")
      }
      var result = row(entry)
      result["reviewStatus"] = "pending"
      result["intendedUse"] = "internal engineering exercise only"
      result["learnerFindingEligible"] = false
      return result
    }
    try FileManager.default.createDirectory(at: output, withIntermediateDirectories: true)
    try json(report).write(to: output.appendingPathComponent("catalog-coverage.json"))
    try json([
      "schemaVersion": 1, "status": "PROPOSED / ALL REVIEW PENDING", "catalogSourceHashes": sources,
      "prompts": pack,
    ]).write(to: output.appendingPathComponent("proposed-engineering-pack.json"))
    var markdown =
      "# Current native catalog coverage\n\nGenerated by compiling the real native library with `catalog-audit.swift`. Metadata only: inventory compatibility is not pronunciation accuracy, target localization, clinical suitability, or product eligibility.\n\n"
    markdown +=
      "892 distinct words; \(entries.count) entries; \(supportedCount) entries map to the 23 model targets; \(entries.count - supportedCount) ZH entries unsupported. ER is excluded from R. \(PracticeVocabulary.words.filter { $0.pronunciations.count > 1 }.count) words have multiple dictionary variants.\n\n"
    markdown +=
      "\(repeated) entries have a repeated target in at least one variant; \(ambiguous) have multiple occurrences within the selected position; \(shifted) have selected occurrence indexes that differ across variants. An entry describes a word/target/position, not one uniquely localized occurrence. There are 2,637 entry/variant position memberships and 2,644 individual occurrences; repeated occurrences account for the difference. Zero-based indexes and complete variants are retained in the JSON.\n\n"
    markdown +=
      "| Sound | Phone | Beginning | Middle | End | Model inventory |\n| --- | --- | ---: | ---: | ---: | --- |\n"
    for sound in PracticeLibrary.sounds {
      let counts = PracticeTargetPosition.allCases.map {
        PracticeLibrary.entries(soundID: sound.id, position: $0).count
      }
      markdown +=
        "| \(sound.id) | \(PracticeLibrary.targetPhones[sound.id]!) | \(counts[0]) | \(counts[1]) | \(counts[2]) | \(sound.id == "zh" ? "Unsupported" : "Supported inventory only") |\n"
    }
    markdown +=
      "\nThe September 26 audit's 29/72 all-age and 17/72 age-6–12 overlaps describe starter word/phone joins only. They are not reused for 892 words, do not verify position and are not a performance estimate. Expanded cohort overlap is **not recomputed** here. No corpus/archive, audio, TEST, features or model checkpoint was read.\n\nNine independent named oracle groups and exhaustive dictionary/catalog intersection checks passed. This report also fails on inventory/count drift instead of silently changing assessment scope.\n\nSources:\n\n"
    for source in sources { markdown += "- `\(source["path"]!)`: `\(source["sha256"]!)`\n" }
    try Data(markdown.utf8).write(to: output.appendingPathComponent("catalog-coverage.md"))
    print(
      "PASS: \(passed.count) oracle groups; exhaustive \(entries.count)-entry / 892-word audit; \(supportedCount) supported inventory, \(entries.count - supportedCount) unsupported ZH; \(pack.count) pending engineering prompts"
    )
  }
}
