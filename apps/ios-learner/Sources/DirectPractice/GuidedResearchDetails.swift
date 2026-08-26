#if DEBUG && targetEnvironment(simulator)
  import Foundation
  import SwiftUI

  /// Ephemeral presentation of admitted research output, never a learner finding.
  struct GuidedResearchDetailsPresentation: Identifiable, Equatable {
    struct ID: Hashable {
      let workflowID: UUID
      let entryID: String
    }
    struct Snapshot: Equatable {
      let identity: LocalGuidedCheckIdentity
      let result: ResearchAssessmentResult
    }
    enum Side: Equatable {
      case available(Snapshot)
      case unavailable(String)

      @MainActor
      static func resolve(
        row: LocalGuidedReviewRow?, workflowID: UUID, roundID: UUID?,
        entry: PracticeLibraryEntry, ageYears: Int,
        observations: [UUID: GuidedResearchModelObservation]
      ) -> Self {
        guard let row else { return .unavailable("No recheck result yet.") }
        guard row.entry == entry, row.state == .finished(.matched) else {
          return .unavailable("No eligible completed word check for this review.")
        }
        guard let visit = row.visit, let identity = row.firstSubmission,
          visit == identity.visit, visit.workflowID == workflowID,
          visit.roundID == roundID, visit.entryID == entry.id
        else { return .unavailable("The review’s take binding is unavailable.") }
        guard let observation = observations[identity.operationID],
          observation.request.operationID == identity.operationID,
          observation.request.tryID == identity.tryID,
          observation.entryID == entry.id,
          observation.request.expectedWord == entry.prompt.word
        else { return .unavailable("No research output bound to this review’s take.") }
        guard case .processedUnverified(let milliseconds) = observation.outcome,
          let result = observation.researchResult
        else { return .unavailable("No retained research distribution. " + observation.note) }
        guard result.context.operationID == identity.operationID,
          result.context.entryID == entry.id, result.context.ageYears == ageYears,
          (6...12).contains(ageYears), milliseconds == result.timingMilliseconds.total,
          let prompt = try? ResearchAssessmentClient.prompt(for: entry),
          result.isBound(to: result.context, prompt: prompt)
        else { return .unavailable("The retained research output does not match this review’s context.") }
        // The recognizer independently admitted request/audio hashes before retention.
        // This rechecks context and target geometry; it does not re-prove those hashes
        // against the result's own context or reopen a cleaned-up recording.
        return .available(.init(identity: identity, result: result))
      }
    }
    let id: ID
    let word: String
    let initial: Side
    let recheck: Side

    var contractsDiffer: Bool {
      guard case .available(let first) = initial, case .available(let next) = recheck else {
        return false
      }
      let a = first.result, b = next.result
      return a.model != b.model || a.context.ageYears != b.context.ageYears
        || a.targets.count != b.targets.count
        || !zip(a.targets, b.targets).allSatisfy { left, right in
          left.id == right.id && left.wordIndex == right.wordIndex
            && left.phoneIndex == right.phoneIndex && left.targetPhone == right.targetPhone
        }
    }
  }

  struct GuidedResearchDetailsSheet: View {
    let details: GuidedResearchDetailsPresentation
    @Environment(\.dismiss) private var dismiss

    var body: some View {
      ScrollView {
        VStack(alignment: .leading, spacing: 24) {
          Text("Research model details").font(.title.weight(.semibold))
            .accessibilityAddTraits(.isHeader)
            .accessibilityIdentifier("guided-research-details-title")
          Text("Internal research output. Not validated pronunciation feedback.")
            .font(.body).foregroundStyle(DirectPracticeStyle.muted)
            .accessibilityIdentifier("guided-research-details-disclaimer")
          Text(details.word).font(.title2.weight(.semibold))
          Text("These probabilities are model estimates of subjective corpus ratings.")
            .font(.body)
          if details.contractsDiffer {
            Text("The model, targets or declared age differ. These reviews are not a comparable pair.")
              .font(.body)
              .accessibilityIdentifier("guided-research-details-not-comparable")
          }
          side("First review", key: "first-review", details.initial)
          side("Recheck", key: "recheck", details.recheck)
        }
        .padding(24)
        .frame(maxWidth: .infinity, alignment: .leading)
      }
      .accessibilityIdentifier("guided-research-details-scroll")
      .background(DirectPracticeStyle.canvas)
      .foregroundStyle(DirectPracticeStyle.ink)
      .safeAreaInset(edge: .top, spacing: 0) {
        VStack(spacing: 0) {
          Button { dismiss() } label: {
            Text("Close")
              .font(.subheadline)
              .frame(maxWidth: .infinity, minHeight: 44, alignment: .leading)
              .contentShape(Rectangle())
          }
            .buttonStyle(.plain)
            .accessibilityIdentifier("guided-research-details-close")
          PracticeRule()
        }
        .padding(.horizontal, 24)
        .background(DirectPracticeStyle.canvas)
      }
    }

    @ViewBuilder
    private func side(_ title: String, key: String, _ value: GuidedResearchDetailsPresentation.Side) -> some View {
      VStack(alignment: .leading, spacing: 16) {
        Text(title).font(.title2.weight(.semibold)).accessibilityAddTraits(.isHeader)
          .accessibilityIdentifier("guided-research-details-\(key)")
        switch value {
        case .unavailable(let reason):
          Text(reason).font(.body).foregroundStyle(DirectPracticeStyle.muted)
            .accessibilityIdentifier("guided-research-details-\(key)-unavailable")
        case .available(let snapshot):
          ForEach(snapshot.result.targets, id: \.id) { target in
            VStack(alignment: .leading, spacing: 8) {
              Text("Target /\(target.targetPhone)/ · word \(target.wordIndex + 1), phone \(target.phoneIndex + 1)")
                .font(.headline)
                .accessibilityIdentifier("guided-research-details-\(key)-target-\(target.id)")
              ForEach(0..<3) { rating in
                Text("Corpus rating \(rating) probability: \(target.subjectiveCorpusRatingProbabilities[rating].formatted(.number.precision(.fractionLength(6))))")
                  .font(.body).monospacedDigit()
                  .accessibilityIdentifier("guided-research-details-\(key)-target-\(target.id)-rating-\(rating)")
              }
            }
          }
          DisclosureGroup("Research provenance") {
            VStack(alignment: .leading, spacing: 8) {
              Text("Model: \(snapshot.result.model.id)")
              Text("Manifest: \(snapshot.result.model.manifestSha256)")
              Text("Declared age: \(snapshot.result.context.ageYears) years")
              Text("Operation: \(snapshot.identity.operationID.uuidString)")
              Text("Take: \(snapshot.identity.tryID.uuidString)")
              Text("Visit: \(snapshot.identity.visit.visitID.uuidString)")
            }
            .font(.body).foregroundStyle(DirectPracticeStyle.muted)
            .padding(.top, 8)
          }
        }
      }
      .fixedSize(horizontal: false, vertical: true)
    }
  }
#endif
