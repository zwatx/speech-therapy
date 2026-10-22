import Foundation

enum PracticeTargetPosition: String, CaseIterable, Sendable {
  case beginning
  case middle
  case end

  var label: String { rawValue.capitalized }
}

struct PracticePrompt: Identifiable, Equatable, Sendable {
  let id: String
  let word: String
  let systemImage: String
  /// Stress-free ARPABET phones from the first listed source pronunciation.
  let phones: [String]
  let pronunciationVariants: [[String]]
  let pronunciationSource: String?
  let sourceWord: String?

  init(
    id: String,
    word: String,
    systemImage: String,
    phones: [String] = [],
    pronunciationVariants: [[String]] = [],
    pronunciationSource: String? = nil,
    sourceWord: String? = nil
  ) {
    self.id = id
    self.word = word
    self.systemImage = systemImage
    self.phones = phones
    self.pronunciationVariants = pronunciationVariants
    self.pronunciationSource = pronunciationSource
    self.sourceWord = sourceWord
  }
}

struct PracticeLibraryEntry: Identifiable, Equatable, Sendable {
  let soundID: String
  let position: PracticeTargetPosition
  let prompt: PracticePrompt

  var id: String { prompt.id }
  var targetPhone: String { PracticeLibrary.targetPhones[soundID] ?? "" }
}

struct PracticeSound: Identifiable, Equatable, Sendable {
  let id: String
  let symbol: String
  let name: String
  let position: PracticeTargetPosition
  let prompts: [PracticePrompt]

  var targetLabel: String { "\(position.label) /\(symbol)/" }
}

/// Curated words for self-directed practice, with positions checked against CMUdict.
/// Positions refer to the first, interior, or last phone, including consonant clusters.
enum PracticeLibrary {
  static let sourceNotice = "Pronunciations from CMUdict · US English"
  static let sourceLicense = PracticeVocabulary.license
  static let reviewNotice = "Practice vocabulary review pending · Not a prescribed treatment plan"

  // R is the consonantal CMUdict R phone; the rhotic vowel ER is not included.
  static let targetPhones: [String: String] = [
    "b": "B", "p": "P", "m": "M", "t": "T", "d": "D", "n": "N",
    "k": "K", "g": "G", "f": "F", "v": "V", "s": "S", "z": "Z",
    "sh": "SH", "ch": "CH", "j": "JH", "l": "L", "r": "R", "w": "W",
    "y": "Y", "h": "HH", "th": "TH", "voiced-th": "DH", "ng": "NG", "zh": "ZH",
  ]

  static let sounds: [PracticeSound] = [
    sound(
      "b", "b", "B sound",
      words: [
        ("ball", "basketball.fill"), ("boat", "sailboat.fill"), ("bee", "text.bubble.fill"),
      ]),
    sound(
      "p", "p", "P sound",
      words: [
        ("pig", "text.bubble.fill"), ("pear", "text.bubble.fill"), ("pie", "text.bubble.fill"),
      ]),
    sound(
      "m", "m", "M sound",
      words: [
        ("moon", "moon.fill"), ("mouse", "text.bubble.fill"), ("milk", "text.bubble.fill"),
      ]),
    sound(
      "t", "t", "T sound",
      words: [
        ("tiger", "text.bubble.fill"), ("toe", "text.bubble.fill"), ("tent", "tent.fill"),
      ]),
    sound(
      "d", "d", "D sound",
      words: [
        ("dog", "dog.fill"), ("duck", "text.bubble.fill"), ("door", "door.left.hand.closed"),
      ]),
    sound(
      "n", "n", "N sound",
      words: [
        ("nest", "text.bubble.fill"), ("nose", "text.bubble.fill"), ("net", "text.bubble.fill"),
      ]),
    sound(
      "k", "k", "K sound",
      words: [
        ("cat", "cat.fill"), ("key", "key.fill"), ("kite", "text.bubble.fill"),
      ]),
    sound(
      "g", "ɡ", "G sound",
      words: [
        ("goat", "text.bubble.fill"), ("gate", "text.bubble.fill"), ("gum", "text.bubble.fill"),
      ]),
    sound(
      "f", "f", "F sound",
      words: [
        ("fish", "fish.fill"), ("fan", "fan.fill"), ("feet", "text.bubble.fill"),
      ]),
    sound(
      "v", "v", "V sound",
      words: [
        ("van", "text.bubble.fill"), ("vase", "text.bubble.fill"), ("vest", "text.bubble.fill"),
      ]),
    sound(
      "s", "s", "S sound",
      words: [
        ("sun", "sun.max.fill"), ("sock", "text.bubble.fill"),
        ("soap", "bubbles.and.sparkles.fill"),
      ]),
    sound(
      "z", "z", "Z sound",
      words: [
        ("zebra", "text.bubble.fill"), ("zipper", "text.bubble.fill"), ("zoo", "text.bubble.fill"),
      ]),
    sound(
      "sh", "ʃ", "SH sound",
      words: [
        ("ship", "ferry.fill"), ("shoe", "shoe.fill"), ("shell", "text.bubble.fill"),
      ]),
    sound(
      "ch", "tʃ", "CH sound",
      words: [
        ("chair", "chair.fill"), ("cheese", "text.bubble.fill"), ("chick", "text.bubble.fill"),
      ]),
    sound(
      "j", "dʒ", "J sound",
      words: [
        ("juice", "text.bubble.fill"), ("jam", "text.bubble.fill"), ("jacket", "text.bubble.fill"),
      ]),
    sound(
      "l", "l", "L sound",
      words: [
        ("leaf", "leaf.fill"), ("lion", "text.bubble.fill"), ("lamp", "lamp.desk.fill"),
      ]),
    sound(
      "r", "ɹ", "R sound",
      words: [
        ("rabbit", "hare.fill"), ("rain", "cloud.rain.fill"), ("ring", "circle"),
      ]),
    sound(
      "w", "w", "W sound",
      words: [
        ("web", "text.bubble.fill"), ("wing", "text.bubble.fill"), ("wagon", "text.bubble.fill"),
      ]),
    sound(
      "y", "j", "Y sound",
      words: [
        ("yarn", "text.bubble.fill"), ("yo-yo", "text.bubble.fill"), ("yogurt", "text.bubble.fill"),
      ]),
    sound(
      "h", "h", "H sound",
      words: [
        ("hat", "text.bubble.fill"), ("horse", "text.bubble.fill"), ("house", "house.fill"),
      ]),
    sound(
      "th", "θ", "TH · thumb",
      words: [
        ("thumb", "hand.thumbsup.fill"), ("thorn", "text.bubble.fill"),
        ("thread", "text.bubble.fill"),
      ]),
    sound(
      "voiced-th", "ð", "TH · feather", position: .middle,
      words: [
        ("feather", "text.bubble.fill"), ("weather", "cloud.sun.fill"), ("mother", "person.fill"),
      ]),
    sound(
      "ng", "ŋ", "NG sound", position: .end,
      words: [
        ("ring", "circle"), ("wing", "text.bubble.fill"), ("king", "crown.fill"),
      ]),
    sound(
      "zh", "ʒ", "ZH · treasure", position: .middle,
      words: [
        ("treasure", "sparkles"), ("measure", "ruler.fill"), ("television", "tv.fill"),
      ]),
  ]

  static var starterSound: PracticeSound { sounds[0] }

  static var wordCount: Int { PracticeVocabulary.words.count }
  static var entryCount: Int { catalog.count }

  /// Sound order, then beginning/middle/end. Starter words lead each sound's default
  /// position; the remaining words are alphabetic. Filtering preserves this order.
  static func entries(
    soundID: String? = nil,
    position: PracticeTargetPosition? = nil,
    query: String = ""
  ) -> [PracticeLibraryEntry] {
    let search = normalized(query)
    return catalog.filter { entry in
      (soundID == nil || entry.soundID == soundID)
        && (position == nil || entry.position == position)
        && (search.isEmpty || entry.prompt.word.contains(search)
          || entry.prompt.sourceWord?.contains(search) == true)
    }
  }

  /// Start at a matching selected word, then continue forward for up to three words.
  /// The final session can contain one or two words. It never wraps to earlier words.
  /// Unknown sounds, mismatched selected IDs, empty results, or nonpositive limits return nil.
  static func session(
    soundID: String,
    position: PracticeTargetPosition,
    query: String = "",
    startingAt entryID: String? = nil,
    limit: Int = 3
  ) -> PracticeSound? {
    guard limit > 0, let sound = sounds.first(where: { $0.id == soundID }) else {
      return nil
    }
    let matching = entries(soundID: soundID, position: position, query: query)
    let start: Int
    if let entryID {
      guard let index = matching.firstIndex(where: { $0.id == entryID }) else { return nil }
      start = index
    } else {
      start = 0
    }
    let prompts = matching.dropFirst(start).prefix(min(limit, 3)).map(\.prompt)
    guard !prompts.isEmpty else { return nil }
    return PracticeSound(
      id: sound.id,
      symbol: sound.symbol,
      name: sound.name,
      position: position,
      prompts: prompts
    )
  }

  /// Continue in the complete sound/position list. At the end, return nil.
  static func nextEntryID(
    after entryID: String,
    soundID: String,
    position: PracticeTargetPosition
  ) -> String? {
    let matching = entries(soundID: soundID, position: position)
    guard let index = matching.firstIndex(where: { $0.id == entryID }),
      index + 1 < matching.count
    else { return nil }
    return matching[index + 1].id
  }

  private static let vocabularyByWord = Dictionary(
    uniqueKeysWithValues: PracticeVocabulary.words.map { ($0.word, $0) })

  private static let catalog: [PracticeLibraryEntry] = sounds.flatMap { sound in
    PracticeTargetPosition.allCases.flatMap { position in
      let key = "\(sound.id):\(position.rawValue)"
      let matching = PracticeVocabulary.words.filter { $0.targetKeys.contains(key) }
      let starters = position == sound.position ? sound.prompts : []
      let starterWords = Set(starters.map(\.word))
      let prompts =
        starters
        + matching.filter { !starterWords.contains($0.word) }.map {
          prompt(for: $0, soundID: sound.id, position: position)
        }
      return prompts.map { PracticeLibraryEntry(soundID: sound.id, position: position, prompt: $0) }
    }
  }

  private static func normalized(_ text: String) -> String {
    text.folding(
      options: [.caseInsensitive, .diacriticInsensitive], locale: Locale(identifier: "en_US_POSIX")
    )
    .trimmingCharacters(in: .whitespacesAndNewlines)
  }

  private static func prompt(
    for word: PracticeVocabularyWord,
    soundID: String,
    position: PracticeTargetPosition,
    systemImage: String = "text.bubble.fill"
  ) -> PracticePrompt {
    PracticePrompt(
      id: "\(soundID)-\(position.rawValue)-\(word.word)",
      word: word.word,
      systemImage: systemImage,
      phones: word.pronunciations[0],
      pronunciationVariants: word.pronunciations,
      pronunciationSource: PracticeVocabulary.sourceID,
      sourceWord: word.sourceWord
    )
  }

  private static func sound(
    _ id: String,
    _ symbol: String,
    _ name: String,
    position: PracticeTargetPosition = .beginning,
    words: [(String, String)]
  ) -> PracticeSound {
    PracticeSound(
      id: id,
      symbol: symbol,
      name: name,
      position: position,
      prompts: words.map { word, image in
        guard let vocabularyWord = vocabularyByWord[word] else {
          preconditionFailure("Starter word is missing verified pronunciation: \(word)")
        }
        return prompt(for: vocabularyWord, soundID: id, position: position, systemImage: image)
      }
    )
  }
}
