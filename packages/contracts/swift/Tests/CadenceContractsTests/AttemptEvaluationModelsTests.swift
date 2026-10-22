import CadenceContracts
import Foundation
import Testing

@Test("A request round-trips through the generated Codable contract")
func requestRoundTrip() throws {
  let request = AttemptEvaluationRequest(
    attemptId: "attempt-swift-001",
    protocolId: .bilabialClosureV1,
    quality: CaptureQuality(
      audioScore: 0.96,
      videoScore: nil,
      reasonCodes: []
    ),
    audio: AudioEvidence(
      pCorrect: 0.93,
      pError: 0.04,
      calibrated: true,
      ambiguous: false,
      likelyError: nil
    ),
    consent: ConsentSnapshot(
      audioProcessing: true,
      videoProcessing: true,
      clinicianReview: true,
      researchUse: false
    )
  )

  let encoded = try JSONEncoder().encode(request)
  let json = try #require(
    JSONSerialization.jsonObject(with: encoded) as? [String: Any]
  )
  let quality = try #require(json["quality"] as? [String: Any])
  let audio = try #require(json["audio"] as? [String: Any])
  let decoded = try JSONDecoder().decode(
    AttemptEvaluationRequest.self,
    from: encoded
  )

  #expect(decoded == request)
  #expect(quality["videoScore"] == nil)
  #expect(audio["likelyError"] == nil)
}

@Test("Generated decision enums decode wire-format values")
func decisionEnumWireValues() throws {
  let data = Data(#""needs-deep-analysis""#.utf8)
  let value = try JSONDecoder().decode(RoutingDecisionKind.self, from: data)

  #expect(value == .needsDeepAnalysis)
}
