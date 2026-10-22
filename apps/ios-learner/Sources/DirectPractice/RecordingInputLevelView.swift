import Foundation
import SwiftUI

/// Display-only amplitude from the current recorder; no voice or correctness thresholds.
struct RecordingInputLevelView: View {
  let power: Float?

  private var finitePower: Float? {
    guard let power, power.isFinite else { return nil }
    return power
  }

  private var amplitude: Double {
    guard let finitePower else { return 0 }
    return pow(10, Double(min(0, finitePower)) / 20)
  }

  private var value: String {
    guard let finitePower else { return "Unavailable" }
    return "\(finitePower.formatted(.number.precision(.fractionLength(0)))) dB"
  }

  private var spokenValue: String {
    guard let finitePower else { return "Unavailable" }
    return "\(finitePower.formatted(.number.precision(.fractionLength(0)))) decibels"
  }

  var body: some View {
    VStack(alignment: .leading, spacing: 10) {
      Text("Microphone input")
        .font(.subheadline.weight(.medium))
        .fixedSize(horizontal: false, vertical: true)
      GeometryReader { geometry in
        ZStack(alignment: .leading) {
          Capsule().fill(DirectPracticeStyle.border)
          Capsule().fill(DirectPracticeStyle.ink)
            .frame(width: geometry.size.width * amplitude)
        }
      }
      .frame(height: 8)
      // Reserve the same natural text height for every reading, including unavailable.
      ZStack(alignment: .leading) {
        Text("Unavailable").hidden()
        Text(value)
      }
      .font(.caption.monospacedDigit())
      .foregroundStyle(DirectPracticeStyle.muted)
      .fixedSize(horizontal: false, vertical: true)
    }
    .frame(maxWidth: .infinity, alignment: .leading)
    .accessibilityElement(children: .ignore)
    .accessibilityLabel("Microphone input")
    .accessibilityValue(spokenValue)
    .accessibilityIdentifier("cadence.recording-input")
  }
}
