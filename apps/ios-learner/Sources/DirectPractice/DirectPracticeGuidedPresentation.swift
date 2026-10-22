// A value for managed rendering; the coordinator retains media and lifecycle ownership.
import Foundation

@MainActor
struct DirectPracticeGuidedPresentation {
  let stageTitle: String
  let positionLabel: String
  let statusNote: String?
  let firstObservationNote: String?
  let firstCheckStatusNote: String?

  let showsRecordAndCheck: Bool
  let canRecordAndCheck: Bool
  let recordAndCheck: @MainActor () async -> Void

  let showsWordCheck: Bool
  let checkLabel: String?
  let checkProgressNote: String?
  let modelObservationNote: String?
  let canCheckWords: Bool
  let check: @MainActor () async -> Void

  let continueLabel: String
  let canContinue: Bool
  let continueVisit: @MainActor () async -> Void
  let canSkip: Bool
  let skip: @MainActor () async -> Void
  let finishStageLabel: String
  let canFinishStage: Bool
  let finishStage: @MainActor () async -> Void

  // A save retry reuses the same practice completion UUID. Continue changes its
  // label to "Continue without saving" when this is the honest available path.
  let canRetrySave: Bool
  let retrySave: @MainActor () -> Void
}
