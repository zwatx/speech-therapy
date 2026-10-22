#if DEBUG && targetEnvironment(simulator)
  import Foundation

  /// Exact reviewed browser successor, on a separately owned local native instance.
  /// Source metadata returned by the service cannot replace these compiled values.
  enum ResearchBrowserWordGuessService {
    static let origin = "http://127.0.0.1:8803"
    static let policyID = "consumer-recording-feedback-word-guess-v1"
    static let featureSourceSha256 =
      "f4c6b3931676c6d461d3efbe81a5942e467a9dc80ca769885dee1d54eb69f42e"
    static let pins = FeedbackContract.corePins.merging([
      "feedbackSourceSha256": "a593c3cac1af094d737638cb3bafa11d70cff7dc5d342f4efba6fbb21f7b2540",
      "wrapperSourceSha256": "a1b42b478b33e96a38cca4a449474ff5e4a844e9b4e95143ce8e7f7e39586f42",
      "feedbackPolicySha256": "6cd0ef602f6ba526262cbade869d91b83555822a13e14a9acb87a43f8527239d",
      "contentSha256": "beafb00cbfe5578560549abd0ebd1fbbfba88218521f3c50cbab654d8a33ebd1",
    ]) { _, new in new }
    static func requireConfigured() throws {
      guard pins.values.allSatisfy(FeedbackContract.isHash),
        FeedbackContract.isHash(featureSourceSha256)
      else { throw RecordingFeedbackError.invalidResponse }
    }
  }
#endif
