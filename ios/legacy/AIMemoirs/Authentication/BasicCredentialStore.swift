import Foundation
import Security

struct FamilyCredentials: Codable, Equatable {
    let username: String
    let password: String
}

final class BasicCredentialStore {
    static let shared = BasicCredentialStore()

    private let service = Bundle.main.bundleIdentifier ?? "com.aimemories.app"
    private let account = "family-basic-auth"
    private let simulatorKey = "aimemories.simulator.family-credentials"

    private init() {}

    func load() -> FamilyCredentials? {
        #if targetEnvironment(simulator)
        guard let data = UserDefaults.standard.data(forKey: simulatorKey) else { return nil }
        return try? JSONDecoder().decode(FamilyCredentials.self, from: data)
        #else
        var query = baseQuery
        query[kSecReturnData as String] = true
        query[kSecMatchLimit as String] = kSecMatchLimitOne

        var result: CFTypeRef?
        guard SecItemCopyMatching(query as CFDictionary, &result) == errSecSuccess,
              let data = result as? Data else { return nil }
        return try? JSONDecoder().decode(FamilyCredentials.self, from: data)
        #endif
    }

    @discardableResult
    func save(_ credentials: FamilyCredentials) -> Bool {
        guard let data = try? JSONEncoder().encode(credentials) else { return false }
        #if targetEnvironment(simulator)
        UserDefaults.standard.set(data, forKey: simulatorKey)
        return true
        #else
        let status: OSStatus
        if load() == nil {
            var query = baseQuery
            query[kSecValueData as String] = data
            query[kSecAttrAccessible as String] = kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly
            status = SecItemAdd(query as CFDictionary, nil)
        } else {
            status = SecItemUpdate(
                baseQuery as CFDictionary,
                [kSecValueData as String: data] as CFDictionary
            )
        }
        return status == errSecSuccess
        #endif
    }

    func clear() {
        #if targetEnvironment(simulator)
        UserDefaults.standard.removeObject(forKey: simulatorKey)
        #else
        SecItemDelete(baseQuery as CFDictionary)
        #endif
    }

    var authorizationHeader: String? {
        guard let credentials = load(),
              let data = "\(credentials.username):\(credentials.password)".data(using: .utf8)
        else { return nil }
        return "Basic \(data.base64EncodedString())"
    }

    private var baseQuery: [String: Any] {
        [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: account
        ]
    }
}
