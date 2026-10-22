import Accessibility
import SwiftUI

/// The App constructs this host only after launch selection. Generated Sound injects its
/// run-owned resources; inert roots never construct a model or read shared ownership.
struct AudioCleanupRecoveryHost<Content: View>: View {
  @StateObject private var model: AudioCleanupRecoveryModel
  @Environment(\.scenePhase) private var scenePhase
  private let content: Content

  init(
    ownership: AudioHardwareOwnership = .shared,
    files: ProcessAudioFileOwnership = .shared,
    @ViewBuilder content: () -> Content
  ) {
    _model = StateObject(
      wrappedValue: AudioCleanupRecoveryModel(ownership: ownership, files: files))
    self.content = content()
  }

  var body: some View {
    GeometryReader { proxy in
      VStack(spacing: 0) {
        AudioCleanupRecoveryNotice(model: model, maxHeight: proxy.size.height * 0.4)
        content.frame(maxWidth: .infinity, maxHeight: .infinity)
      }
    }
    .environment(\.refreshAudioCleanupRecovery, AudioCleanupRecoveryRefreshAction(model: model))
    .onChange(of: scenePhase) { _, phase in
      if phase == .active { model.refresh() }
    }
  }
}

/// Passive hook for roots: re-reads ownership and never retries. Without a host it does nothing.
struct AudioCleanupRecoveryRefreshAction: Equatable {
  fileprivate let model: AudioCleanupRecoveryModel?

  @MainActor func callAsFunction() { model?.refresh() }

  static func == (lhs: Self, rhs: Self) -> Bool { lhs.model === rhs.model }
}

private struct AudioCleanupRecoveryRefreshKey: EnvironmentKey {
  static var defaultValue: AudioCleanupRecoveryRefreshAction { .init(model: nil) }
}

extension EnvironmentValues {
  var refreshAudioCleanupRecovery: AudioCleanupRecoveryRefreshAction {
    get { self[AudioCleanupRecoveryRefreshKey.self] }
    set { self[AudioCleanupRecoveryRefreshKey.self] = newValue }
  }
}

/// Learner copy derived only from the published snapshot. Identifiers never reach the text.
struct AudioCleanupRecoveryPresentation: Equatable {
  enum Retry: Equatable {
    case available(String)
    case running(String)
    /// Hardware is in ordinary use; guidance replaces a button that could not act.
    case unavailable
  }

  let heading: String
  let detail: String
  let retry: Retry
  let retryHint: String

  /// `retryFailed` is true only while the snapshot still matches the one a failed Retry left.
  init?(snapshot: AudioCleanupRecoveryModel.Snapshot, isRetrying: Bool, retryFailed: Bool) {
    guard snapshot.hasPendingCleanup else { return nil }
    if snapshot.blockedPlaybackOperationID != nil || snapshot.blockedCaptureOperationID != nil
      || snapshot.blockedSpokenWordOperationID != nil
    {
      let source =
        snapshot.blockedPlaybackOperationID != nil
        ? "playback"
        : snapshot.blockedCaptureOperationID != nil ? "recording" : "spoken word"
      heading = "Stopping not confirmed"
      detail =
        retryFailed
        ? "Stopping still isn’t confirmed. Recording and playback stay paused until it is."
        : "Cadence couldn’t confirm the last \(source) stopped. Recording and playback stay paused until it does."
      retry = isRetrying ? .running("Stopping…") : .available("Retry stopping")
      retryHint = "Asks the last \(source) to stop again."
    } else if snapshot.activeHardwareOperationID != nil {
      heading = "Recording cleanup pending"
      detail =
        "A temporary practice recording is waiting to be removed. Cleanup can run after the current recording or playback stops."
      retry = isRetrying ? .running("Removing…") : .unavailable
      retryHint = ""
    } else {
      heading = "Recording cleanup pending"
      detail =
        retryFailed
        ? "The temporary practice recording still hasn’t been removed. You can try again."
        : "A temporary practice recording hasn’t been removed from this device yet."
      retry = isRetrying ? .running("Removing…") : .available("Retry cleanup")
      retryHint = "Tries again to remove the temporary recording."
    }
  }
}

/// Compact notice for ordinary roots. Retry is explicit; the model owns the attempt, so leaving
/// this screen or cancelling a waiter never abandons cleanup.
struct AudioCleanupRecoveryNotice: View {
  @ObservedObject var model: AudioCleanupRecoveryModel
  /// Copy scrolls only when its full height would leave too little space for Home.
  var maxHeight: CGFloat = .infinity
  /// The refreshed snapshot a failed Retry left. Any later change retires the failure copy.
  @State private var failedSnapshot: AudioCleanupRecoveryModel.Snapshot?
  @AccessibilityFocusState private var focus: Focus?

  private enum Focus: Hashable { case detail, retry }

  var body: some View {
    if let presentation {
      AudioCleanupRecoveryHeightCap(maxHeight: maxHeight) {
        ViewThatFits(in: .vertical) {
          VStack(alignment: .leading, spacing: 6) {
            copy(presentation)
            retryButton(presentation)
          }
          VStack(alignment: .leading, spacing: 6) {
            ScrollView {
              VStack(alignment: .leading, spacing: 6) { copy(presentation) }
                .frame(maxWidth: .infinity, alignment: .leading)
            }
            .accessibilityIdentifier("cadence.cleanup-recovery.scroll")
            retryButton(presentation)
          }
        }
        .padding(.horizontal, 24)
        .padding(.top, 12)
        .padding(.bottom, presentation.retry == .unavailable ? 12 : 4)
      }
      .frame(maxWidth: 680, alignment: .leading)
      .frame(maxWidth: .infinity)
      .background(DirectPracticeStyle.canvas.ignoresSafeArea(edges: .top))
      .overlay(alignment: .bottom) { PracticeRule() }
      .foregroundStyle(DirectPracticeStyle.ink)
      .tint(DirectPracticeStyle.ink)
      .accessibilityElement(children: .contain)
      .accessibilityIdentifier("cadence.cleanup-recovery")
    }
  }

  @ViewBuilder
  private func copy(_ presentation: AudioCleanupRecoveryPresentation) -> some View {
    Text(presentation.heading)
      .font(.subheadline.weight(.semibold))
      .fixedSize(horizontal: false, vertical: true)
      .accessibilityAddTraits(.isHeader)
    Text(presentation.detail)
      .font(.subheadline)
      .foregroundStyle(DirectPracticeStyle.muted)
      .fixedSize(horizontal: false, vertical: true)
      .accessibilityFocused($focus, equals: .detail)
  }

  private var presentation: AudioCleanupRecoveryPresentation? {
    AudioCleanupRecoveryPresentation(
      snapshot: model.snapshot, isRetrying: model.isRetrying,
      retryFailed: !model.isRetrying && model.failure != nil
        && failedSnapshot == model.snapshot)
  }

  @ViewBuilder
  private func retryButton(_ presentation: AudioCleanupRecoveryPresentation) -> some View {
    switch presentation.retry {
    case .available(let title), .running(let title):
      let running = presentation.retry == .running(title)
      Button {
        retry()
      } label: {
        HStack(spacing: 8) {
          Text(title)
            .font(.subheadline.weight(.medium))
            .fixedSize(horizontal: false, vertical: true)
          if running {
            ProgressView()
              .controlSize(.small)
              .accessibilityHidden(true)
          }
        }
        .frame(minWidth: 44, minHeight: 44, alignment: .leading)
        .contentShape(Rectangle())
      }
      .buttonStyle(.plain)
      .disabled(running)
      .accessibilityHint(running ? "" : presentation.retryHint)
      .accessibilityIdentifier("cadence.cleanup-recovery.retry")
      .accessibilityFocused($focus, equals: .retry)
    case .unavailable:
      EmptyView()
    }
  }

  private func retry() {
    guard !model.isRetrying, model.snapshot.canRetry else { return }
    let attempt = model.retry()
    Task {
      let recovered = await attempt.value
      // Read the source of truth again; the result alone does not decide what is shown.
      model.refresh()
      guard model.snapshot.hasPendingCleanup else {
        failedSnapshot = nil
        AccessibilityNotification.Announcement(
          recovered ? "Cleanup finished." : "Cleanup is no longer pending."
        ).post()
        return
      }
      let failed = !model.isRetrying && model.failure != nil
      failedSnapshot = failed ? model.snapshot : nil
      guard
        let presentation = AudioCleanupRecoveryPresentation(
          snapshot: model.snapshot, isRetrying: model.isRetrying, retryFailed: failed)
      else { return }
      AccessibilityNotification.Announcement(presentation.detail).post()
      focus = presentation.retry == .unavailable ? .detail : .retry
    }
  }
}

/// Offers a bounded height while adopting the notice's actual height when its copy fits.
private struct AudioCleanupRecoveryHeightCap: Layout {
  var maxHeight: CGFloat

  func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
    subviews.first?.sizeThatFits(capped(proposal)) ?? .zero
  }

  func placeSubviews(
    in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout ()
  ) {
    subviews.first?.place(
      at: bounds.origin, anchor: .topLeading, proposal: capped(ProposedViewSize(bounds.size)))
  }

  private func capped(_ proposal: ProposedViewSize) -> ProposedViewSize {
    let height = min(proposal.height ?? maxHeight, maxHeight)
    return ProposedViewSize(width: proposal.width, height: height.isFinite ? height : nil)
  }
}
