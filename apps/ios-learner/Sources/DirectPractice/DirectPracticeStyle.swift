import SwiftUI
import UIKit

/// "Paper" direction: warm paper, near-black ink, one tomato accent reserved for the
/// target sound and recording. Colors adapt to light and dark appearances.
enum DirectPracticeStyle {
  static let ink = adaptive(0x1C1A16, dark: 0xF3EEE4)
  static let muted = adaptive(0x6B6459, dark: 0xA79F92)
  static let canvas = adaptive(0xF6F2EA, dark: 0x14120F)
  static let border = adaptive(0xE2DBCE, dark: 0x2E2A24)
  static let accent = adaptive(0xBC4219, dark: 0xF07A52)
  /// Glyphs drawn on an accent fill.
  static let onAccent = adaptive(0xFFFFFF, dark: 0x14120F)
  static let cornerRadius: CGFloat = 14

  private static func adaptive(_ light: UInt32, dark: UInt32) -> Color {
    Color(
      uiColor: UIColor { traits in
        let hex = traits.userInterfaceStyle == .dark ? dark : light
        return UIColor(
          red: CGFloat((hex >> 16) & 255) / 255,
          green: CGFloat((hex >> 8) & 255) / 255,
          blue: CGFloat(hex & 255) / 255,
          alpha: 1
        )
      })
  }
}

struct DirectPracticeButtonStyle: ButtonStyle {
  var secondary = false
  @Environment(\.isEnabled) private var isEnabled

  func makeBody(configuration: Configuration) -> some View {
    let shape = RoundedRectangle(cornerRadius: DirectPracticeStyle.cornerRadius, style: .continuous)
    return configuration.label
      .font(.body.weight(.medium))
      .multilineTextAlignment(.center)
      .padding(.horizontal, 20)
      .padding(.vertical, 16)
      .frame(maxWidth: .infinity, minHeight: 56)
      .foregroundStyle(secondary ? DirectPracticeStyle.ink : DirectPracticeStyle.canvas)
      .background(secondary ? Color.clear : DirectPracticeStyle.ink, in: shape)
      .overlay {
        if secondary { shape.strokeBorder(DirectPracticeStyle.border) }
      }
      .contentShape(shape)
      .opacity(isEnabled ? (configuration.isPressed ? 0.65 : 1) : 0.45)
  }
}

/// The large round record/stop control. The circle keeps a fixed visual size while the
/// caption beneath it (the button's label) scales with Dynamic Type.
struct PracticeRecordControlStyle: ButtonStyle {
  var recording = false
  @Environment(\.isEnabled) private var isEnabled
  @Environment(\.accessibilityReduceMotion) private var reduceMotion
  private let diameter: CGFloat = 88

  func makeBody(configuration: Configuration) -> some View {
    VStack(spacing: 14) {
      ZStack {
        Circle()
          .fill(DirectPracticeStyle.accent.opacity(0.14))
          .frame(width: diameter + 18, height: diameter + 18)
        Circle()
          .fill(DirectPracticeStyle.accent)
          .frame(width: diameter, height: diameter)
        if recording {
          RoundedRectangle(cornerRadius: 6, style: .continuous)
            .fill(DirectPracticeStyle.onAccent)
            .frame(width: diameter * 0.3, height: diameter * 0.3)
        } else {
          Circle()
            .fill(DirectPracticeStyle.onAccent)
            .frame(width: diameter * 0.32, height: diameter * 0.32)
        }
      }
      .scaleEffect(configuration.isPressed && !reduceMotion ? 0.94 : 1)
      .animation(reduceMotion ? nil : .easeOut(duration: 0.12), value: configuration.isPressed)
      configuration.label
        .font(.subheadline.weight(.medium))
        .foregroundStyle(DirectPracticeStyle.ink)
        .multilineTextAlignment(.center)
        .fixedSize(horizontal: false, vertical: true)
    }
    .frame(maxWidth: .infinity, minHeight: 44)
    .contentShape(Rectangle())
    .opacity(isEnabled ? 1 : 0.4)
  }
}

/// A low-emphasis action: plain text with a full-width 48-point hit area.
struct PracticeTextButtonStyle: ButtonStyle {
  @Environment(\.isEnabled) private var isEnabled

  func makeBody(configuration: Configuration) -> some View {
    configuration.label
      .font(.body)
      .underline(configuration.isPressed)
      .multilineTextAlignment(.center)
      .foregroundStyle(DirectPracticeStyle.ink)
      .frame(maxWidth: .infinity, minHeight: 48)
      .contentShape(Rectangle())
      .opacity(isEnabled ? (configuration.isPressed ? 0.65 : 1) : 0.45)
  }
}

struct PracticeRule: View {
  var body: some View {
    Rectangle()
      .fill(DirectPracticeStyle.border)
      .frame(height: 1)
      .accessibilityHidden(true)
  }
}

/// "/r/ at the start" with the sound in the accent color.
func practicePositionText(symbol: String, position: PracticeTargetPosition) -> Text {
  let place: String =
    switch position {
    case .middle: " in the middle"
    default: " at the \(position.rawValue)"
    }
  return Text("/\(symbol)/").foregroundColor(DirectPracticeStyle.accent).fontWeight(.semibold)
    + Text(place)
}
