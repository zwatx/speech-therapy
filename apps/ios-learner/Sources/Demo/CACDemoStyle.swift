import SwiftUI
import UIKit

/// Visual tokens for the sound-check journey. They follow the app's "paper" direction
/// (DirectPracticeStyle): warm paper, near-black ink, one tomato accent for the target sound
/// and recording. Outcome colors stay distinct from the accent.
enum CACDemoStyle {
  static let background = DirectPracticeStyle.canvas
  static let surface = adaptive(0xFFFCF6, dark: 0x1F1C18)
  static let separator = DirectPracticeStyle.border
  static let ink = DirectPracticeStyle.ink
  static let muted = DirectPracticeStyle.muted
  static let accent = DirectPracticeStyle.accent
  static let onAccent = DirectPracticeStyle.onAccent
  static let accentSoft = adaptive(0xFBEDE5, dark: 0x3A2118)
  static let recording = DirectPracticeStyle.accent
  static let cornerRadius: CGFloat = 18
  static let maxWidth: CGFloat = 560

  static func tint(_ outcome: CACScriptedOutcome) -> Color {
    switch outcome {
    case .clear: adaptive(0x2E7A4C, dark: 0x6FCF97)
    case .needsPractice: adaptive(0x8F6200, dark: 0xE8B64C)
    }
  }

  static func soft(_ outcome: CACScriptedOutcome) -> Color {
    switch outcome {
    case .clear: adaptive(0xE6F0E4, dark: 0x18291D)
    case .needsPractice: adaptive(0xF5EBD3, dark: 0x332A14)
    }
  }

  static func icon(_ outcome: CACScriptedOutcome) -> String {
    switch outcome {
    case .clear: "checkmark.circle.fill"
    case .needsPractice: "arrow.triangle.2.circlepath.circle.fill"
    }
  }

  static func label(_ outcome: CACScriptedOutcome) -> String {
    switch outcome {
    case .clear: "Clear"
    case .needsPractice: "Needs practice"
    }
  }

  /// One symbol per step of sound check → practice → check again.
  static func icon(_ part: CACJourneyPart) -> String {
    switch part {
    case .soundCheck: "waveform"
    case .practice: "repeat"
    case .recheck: "checkmark.circle"
    }
  }

  /// The word's library picture. Library placeholders carry no meaning for the word,
  /// so they are not shown; callers fall back to the sound's letter.
  static func picture(_ word: CACScriptedWord) -> String? { picture(word.prompt) }

  static func picture(_ prompt: PracticePrompt) -> String? {
    ["text.bubble.fill", "circle"].contains(prompt.systemImage) ? nil : prompt.systemImage
  }

  private static func adaptive(_ light: UInt32, dark: UInt32) -> Color {
    func color(_ hex: UInt32) -> UIColor {
      UIColor(
        red: CGFloat((hex >> 16) & 0xFF) / 255, green: CGFloat((hex >> 8) & 0xFF) / 255,
        blue: CGFloat(hex & 0xFF) / 255, alpha: 1)
    }
    return Color(
      uiColor: UIColor { $0.userInterfaceStyle == .dark ? color(dark) : color(light) })
  }
}

extension View {
  /// Paper card: a lighter sheet with a hairline edge. Tinted fills drop the edge.
  func cacSurface(_ fill: Color = CACDemoStyle.surface, edge: Bool = true) -> some View {
    let shape = RoundedRectangle(cornerRadius: CACDemoStyle.cornerRadius, style: .continuous)
    return background(fill, in: shape)
      .overlay(shape.strokeBorder(CACDemoStyle.separator.opacity(edge ? 1 : 0)))
  }
}

/// Full-width ink action; at most one per state. An optional trailing symbol marks a step
/// forward, as on the home screen.
struct CACPrimaryButtonStyle: ButtonStyle {
  var icon: String? = nil
  @Environment(\.isEnabled) private var isEnabled

  func makeBody(configuration: Configuration) -> some View {
    let shape = RoundedRectangle(cornerRadius: 14, style: .continuous)
    return HStack(spacing: 12) {
      configuration.label
        .multilineTextAlignment(icon == nil ? .center : .leading)
        .frame(maxWidth: .infinity, alignment: icon == nil ? .center : .leading)
      if let icon {
        Image(systemName: icon).accessibilityHidden(true)
      }
    }
    .font(.body.weight(.semibold))
    .padding(.horizontal, 20)
    .padding(.vertical, 12)
    .frame(maxWidth: .infinity, minHeight: 54)
    .foregroundStyle(isEnabled ? CACDemoStyle.background : CACDemoStyle.muted)
    .background(isEnabled ? CACDemoStyle.ink : CACDemoStyle.separator, in: shape)
    .opacity(configuration.isPressed ? 0.75 : 1)
    .contentShape(shape)
  }
}

/// Quiet text action beside a primary.
struct CACSecondaryButtonStyle: ButtonStyle {
  @Environment(\.isEnabled) private var isEnabled

  func makeBody(configuration: Configuration) -> some View {
    configuration.label
      .font(.body.weight(.medium))
      .multilineTextAlignment(.center)
      .frame(maxWidth: .infinity, minHeight: 48)
      .foregroundStyle(CACDemoStyle.ink)
      .opacity(isEnabled ? (configuration.isPressed ? 0.6 : 1) : 0.4)
      .contentShape(Rectangle())
  }
}

/// Compact capsule for in-content controls such as Play and Hear it.
struct CACCapsuleButtonStyle: ButtonStyle {
  @Environment(\.isEnabled) private var isEnabled

  func makeBody(configuration: Configuration) -> some View {
    configuration.label
      .font(.subheadline.weight(.semibold))
      .padding(.horizontal, 16)
      .frame(minHeight: 44)
      .foregroundStyle(CACDemoStyle.accent)
      .background(CACDemoStyle.accentSoft, in: Capsule())
      .opacity(isEnabled ? (configuration.isPressed ? 0.7 : 1) : 0.45)
      .contentShape(Capsule())
  }
}

/// Large round microphone / stop control. Callers set the accessibility label.
struct CACRecordButtonStyle: ButtonStyle {
  let recording: Bool

  func makeBody(configuration: Configuration) -> some View {
    CACRecordGlyph(recording: recording, pressed: configuration.isPressed)
  }
}

private struct CACRecordGlyph: View {
  let recording: Bool
  let pressed: Bool
  @Environment(\.isEnabled) private var isEnabled
  @Environment(\.accessibilityReduceMotion) private var reduceMotion
  @ScaledMetric(relativeTo: .largeTitle) private var scaledSize = 68

  /// Grows with text a little, but never crowds the word and camera.
  private var size: CGFloat { min(scaledSize, 96) }

  var body: some View {
    Image(systemName: recording ? "stop.fill" : "mic.fill")
      .font(.system(size: size * 0.36, weight: .semibold))
      .foregroundStyle(CACDemoStyle.onAccent)
      .frame(width: size, height: size)
      .background(Circle().fill(CACDemoStyle.recording))
      .padding(6)
      .background(Circle().fill(CACDemoStyle.recording.opacity(recording ? 0.22 : 0.12)))
      .opacity(isEnabled ? 1 : 0.4)
      .scaleEffect(pressed && !reduceMotion ? 0.95 : 1)
      .contentShape(Circle())
  }
}
