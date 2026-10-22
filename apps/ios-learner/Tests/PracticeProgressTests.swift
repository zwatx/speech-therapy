import Foundation
import XCTest

@testable import CadenceLearner

final class PracticeProgressTests: XCTestCase {
  private var calendar: Calendar {
    var calendar = Calendar(identifier: .gregorian)
    calendar.timeZone = TimeZone(identifier: "America/Chicago")!
    return calendar
  }

  private func date(_ day: Int, month: Int = 11, hour: Int = 0, minute: Int = 0) -> Date {
    calendar.date(
      from: DateComponents(year: 2026, month: month, day: day, hour: hour, minute: minute))!
  }

  private func entry(
    _ day: Int, month: Int = 11, hour: Int = 0, minute: Int = 0, sound: String = "b", words: Int = 1
  )
    -> PracticeParticipation
  {
    PracticeParticipation(
      id: UUID(), completedAt: date(day, month: month, hour: hour, minute: minute), soundID: sound,
      wordCount: words)
  }

  func testWeekContainsSevenCalendarDaysEndingTodayAcrossDaylightSavingChange() {
    let week = PracticeWeek(entries: [], endingOn: date(4, hour: 13), calendar: calendar)
    let expected = [
      date(29, month: 10), date(30, month: 10), date(31, month: 10), date(1), date(2), date(3),
      date(4),
    ]
    XCTAssertEqual(week.days.map(\.date), expected)
    XCTAssertEqual(week.days.map(\.id), expected)
    XCTAssertEqual(week.days.map(\.words), Array(repeating: 0, count: 7))
    XCTAssertEqual(week.days.last?.date, calendar.startOfDay(for: date(4, hour: 13)))
  }

  func testWeekSumsSessionsByLocalCalendarDayAndIgnoresEntriesOutsideWindow() {
    let week = PracticeWeek(
      entries: [
        entry(29, month: 10, hour: 0, words: 2),
        entry(29, month: 10, hour: 23, minute: 59, sound: "r", words: 3),
        entry(1, hour: 0, minute: 30, words: 1), entry(1, hour: 23, words: 2),
        entry(4, hour: 23, minute: 59, words: 3),
        entry(28, month: 10, hour: 23, minute: 59, words: 3), entry(5, words: 3),
      ], endingOn: date(4, hour: 12), calendar: calendar)
    XCTAssertEqual(week.days.map(\.words), [5, 0, 0, 3, 0, 0, 3])
    XCTAssertEqual(week.activeDays, 3)
    XCTAssertEqual(week.totalWords, 11)
  }

  func testEmptyWeekCopyInvitesPractice() {
    let week = PracticeWeek(entries: [entry(28, month: 10)], endingOn: date(4), calendar: calendar)
    XCTAssertEqual(week.activeDays, 0)
    XCTAssertEqual(week.totalWords, 0)
    XCTAssertEqual(week.headline, "No practice yet this week.")
    XCTAssertEqual(week.detail, "Start from Today or pick a sound. A few words a day is plenty.")
  }

  func testOneActiveDayUsesSingularDayAndWordCopy() {
    let week = PracticeWeek(entries: [entry(4)], endingOn: date(4), calendar: calendar)
    XCTAssertEqual(week.activeDays, 1)
    XCTAssertEqual(week.totalWords, 1)
    XCTAssertEqual(week.headline, "1 day this week.")
    XCTAssertEqual(week.detail, "1 word practiced in the last seven days.")
  }

  func testMultipleSessionsOnOneDayKeepSingularDayAndPluralWords() {
    let week = PracticeWeek(
      entries: [entry(4), entry(4, hour: 12, words: 2)], endingOn: date(4), calendar: calendar)
    XCTAssertEqual(week.headline, "1 day this week.")
    XCTAssertEqual(week.detail, "3 words practiced in the last seven days.")
  }

  func testManyActiveDaysUsePluralCopy() {
    let week = PracticeWeek(
      entries: [entry(2, words: 2), entry(3), entry(4, words: 3)],
      endingOn: date(4), calendar: calendar)
    XCTAssertEqual(week.activeDays, 3)
    XCTAssertEqual(week.headline, "3 days this week.")
    XCTAssertEqual(week.detail, "6 words practiced in the last seven days.")
  }

  func testSoundTalliesGroupSumAndSortByNewestSessionRegardlessOfInputOrder() {
    let entries = [
      entry(2, sound: "r", words: 2), entry(1, sound: "b", words: 3),
      entry(4, sound: "r"), entry(3, sound: "sh", words: 2),
      entry(2, hour: 12, sound: "b"),
    ]
    let expected = [
      PracticeSoundTally(soundID: "r", sessions: 2, words: 3, lastPracticed: date(4)),
      PracticeSoundTally(soundID: "sh", sessions: 1, words: 2, lastPracticed: date(3)),
      PracticeSoundTally(soundID: "b", sessions: 2, words: 4, lastPracticed: date(2, hour: 12)),
    ]
    XCTAssertEqual(PracticeSoundTally.from(entries), expected)
    XCTAssertEqual(PracticeSoundTally.from(entries.reversed()), expected)
    XCTAssertEqual(PracticeSoundTally.from(entries).map(\.id), ["r", "sh", "b"])
  }

  func testEmptyHistoryHasNoSoundTallies() {
    XCTAssertEqual(PracticeSoundTally.from([]), [])
  }
}
