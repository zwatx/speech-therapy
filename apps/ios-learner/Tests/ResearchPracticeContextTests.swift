#if DEBUG && targetEnvironment(simulator)
  import Foundation
  import XCTest
  @testable import CadenceLearner

  @MainActor
  final class ResearchPracticeContextTests: XCTestCase {
    func testExactAdultAndChildBoundaryBytesWithoutAgeImputation() throws {
      let encoder = FeedbackContract.encoder()
      for (context, expected) in [
        (ResearchPracticeContext.adult, #"{"kind":"adult"}"#),
        (.child(ageYears: 6), #"{"ageYears":6,"kind":"child"}"#),
        (.child(ageYears: 12), #"{"ageYears":12,"kind":"child"}"#),
      ] {
        let bytes = try encoder.encode(context)
        XCTAssertEqual(bytes, Data(expected.utf8)); XCTAssertEqual(try ResearchPracticeContext.decode(bytes), context)
      }
      for age in [5, 13, 18] { XCTAssertThrowsError(try encoder.encode(ResearchPracticeContext.child(ageYears: age))) }
    }
    func testClosedRawContextRejectsUnknownExtraBooleanFloatStringAndDuplicateFields() {
      for raw in ["null", "[]", "{}", #"{"kind":"unknown"}"#, #"{"kind":"adult","ageYears":18}"#,
        #"{"kind":"adult","extra":false}"#, #"{"kind":"child"}"#, #"{"kind":"child","ageYears":true}"#,
        #"{"kind":"child","ageYears":9.0}"#, #"{"kind":"child","ageYears":"9"}"#,
        #"{"kind":"child","ageYears":5}"#, #"{"kind":"child","ageYears":13}"#,
        #"{"kind":"adult","kind":"child"}"#,
      ] { XCTAssertThrowsError(try ResearchPracticeContext.decode(Data(raw.utf8)), raw) }
    }
    func testActualRequestSerializerUsesSchema2AndContextChangesOnlyRequestBinding() throws {
      let audio = FeedbackFixture.wav(); let prompt = ResearchFeedbackCatalog.prompts[1]
      let adult = try ResearchFeedbackClient.requestBody(attemptId: FeedbackFixture.attempt, audio: audio, prompt: prompt, practiceContext: .adult)
      let child = try ResearchFeedbackClient.requestBody(attemptId: FeedbackFixture.attempt, audio: audio, prompt: prompt, practiceContext: .child(ageYears: 9))
      let value = try JSONSerialization.jsonObject(with: adult) as! [String: Any]
      XCTAssertEqual(Set(value.keys), ["schemaVersion", "attemptId", "practiceContext", "prompt", "audioBase64"])
      XCTAssertEqual(value["schemaVersion"] as? Int, 2); XCTAssertNil(value["ageYears"])
      XCTAssertEqual(value["practiceContext"] as? [String: String], ["kind": "adult"])
      XCTAssertNotEqual(FeedbackContract.sha(adult), FeedbackContract.sha(child))
      let a = try FeedbackFixture.binding(adult, audio: audio); let b = try FeedbackFixture.binding(child, audio: audio)
      XCTAssertEqual(a["audioSha256"], b["audioSha256"]); XCTAssertEqual(a["promptSha256"], b["promptSha256"])
      XCTAssertThrowsError(try ResearchFeedbackClient.requestBody(attemptId: FeedbackFixture.attempt, audio: audio, prompt: prompt, practiceContext: .child(ageYears: 18)))
    }
    func testOldPolicyAndAllHistoricalWordWrapperPinsRejectedWithoutAdoptingDeclaration() throws {
      let old = [
        "feedbackSourceSha256": "e60137e15cf6efe542456b4232b4e88c975c9fbead459985a0c6eca529ac314c",
        "wrapperSourceSha256": "d05830fe9a0c84ac8c4a1db6f1658bae4fe8f1fde94790636c4466d85dad2b18",
        "feedbackPolicySha256": "6936603a716e4c18bbf96d60c7f6babc906e23d397aff04b0955513618644a3f",
      ]
      var legacy = FeedbackFixture.declaration()
      legacy["feedbackPolicy"] = ["id": "consumer-recording-feedback-v1", "sha256": old["feedbackPolicySha256"]!]
      legacy["feedbackSourceSha256"] = old["feedbackSourceSha256"]!; legacy["wrapperSourceSha256"] = old["wrapperSourceSha256"]!
      XCTAssertThrowsError(try FeedbackDeclaration.decode(FeedbackFixture.json(legacy)))
      for (key, value) in old {
        var changed = FeedbackFixture.declaration()
        if key == "feedbackPolicySha256" { changed["feedbackPolicy"] = ["id": "consumer-recording-feedback-v2", "sha256": value] }
        else { changed[key] = value }
        XCTAssertThrowsError(try FeedbackDeclaration.decode(FeedbackFixture.json(changed)), key)
      }
      var policyOnly = FeedbackFixture.declaration()
      policyOnly["feedbackPolicy"] = ["id": "consumer-recording-feedback-v1", "sha256": FeedbackContract.pins["feedbackPolicySha256"]!]
      XCTAssertThrowsError(try FeedbackDeclaration.decode(FeedbackFixture.json(policyOnly)))
    }
  }
#endif
