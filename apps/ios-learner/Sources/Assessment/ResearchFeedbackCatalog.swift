#if DEBUG && targetEnvironment(simulator)
  import Foundation

  struct ResearchFeedbackPrompt: Identifiable, Equatable, Sendable {
    let id: String
    let word: String
    let phones: [String]
    let occurrenceIndex: Int
    let targetPhone: String
    var targetUnsupported: Bool { targetPhone == "ZH" }
    var requestPrompt: Prompt {
      Prompt(
        schemaVersion: 2, language: "en", transcript: word,
        words: [.init(text: word, phones: phones)],
        targets: [
          .init(id: id, wordIndex: 0, phoneIndex: occurrenceIndex, targetPhone: targetPhone)
        ])
    }
    struct Prompt: Encodable, Equatable, Sendable {
      let schemaVersion: Int
      let language: String
      let transcript: String
      let words: [Word]
      let targets: [Target]
    }
    struct Word: Encodable, Equatable, Sendable {
      let text: String
      let phones: [String]
    }
    struct Target: Encodable, Equatable, Sendable {
      let id: String
      let wordIndex: Int
      let phoneIndex: Int
      let targetPhone: String
    }
  }

  enum ResearchFeedbackCatalog {
    // Exact joined engineering pack; stress-free phones and selected occurrence are intentional.
    static let prompts: [ResearchFeedbackPrompt] = [
      entry("r-beginning-rabbit", "rabbit", ["R", "AE", "B", "AH", "T"], 0, "R"),
      entry("r-middle-bread", "bread", ["B", "R", "EH", "D"], 1, "R"),
      entry("r-end-door", "door", ["D", "AO", "R"], 2, "R"),
      entry("b-beginning-baby", "baby", ["B", "EY", "B", "IY"], 0, "B"),
      entry("b-middle-baby", "baby", ["B", "EY", "B", "IY"], 2, "B"),
      entry("n-middle-banana", "banana", ["B", "AH", "N", "AE", "N", "AH"], 2, "N"),
      entry("k-middle-backpack", "backpack", ["B", "AE", "K", "P", "AE", "K"], 2, "K"),
      entry("k-end-backpack", "backpack", ["B", "AE", "K", "P", "AE", "K"], 5, "K"),
      entry("s-beginning-sky", "sky", ["S", "K", "AY"], 0, "S"),
      entry("v-beginning-vase", "vase", ["V", "EY", "S"], 0, "V"),
      entry("y-beginning-yo-yo", "yo-yo", ["Y", "OW", "Y", "OW"], 0, "Y"),
      entry("th-beginning-thumb", "thumb", ["TH", "AH", "M"], 0, "TH"),
      entry("voiced-th-middle-feather", "feather", ["F", "EH", "DH", "ER"], 2, "DH"),
      entry("ng-end-ring", "ring", ["R", "IH", "NG"], 2, "NG"),
      entry("zh-middle-treasure", "treasure", ["T", "R", "EH", "ZH", "ER"], 3, "ZH"),
    ]
    private static func entry(
      _ id: String, _ word: String, _ phones: [String], _ index: Int, _ target: String
    ) -> ResearchFeedbackPrompt {
      .init(id: id, word: word, phones: phones, occurrenceIndex: index, targetPhone: target)
    }
  }
#endif
