import Foundation
import Security

protocol EnrollmentCredentialStoring {
  func load() throws -> Data?
  func save(_ data: Data) throws
  func remove() throws
}

enum EnrollmentCredentialStoreError: LocalizedError {
  case keychain(OSStatus)

  var errorDescription: String? {
    switch self {
    case .keychain:
      "The secure practice link could not be stored on this device."
    }
  }
}

struct KeychainEnrollmentCredentialStore: EnrollmentCredentialStoring {
  private let service = "com.cadence.speechtherapy.learner.enrollment"
  private let account = "active-device-session"

  func load() throws -> Data? {
    let query: [String: Any] = [
      kSecClass as String: kSecClassGenericPassword,
      kSecAttrService as String: service,
      kSecAttrAccount as String: account,
      kSecReturnData as String: true,
      kSecMatchLimit as String: kSecMatchLimitOne,
    ]
    var result: CFTypeRef?
    let status = SecItemCopyMatching(query as CFDictionary, &result)
    if status == errSecItemNotFound { return nil }
    guard status == errSecSuccess, let data = result as? Data else {
      throw EnrollmentCredentialStoreError.keychain(status)
    }
    return data
  }

  func save(_ data: Data) throws {
    try remove()
    let query: [String: Any] = [
      kSecClass as String: kSecClassGenericPassword,
      kSecAttrService as String: service,
      kSecAttrAccount as String: account,
      kSecAttrAccessible as String: kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly,
      kSecValueData as String: data,
    ]
    let status = SecItemAdd(query as CFDictionary, nil)
    guard status == errSecSuccess else {
      throw EnrollmentCredentialStoreError.keychain(status)
    }
  }

  func remove() throws {
    let query: [String: Any] = [
      kSecClass as String: kSecClassGenericPassword,
      kSecAttrService as String: service,
      kSecAttrAccount as String: account,
    ]
    let status = SecItemDelete(query as CFDictionary)
    guard status == errSecSuccess || status == errSecItemNotFound else {
      throw EnrollmentCredentialStoreError.keychain(status)
    }
  }
}
