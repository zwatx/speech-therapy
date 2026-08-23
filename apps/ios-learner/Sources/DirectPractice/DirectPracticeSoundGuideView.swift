import SwiftUI

/// Static educational content. The parent owns target identity; this view owns only disclosure.
struct DirectPracticeSoundGuideView: View {
  let guide: DirectPracticeSoundGuide
  let showsDetail: Bool
  @State private var expanded = false
  @State private var sourcesExpanded = false
  @Environment(\.dynamicTypeSize) private var dynamicTypeSize

  init(guide: DirectPracticeSoundGuide, showsDetail: Bool = true) {
    self.guide = guide
    self.showsDetail = showsDetail
  }

  var body: some View {
    VStack(alignment: .leading, spacing: 0) {
      Button {
        expanded.toggle()
        if !expanded { sourcesExpanded = false }
      } label: {
        HStack(spacing: 12) {
          Text("About this sound")
            .font(.body)
            .fixedSize(horizontal: false, vertical: true)
          Spacer(minLength: 0)
          Image(systemName: expanded ? "chevron.down" : "chevron.right")
            .font(.subheadline.weight(.semibold))
            .accessibilityHidden(true)
        }
        .frame(maxWidth: .infinity, minHeight: 48, alignment: .leading)
        .contentShape(Rectangle())
      }
      .buttonStyle(.plain)
      .accessibilityValue(expanded ? "Expanded" : "Collapsed")
      .accessibilityIdentifier("cadence.sound-guide.toggle")

      if expanded {
        expandedContent
      }
    }
    .foregroundStyle(DirectPracticeStyle.ink)
    .tint(DirectPracticeStyle.ink)
  }

  private var expandedContent: some View {
    VStack(alignment: .leading, spacing: 20) {
      Text(guide.title)
        .font(.body.weight(.medium))
        .accessibilityAddTraits(.isHeader)
        .accessibilityIdentifier("cadence.sound-guide.title")
      if showsDetail {
        Text(guide.detail)
          .font(.body)
          .accessibilityIdentifier("cadence.sound-guide.detail")
      }
      switch guide.kind {
      case .b:
        illustrations
      case .p, .m, .t, .d:
        EmptyView()
      case .r, .br:
        rGuidance
      }
      Text("A general guide to this sound.")
        .font(.subheadline)
        .foregroundStyle(DirectPracticeStyle.muted)
      sources
    }
    .fixedSize(horizontal: false, vertical: true)
    .padding(.top, 12)
    .padding(.bottom, 8)
  }

  private var rGuidance: some View {
    VStack(alignment: .leading, spacing: 20) {
      VStack(alignment: .leading, spacing: 8) {
        Text("One way to try R")
          .font(.body.weight(.medium))
          .accessibilityAddTraits(.isHeader)
          .accessibilityIdentifier("cadence.sound-guide.r-option-title")
        Text("Try drawing your tongue back and up, with its sides touching the inside of your upper back teeth. Say “\(guide.word)” with your usual voice.")
          .font(.body)
          .accessibilityIdentifier("cadence.sound-guide.r-option-detail")
      }
      VStack(alignment: .leading, spacing: 8) {
        Text("More than one way")
          .font(.body.weight(.medium))
          .accessibilityAddTraits(.isHeader)
          .accessibilityIdentifier("cadence.sound-guide.r-variation-title")
        Text("Some people make R with the tongue tip curled back. Others do not. You do not have to force a curl. Keep practice relaxed.")
          .font(.body)
          .accessibilityIdentifier("cadence.sound-guide.r-variation-detail")
      }
      Text("US English word list. R varies across English accents.")
        .font(.subheadline)
        .foregroundStyle(DirectPracticeStyle.muted)
        .accessibilityIdentifier("cadence.sound-guide.r-accent")
    }
    .fixedSize(horizontal: false, vertical: true)
  }

  private var illustrations: some View {
    let layout = dynamicTypeSize.isAccessibilitySize
      ? AnyLayout(VStackLayout(alignment: .leading, spacing: 24))
      : AnyLayout(HStackLayout(alignment: .top, spacing: 20))
    return layout {
      illustration(open: false, caption: "1. Lips together", identifier: "closed-caption")
      illustration(open: true, caption: "2. Lips open", identifier: "open-caption")
    }
  }

  private func illustration(open: Bool, caption: String, identifier: String) -> some View {
    VStack(alignment: .leading, spacing: 10) {
      SoundGuideLips(open: open)
        .stroke(DirectPracticeStyle.ink, style: StrokeStyle(lineWidth: 2, lineCap: .round, lineJoin: .round))
        .aspectRatio(2, contentMode: .fit)
        .frame(maxWidth: 200)
        .frame(maxWidth: .infinity)
        .accessibilityHidden(true)
      Text(caption)
        .font(.subheadline)
        .fixedSize(horizontal: false, vertical: true)
        .accessibilityIdentifier("cadence.sound-guide.\(identifier)")
    }
    .frame(maxWidth: .infinity, alignment: .leading)
  }

  private var sources: some View {
    VStack(alignment: .leading, spacing: 0) {
      Button {
        sourcesExpanded.toggle()
      } label: {
        HStack(spacing: 12) {
          Text("Sources")
            .font(.subheadline)
            .fixedSize(horizontal: false, vertical: true)
          Spacer(minLength: 0)
          Image(systemName: sourcesExpanded ? "chevron.down" : "chevron.right")
            .font(.subheadline.weight(.semibold))
            .accessibilityHidden(true)
        }
        .frame(maxWidth: .infinity, minHeight: 44, alignment: .leading)
        .contentShape(Rectangle())
      }
      .buttonStyle(.plain)
      .accessibilityValue(sourcesExpanded ? "Expanded" : "Collapsed")
      .accessibilityIdentifier("cadence.sound-guide.sources")

      if sourcesExpanded {
        VStack(alignment: .leading, spacing: 12) {
          switch guide.kind {
          case .b, .p, .m, .t, .d:
            Text("Guide text adapted from Essentials of Linguistics, §2.6 Classifying Consonants, © 2018 Catherine Anderson. Shortened and reworded for this guide.")
              .accessibilityIdentifier("cadence.sound-guide.source-attribution")
            Text(guide.kind == .b
              ? "Guide text is licensed under CC BY-SA 4.0. This license applies to the guide text, not the app. Original diagram created for this guide."
              : "Guide text is licensed under CC BY-SA 4.0. This license applies to the guide text, not the app.")
              .accessibilityIdentifier("cadence.sound-guide.source-license")
            Link(destination: URL(string:
              "https://pressbooks.pub/essentialsoflinguistics/chapter/2-7-classifying-consonants/")!) {
              Text("Read the source chapter")
                .frame(minHeight: 44, alignment: .leading)
                .contentShape(Rectangle())
            }
            .accessibilityIdentifier("cadence.sound-guide.source-chapter")
            Link(destination: URL(string:
              "https://creativecommons.org/licenses/by-sa/4.0/")!) {
              Text("CC BY-SA 4.0 license")
                .frame(minHeight: 44, alignment: .leading)
                .contentShape(Rectangle())
            }
            .accessibilityIdentifier("cadence.sound-guide.source-license-link")
          case .r, .br:
            Text("General sound information: Alberta Health Services, “Speech sound activities: R sound.” Guide wording written for this app; no source images, audio or video are included.")
            Link(destination: URL(string:
              "https://myhealth.alberta.ca/health/Pages/5-speech-sound-activities-R-sound.aspx")!) {
              Text("Read the R sound guide")
                .frame(minHeight: 44, alignment: .leading)
                .contentShape(Rectangle())
            }
          }
        }
        .font(.subheadline)
        .fixedSize(horizontal: false, vertical: true)
        .padding(.vertical, 8)
      }
    }
  }
}

/// Original schematic front-view paths; no third-party image or camera geometry.
private struct SoundGuideLips: Shape {
  let open: Bool

  func path(in rect: CGRect) -> Path {
    func point(_ x: CGFloat, _ y: CGFloat) -> CGPoint {
      CGPoint(x: rect.minX + rect.width * x, y: rect.minY + rect.height * y)
    }
    var path = Path()
    path.move(to: point(0.08, 0.5))
    path.addCurve(to: point(0.5, 0.31), control1: point(0.25, 0.46), control2: point(0.34, 0.15))
    path.addCurve(to: point(0.92, 0.5), control1: point(0.66, 0.15), control2: point(0.75, 0.46))
    path.addCurve(to: point(0.08, 0.5), control1: point(0.72, 0.86), control2: point(0.28, 0.86))
    path.closeSubpath()
    if open {
      path.addEllipse(in: CGRect(
        x: rect.minX + rect.width * 0.24, y: rect.minY + rect.height * 0.44,
        width: rect.width * 0.52, height: rect.height * 0.16))
    } else {
      path.move(to: point(0.08, 0.5))
      path.addQuadCurve(to: point(0.92, 0.5), control: point(0.5, 0.56))
    }
    return path
  }
}
