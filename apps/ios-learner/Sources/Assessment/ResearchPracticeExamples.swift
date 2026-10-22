#if DEBUG && targetEnvironment(simulator)
  import Foundation

  struct ResearchPracticeExample: Equatable, Sendable {
    let sourceWord: String
    let author: String
    let licenseId: String
    let licenseURL: URL
    let sourceURL: URL
    let attribution: String
    let changes: String
    let speakerAgeKnown: Bool
    let clinicalReferenceApproved: Bool
    let wavSha256: String
    let sampleCount: Int
    var declaredVariety = "Not stated"
    var isGeneratedFixture = false
    var listeningCue: String? = nil
  }

  enum ResearchPracticeExamples {
    static let registrySha256 = "01de20fb2759fc7605bcf20322749a9405961ce5f33f20acbbe73508f2e61564"
    // Metadata only, copied from the immutable public registry; no audio is bundled.
    static let all: [ResearchPracticeExample] = [
      .init(
        sourceWord: "baby", author: "Dvortygirl",
        licenseId: "CC-BY-SA-3.0",
        licenseURL: URL(string: "https://creativecommons.org/licenses/by-sa/3.0/")!,
        sourceURL: URL(string: "https://commons.wikimedia.org/wiki/File:En-us-baby.ogg")!,
        attribution:
          "File:En-us-baby.ogg — Dvortygirl; https://commons.wikimedia.org/wiki/File:En-us-baby.ogg; https://creativecommons.org/licenses/by-sa/3.0/. Converted original to mono 16000 Hz PCM16 WAV; no trimming, normalization or speed changes.",
        changes:
          "Converted original to mono 16000 Hz PCM16 WAV; no trimming, normalization or speed changes.",
        speakerAgeKnown: false, clinicalReferenceApproved: false,
        wavSha256: "be0331bf2637fb7510ef04e7ac484c3a77e0efe8cc51cb5c3ed1c8c111987910",
        sampleCount: 7988, declaredVariety: "US English (source label)"),
      .init(
        sourceWord: "backpack", author: "Association Shtooka, Judith Franck",
        licenseId: "CC-BY-3.0-US",
        licenseURL: URL(string: "https://creativecommons.org/licenses/by/3.0/us/")!,
        sourceURL: URL(string: "https://commons.wikimedia.org/wiki/File:En-uk-backpack.ogg")!,
        attribution:
          "File:En-uk-backpack.ogg — Association Shtooka, Judith Franck; https://commons.wikimedia.org/wiki/File:En-uk-backpack.ogg; https://creativecommons.org/licenses/by/3.0/us/. Converted original to mono 16000 Hz PCM16 WAV; no trimming, normalization or speed changes.",
        changes:
          "Converted original to mono 16000 Hz PCM16 WAV; no trimming, normalization or speed changes.",
        speakerAgeKnown: false, clinicalReferenceApproved: false,
        wavSha256: "986d80cad188e2157180af7e5badfbd84efa2af26d234503d932726047505e52",
        sampleCount: 23200, declaredVariety: "London, England (source label)"),
      .init(
        sourceWord: "banana", author: "Dvortygirl",
        licenseId: "CC-BY-SA-3.0",
        licenseURL: URL(string: "https://creativecommons.org/licenses/by-sa/3.0/")!,
        sourceURL: URL(string: "https://commons.wikimedia.org/wiki/File:En-us-banana.ogg")!,
        attribution:
          "File:En-us-banana.ogg — Dvortygirl; https://commons.wikimedia.org/wiki/File:En-us-banana.ogg; https://creativecommons.org/licenses/by-sa/3.0/. Converted original to mono 16000 Hz PCM16 WAV; no trimming, normalization or speed changes.",
        changes:
          "Converted original to mono 16000 Hz PCM16 WAV; no trimming, normalization or speed changes.",
        speakerAgeKnown: false, clinicalReferenceApproved: false,
        wavSha256: "8a90981bb21ef4137d9a52dd4d9b38457bbda014ce684f12910303ea5eaf7054",
        sampleCount: 9474, declaredVariety: "US English (source label)"),
      .init(
        sourceWord: "bread", author: "Dvortygirl",
        licenseId: "CC-BY-SA-3.0",
        licenseURL: URL(string: "https://creativecommons.org/licenses/by-sa/3.0/")!,
        sourceURL: URL(string: "https://commons.wikimedia.org/wiki/File:En-us-bread.ogg")!,
        attribution:
          "File:En-us-bread.ogg — Dvortygirl; https://commons.wikimedia.org/wiki/File:En-us-bread.ogg; https://creativecommons.org/licenses/by-sa/3.0/. Converted original to mono 16000 Hz PCM16 WAV; no trimming, normalization or speed changes.",
        changes:
          "Converted original to mono 16000 Hz PCM16 WAV; no trimming, normalization or speed changes.",
        speakerAgeKnown: false, clinicalReferenceApproved: false,
        wavSha256: "0972084b7673d4d3053ca5c73f9c2ca81ee98bb580a401061ca55bb51ee5ac6f",
        sampleCount: 8917, declaredVariety: "US English (source label)",
        listeningCue:
          "Listen for b followed by r in bread. Say the word, then listen to your own try."),
      .init(
        sourceWord: "door", author: "Dvortygirl",
        licenseId: "CC-BY-SA-3.0",
        licenseURL: URL(string: "https://creativecommons.org/licenses/by-sa/3.0/")!,
        sourceURL: URL(string: "https://commons.wikimedia.org/wiki/File:En-us-door.ogg")!,
        attribution:
          "File:En-us-door.ogg — Dvortygirl; https://commons.wikimedia.org/wiki/File:En-us-door.ogg; https://creativecommons.org/licenses/by-sa/3.0/. Converted original to mono 16000 Hz PCM16 WAV; no trimming, normalization or speed changes.",
        changes:
          "Converted original to mono 16000 Hz PCM16 WAV; no trimming, normalization or speed changes.",
        speakerAgeKnown: false, clinicalReferenceApproved: false,
        wavSha256: "146f916071bcf40a9ee4a8b02b9c62b662b80db574b368eadb4fa8cd67586756",
        sampleCount: 9288, declaredVariety: "US English (source label)"),
      .init(
        sourceWord: "feather", author: "Dvortygirl",
        licenseId: "PD-self",
        licenseURL: URL(string: "https://commons.wikimedia.org/wiki/Template:PD-self")!,
        sourceURL: URL(string: "https://commons.wikimedia.org/wiki/File:En-us-feather.ogg")!,
        attribution:
          "File:En-us-feather.ogg — Dvortygirl; https://commons.wikimedia.org/wiki/File:En-us-feather.ogg; https://commons.wikimedia.org/wiki/Template:PD-self. Converted original to mono 16000 Hz PCM16 WAV; no trimming, normalization or speed changes.",
        changes:
          "Converted original to mono 16000 Hz PCM16 WAV; no trimming, normalization or speed changes.",
        speakerAgeKnown: false, clinicalReferenceApproved: false,
        wavSha256: "a48142bfe8f4886f606109daa6f67206fed2e473d24de31bd0cdc38312340a98",
        sampleCount: 7988, declaredVariety: "US English (source label)"),
      .init(
        sourceWord: "rabbit", author: "Dvortygirl",
        licenseId: "CC-BY-SA-3.0",
        licenseURL: URL(string: "https://creativecommons.org/licenses/by-sa/3.0/")!,
        sourceURL: URL(string: "https://commons.wikimedia.org/wiki/File:En-us-rabbit.ogg")!,
        attribution:
          "File:En-us-rabbit.ogg — Dvortygirl; https://commons.wikimedia.org/wiki/File:En-us-rabbit.ogg; https://creativecommons.org/licenses/by-sa/3.0/. Converted original to mono 16000 Hz PCM16 WAV; no trimming, normalization or speed changes.",
        changes:
          "Converted original to mono 16000 Hz PCM16 WAV; no trimming, normalization or speed changes.",
        speakerAgeKnown: false, clinicalReferenceApproved: false,
        wavSha256: "e544766a3d828bf7a798869d919d5b9ad480461453ac1213ee57b48f8abf0509",
        sampleCount: 16800, declaredVariety: "US English (source label)"),
      .init(
        sourceWord: "ring", author: "Dvortygirl",
        licenseId: "CC-BY-SA-3.0",
        licenseURL: URL(string: "https://creativecommons.org/licenses/by-sa/3.0/")!,
        sourceURL: URL(string: "https://commons.wikimedia.org/wiki/File:En-us-ring.ogg")!,
        attribution:
          "File:En-us-ring.ogg — Dvortygirl; https://commons.wikimedia.org/wiki/File:En-us-ring.ogg; https://creativecommons.org/licenses/by-sa/3.0/. Converted original to mono 16000 Hz PCM16 WAV; no trimming, normalization or speed changes.",
        changes:
          "Converted original to mono 16000 Hz PCM16 WAV; no trimming, normalization or speed changes.",
        speakerAgeKnown: false, clinicalReferenceApproved: false,
        wavSha256: "9d561065a5c2367d2a4c7341a23409de8789cb960652cfa188910c2a0d129a60",
        sampleCount: 9660, declaredVariety: "US English (source label)"),
      .init(
        sourceWord: "sky", author: "Dvortygirl",
        licenseId: "CC-BY-SA-3.0",
        licenseURL: URL(string: "https://creativecommons.org/licenses/by-sa/3.0/")!,
        sourceURL: URL(string: "https://commons.wikimedia.org/wiki/File:En-us-sky.ogg")!,
        attribution:
          "File:En-us-sky.ogg — Dvortygirl; https://commons.wikimedia.org/wiki/File:En-us-sky.ogg; https://creativecommons.org/licenses/by-sa/3.0/. Converted original to mono 16000 Hz PCM16 WAV; no trimming, normalization or speed changes.",
        changes:
          "Converted original to mono 16000 Hz PCM16 WAV; no trimming, normalization or speed changes.",
        speakerAgeKnown: false, clinicalReferenceApproved: false,
        wavSha256: "f845c1107b957194a15ac71fc7c0e9b4c78ea701d794d3edcb33ac7af5babe08",
        sampleCount: 12818, declaredVariety: "US English (source label)"),
      .init(
        sourceWord: "thumb", author: "Dvortygirl",
        licenseId: "PD-self",
        licenseURL: URL(string: "https://commons.wikimedia.org/wiki/Template:PD-self")!,
        sourceURL: URL(string: "https://commons.wikimedia.org/wiki/File:En-us-thumb.ogg")!,
        attribution:
          "File:En-us-thumb.ogg — Dvortygirl; https://commons.wikimedia.org/wiki/File:En-us-thumb.ogg; https://commons.wikimedia.org/wiki/Template:PD-self. Converted original to mono 16000 Hz PCM16 WAV; no trimming, normalization or speed changes.",
        changes:
          "Converted original to mono 16000 Hz PCM16 WAV; no trimming, normalization or speed changes.",
        speakerAgeKnown: false, clinicalReferenceApproved: false,
        wavSha256: "76a9ea588340396eced30cf4bfed5529004c2c6c1c38d4a2869d5cd0cb96459a",
        sampleCount: 8731, declaredVariety: "US English (source label)"),
      .init(
        sourceWord: "treasure", author: "Dvortygirl",
        licenseId: "CC-BY-SA-3.0",
        licenseURL: URL(string: "https://creativecommons.org/licenses/by-sa/3.0/")!,
        sourceURL: URL(string: "https://commons.wikimedia.org/wiki/File:En-us-treasure.ogg")!,
        attribution:
          "File:En-us-treasure.ogg — Dvortygirl; https://commons.wikimedia.org/wiki/File:En-us-treasure.ogg; https://creativecommons.org/licenses/by-sa/3.0/. Converted original to mono 16000 Hz PCM16 WAV; no trimming, normalization or speed changes.",
        changes:
          "Converted original to mono 16000 Hz PCM16 WAV; no trimming, normalization or speed changes.",
        speakerAgeKnown: false, clinicalReferenceApproved: false,
        wavSha256: "499cb32168362ab804da2f91b6c2278f8933d25358cd4fa3457c70c5458caa75",
        sampleCount: 15200, declaredVariety: "US English (source label)"),
      .init(
        sourceWord: "vase", author: "Dvortygirl",
        licenseId: "CC-BY-SA-3.0",
        licenseURL: URL(string: "https://creativecommons.org/licenses/by-sa/3.0/")!,
        sourceURL: URL(string: "https://commons.wikimedia.org/wiki/File:En-us-vase.ogg")!,
        attribution:
          "File:En-us-vase.ogg — Dvortygirl; https://commons.wikimedia.org/wiki/File:En-us-vase.ogg; https://creativecommons.org/licenses/by-sa/3.0/. Converted original to mono 16000 Hz PCM16 WAV; no trimming, normalization or speed changes.",
        changes:
          "Converted original to mono 16000 Hz PCM16 WAV; no trimming, normalization or speed changes.",
        speakerAgeKnown: false, clinicalReferenceApproved: false,
        wavSha256: "f74652e0f412efdb0d12061dd22051e41909c00f305e82e3e9c142472c32c463",
        sampleCount: 16800, declaredVariety: "US English (source label)"),
      .init(
        sourceWord: "yoyo", author: "Speaker:  Flame, not lame \n Recorder:  Flame, not lame",
        licenseId: "CC0-1.0",
        licenseURL: URL(string: "https://creativecommons.org/publicdomain/zero/1.0/")!,
        sourceURL: URL(
          string: "https://commons.wikimedia.org/wiki/File:LL-Q1860_(eng)-Flame,_not_lame-yoyo.wav")!,
        attribution:
          "File:LL-Q1860 (eng)-Flame, not lame-yoyo.wav — Speaker:  Flame, not lame \n Recorder:  Flame, not lame; https://commons.wikimedia.org/wiki/File:LL-Q1860_(eng)-Flame,_not_lame-yoyo.wav; https://creativecommons.org/publicdomain/zero/1.0/. Converted original to mono 16000 Hz PCM16 WAV; no trimming, normalization or speed changes.",
        changes:
          "Converted original to mono 16000 Hz PCM16 WAV; no trimming, normalization or speed changes.",
        speakerAgeKnown: false, clinicalReferenceApproved: false,
        wavSha256: "2ca417bba1f21128359df0da0d1c418f801b85f4575863293a9fa7ac7a68abc4",
        sampleCount: 18859, declaredVariety: "English; variety unspecified"),
    ]
    private static let sourceWords: [String: String] = [
      "r-beginning-rabbit": "rabbit",
      "r-middle-bread": "bread",
      "r-end-door": "door",
      "b-beginning-baby": "baby",
      "b-middle-baby": "baby",
      "n-middle-banana": "banana",
      "k-middle-backpack": "backpack",
      "k-end-backpack": "backpack",
      "s-beginning-sky": "sky",
      "v-beginning-vase": "vase",
      "y-beginning-yo-yo": "yoyo",
      "th-beginning-thumb": "thumb",
      "voiced-th-middle-feather": "feather",
      "ng-end-ring": "ring",
      "zh-middle-treasure": "treasure",
    ]
    static func example(for prompt: ResearchFeedbackPrompt) -> ResearchPracticeExample? {
      guard ResearchFeedbackCatalog.prompts.contains(prompt),
        let sourceWord = sourceWords[prompt.id]
      else { return nil }
      return all.first { $0.sourceWord == sourceWord }
    }
  }
#endif
