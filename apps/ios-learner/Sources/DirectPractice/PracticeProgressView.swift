import SwiftUI

/// Effort over the last week and per sound, from saved participation metadata only.
/// It counts practice; it never implies pronunciation accuracy or improvement.
struct PracticeProgressView: View {
  @ObservedObject var history: PracticeParticipationStore
  let allowsLiveRoutes: Bool
  var now: Date = .now
  @ScaledMetric(relativeTo: .largeTitle) private var titleSize = 40

  var body: some View {
    let week = PracticeWeek(entries: history.entries, endingOn: now)
    ScrollView {
      VStack(alignment: .leading, spacing: 0) {
        Text("Progress")
          .font(.subheadline)
          .foregroundStyle(DirectPracticeStyle.muted)
          .frame(minHeight: 44, alignment: .leading)
        PracticeRule()

        Text(week.headline)
          .font(.system(size: titleSize, weight: .regular, design: .serif))
          .tracking(-1.2)
          .fixedSize(horizontal: false, vertical: true)
          .accessibilityAddTraits(.isHeader)
          .accessibilityIdentifier("cadence.progress.headline")
          .padding(.top, 28)
        Text(week.detail)
          .font(.body)
          .foregroundStyle(DirectPracticeStyle.muted)
          .fixedSize(horizontal: false, vertical: true)
          .padding(.top, 10)

        if week.activeDays > 0 {
          PracticeWeekChart(week: week)
            .padding(.top, 28)
        }

        if history.loadError != nil {
          Text("Saved practice history could not be read. Clear it from Today to start again.")
            .fixedSize(horizontal: false, vertical: true)
            .padding(.top, 32)
            .accessibilityIdentifier("cadence.progress.load-error")
        } else if !history.entries.isEmpty {
          Text("By sound")
            .font(.title3.weight(.medium))
            .accessibilityAddTraits(.isHeader)
            .padding(.top, 40)
            .padding(.bottom, 14)
          PracticeRule()
          ForEach(PracticeSoundTally.from(history.entries)) { tally in
            soundRow(tally)
            PracticeRule()
          }
          NavigationLink {
            if allowsLiveRoutes {
              PracticeParticipationHistoryView(history: history, allowsLiveRoutes: allowsLiveRoutes)
            } else {
              Color.clear
            }
          } label: {
            HStack {
              Text("All practice sessions (\(history.entries.count))")
              Spacer()
              Image(systemName: "chevron.right").font(.footnote)
                .foregroundStyle(DirectPracticeStyle.muted).accessibilityHidden(true)
            }
            .font(.body)
            .frame(maxWidth: .infinity, minHeight: 52, alignment: .leading)
            .contentShape(Rectangle())
          }
          .buttonStyle(.plain)
          .accessibilityIdentifier("cadence.progress.all")
          .disabled(!allowsLiveRoutes)
        }

        Text("Progress counts the practice you do. It doesn’t measure pronunciation.")
          .font(.footnote)
          .foregroundStyle(DirectPracticeStyle.muted)
          .fixedSize(horizontal: false, vertical: true)
          .padding(.vertical, 28)
      }
      .padding(.horizontal, 24)
      .padding(.top, 8)
      .frame(maxWidth: 680)
      .frame(maxWidth: .infinity)
    }
    .background(DirectPracticeStyle.canvas.ignoresSafeArea())
    .foregroundStyle(DirectPracticeStyle.ink)
    .tint(DirectPracticeStyle.ink)
    .toolbar(.hidden, for: .navigationBar)
  }

  private func soundRow(_ tally: PracticeSoundTally) -> some View {
    let sound = PracticeLibrary.sounds.first { $0.id == tally.soundID }
    return NavigationLink {
      if allowsLiveRoutes, let sound {
        PracticeSoundLibraryView(sound: sound, history: history)
      } else {
        Color.clear
      }
    } label: {
      HStack(alignment: .center, spacing: 18) {
        Text(sound?.symbol ?? tally.soundID)
          .font(.system(.title2, design: .serif))
          .frame(width: 36, alignment: .leading)
          .accessibilityHidden(true)
        VStack(alignment: .leading, spacing: 4) {
          Text((sound?.name ?? tally.soundID).lowercased())
            .font(.body.weight(.medium))
          Text(tally.summary)
            .font(.subheadline)
            .foregroundStyle(DirectPracticeStyle.muted)
        }
        .fixedSize(horizontal: false, vertical: true)
        Spacer(minLength: 4)
        Image(systemName: "chevron.right").font(.footnote)
          .foregroundStyle(DirectPracticeStyle.muted).accessibilityHidden(true)
      }
      .frame(maxWidth: .infinity, minHeight: 68, alignment: .leading)
      .contentShape(Rectangle())
      .accessibilityElement(children: .ignore)
      .accessibilityLabel("\(sound?.name ?? tally.soundID), \(tally.summary)")
    }
    .buttonStyle(.plain)
    .accessibilityHint("Opens words for this sound")
    .accessibilityIdentifier("cadence.progress.sound.\(tally.soundID)")
    .disabled(!allowsLiveRoutes || sound == nil)
  }
}

/// Words practiced per calendar day for the seven days ending today.
struct PracticeWeek: Equatable {
  struct Day: Equatable, Identifiable {
    let date: Date
    let words: Int
    var id: Date { date }
  }

  let days: [Day]

  init(entries: [PracticeParticipation], endingOn now: Date, calendar: Calendar = .current) {
    let today = calendar.startOfDay(for: now)
    days = (0..<7).reversed().compactMap { offset in
      guard let day = calendar.date(byAdding: .day, value: -offset, to: today) else { return nil }
      let words = entries
        .filter { calendar.isDate($0.completedAt, inSameDayAs: day) }
        .reduce(0) { $0 + $1.wordCount }
      return Day(date: day, words: words)
    }
  }

  var activeDays: Int { days.filter { $0.words > 0 }.count }
  var totalWords: Int { days.reduce(0) { $0 + $1.words } }

  var headline: String {
    switch activeDays {
    case 0: "No practice yet this week."
    case 1: "1 day this week."
    default: "\(activeDays) days this week."
    }
  }

  var detail: String {
    activeDays == 0
      ? "Start from Today or pick a sound. A few words a day is plenty."
      : "\(totalWords) \(totalWords == 1 ? "word" : "words") practiced in the last seven days."
  }
}

private struct PracticeWeekChart: View {
  let week: PracticeWeek
  private let height: CGFloat = 120

  var body: some View {
    let peak = max(week.days.map(\.words).max() ?? 0, 1)
    VStack(spacing: 8) {
      HStack(alignment: .bottom, spacing: 10) {
        ForEach(Array(week.days.enumerated()), id: \.element.id) { index, day in
          let isToday = index == week.days.count - 1
          RoundedRectangle(cornerRadius: 4, style: .continuous)
            .fill(isToday ? DirectPracticeStyle.accent : DirectPracticeStyle.ink)
            .frame(height: day.words == 0 ? 2 : max(6, height * CGFloat(day.words) / CGFloat(peak)))
            .opacity(day.words == 0 ? 0.25 : 1)
            .frame(maxWidth: .infinity, maxHeight: height, alignment: .bottom)
        }
      }
      .frame(height: height)
      PracticeRule()
      HStack(spacing: 10) {
        ForEach(week.days) { day in
          Text(day.date, format: .dateTime.weekday(.narrow))
            .font(.caption)
            .foregroundStyle(DirectPracticeStyle.muted)
            .frame(maxWidth: .infinity)
        }
      }
    }
    .accessibilityElement(children: .ignore)
    .accessibilityLabel("Words practiced each day this week")
    .accessibilityValue(
      week.days.map { day in
        "\(day.date.formatted(.dateTime.weekday(.wide))): \(day.words)"
      }.joined(separator: ", "))
    .accessibilityIdentifier("cadence.progress.week")
  }
}

/// Sessions and words per sound group, most recently practiced first.
struct PracticeSoundTally: Identifiable, Equatable {
  let soundID: String
  let sessions: Int
  let words: Int
  let lastPracticed: Date
  var id: String { soundID }

  var summary: String {
    "\(sessions) \(sessions == 1 ? "session" : "sessions") · \(words) \(words == 1 ? "word" : "words") · last \(lastPracticed.formatted(.dateTime.month(.abbreviated).day()))"
  }

  static func from(_ entries: [PracticeParticipation]) -> [PracticeSoundTally] {
    Dictionary(grouping: entries, by: \.soundID)
      .map { soundID, group in
        PracticeSoundTally(
          soundID: soundID,
          sessions: group.count,
          words: group.reduce(0) { $0 + $1.wordCount },
          lastPracticed: group.map(\.completedAt).max() ?? .distantPast)
      }
      .sorted { $0.lastPracticed > $1.lastPracticed }
  }
}
