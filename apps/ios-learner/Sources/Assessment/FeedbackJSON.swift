#if DEBUG && targetEnvironment(simulator)
  import Foundation

  /// Small bounded transport parser. Foundation decoding alone discards duplicate keys.
  enum FeedbackJSON {
    indirect enum Value {
      case object([String: Value]), array([Value]), string(String), number(Double, Int?), bool(
        Bool), null
      func object(_ keys: Set<String>) throws -> [String: Value] {
        guard case .object(let fields) = self, Set(fields.keys) == keys else {
          throw RecordingFeedbackError.invalidResponse
        }
        return fields
      }
      func string() throws -> String {
        guard case .string(let v) = self else { throw RecordingFeedbackError.invalidResponse }
        return v
      }
      func nullableString() throws -> String? {
        if case .null = self { return nil }
        return try string()
      }
      func number() throws -> Double {
        guard case .number(let v, _) = self else { throw RecordingFeedbackError.invalidResponse }
        return v
      }
      func integer() throws -> Int {
        guard case .number(_, let v?) = self else { throw RecordingFeedbackError.invalidResponse }
        return v
      }
      func boolean() throws -> Bool {
        guard case .bool(let v) = self else { throw RecordingFeedbackError.invalidResponse }
        return v
      }
      func array() throws -> [Value] {
        guard case .array(let v) = self else { throw RecordingFeedbackError.invalidResponse }
        return v
      }
      var isNull: Bool {
        if case .null = self { return true }
        return false
      }
    }
    static func parse(_ data: Data) throws -> Value {
      guard !data.isEmpty, data.count <= 16_000, String(data: data, encoding: .utf8) != nil else {
        throw RecordingFeedbackError.invalidResponse
      }
      var parser = Parser(bytes: Array(data))
      let value = try parser.value(depth: 0)
      parser.space()
      guard parser.index == parser.bytes.count else { throw RecordingFeedbackError.invalidResponse }
      return value
    }
    private struct Parser {
      let bytes: [UInt8]
      var index = 0
      var tokens = 0
      mutating func space() {
        while index < bytes.count && [9, 10, 13, 32].contains(bytes[index]) { index += 1 }
      }
      mutating func take(_ byte: UInt8) -> Bool {
        space()
        if index < bytes.count && bytes[index] == byte {
          index += 1
          return true
        }
        return false
      }
      mutating func require(_ byte: UInt8) throws {
        guard take(byte) else { throw RecordingFeedbackError.invalidResponse }
      }
      mutating func text() throws -> String {
        space()
        let start = index
        try require(34)
        while index < bytes.count {
          let byte = bytes[index]
          index += 1
          if byte == 34 {
            guard
              let value = try? JSONDecoder().decode(String.self, from: Data(bytes[start..<index]))
            else { throw RecordingFeedbackError.invalidResponse }
            return value
          }
          if byte == 92 {
            guard index < bytes.count else { throw RecordingFeedbackError.invalidResponse }
            index += 1
          } else if byte < 32 {
            throw RecordingFeedbackError.invalidResponse
          }
        }
        throw RecordingFeedbackError.invalidResponse
      }
      mutating func value(depth: Int) throws -> Value {
        tokens += 1
        space()
        guard depth <= 16, tokens <= 1024, index < bytes.count else {
          throw RecordingFeedbackError.invalidResponse
        }
        if take(123) {
          var fields: [String: Value] = [:]
          if take(125) { return .object(fields) }
          repeat {
            let key = try text()
            guard fields[key] == nil, fields.count < 64 else {
              throw RecordingFeedbackError.invalidResponse
            }
            try require(58)
            fields[key] = try value(depth: depth + 1)
            if take(125) { return .object(fields) }
            try require(44)
          } while true
        }
        if take(91) {
          var items: [Value] = []
          if take(93) { return .array(items) }
          repeat {
            guard items.count < 128 else { throw RecordingFeedbackError.invalidResponse }
            items.append(try value(depth: depth + 1))
            if take(93) { return .array(items) }
            try require(44)
          } while true
        }
        if bytes[index] == 34 { return .string(try text()) }
        for (word, result) in [
          ("true", Value.bool(true)), ("false", Value.bool(false)), ("null", Value.null),
        ] {
          let literal = Array(word.utf8)
          if bytes[index...].starts(with: literal) {
            index += literal.count
            return result
          }
        }
        let start = index
        while index < bytes.count && ![9, 10, 13, 32, 44, 93, 125].contains(bytes[index]) {
          index += 1
        }
        let token = String(decoding: bytes[start..<index], as: UTF8.self)
        guard
          token.range(
            of: #"^-?(0|[1-9][0-9]*)(\.[0-9]+)?([eE][+-]?[0-9]+)?$"#, options: .regularExpression)
            != nil,
          let number = Double(token), number.isFinite
        else { throw RecordingFeedbackError.invalidResponse }
        return .number(number, Int(token))
      }
    }
  }
#endif
