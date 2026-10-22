import SwiftUI
import UIKit

enum DirectPracticeStyle {
  static let ink = adaptive(0x141414, dark: 0xF5F5F5)
  static let muted = adaptive(0x606060, dark: 0xABABAB)
  static let canvas = adaptive(0xFFFFFF, dark: 0x0B0B0B)
  static let border = adaptive(0xDEDEDE, dark: 0x323232)

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
    configuration.label
      .font(.body.weight(.medium))
      .multilineTextAlignment(.center)
      .padding(.horizontal, 20)
      .padding(.vertical, 16)
      .frame(maxWidth: .infinity, minHeight: 56)
      .foregroundStyle(secondary ? DirectPracticeStyle.ink : DirectPracticeStyle.canvas)
      .background(secondary ? Color.clear : DirectPracticeStyle.ink)
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
