import Foundation
import Security
import CryptoKit

struct StoredFamilySession: Codable, Equatable {
    let server: String
    let token: String
    let accountID: UUID
    let familyID: UUID
    let username: String
    let legacy: Bool
    let expiresAt: String
    var scope: String { server + "\n" + accountID.uuidString + "\n" + familyID.uuidString }
    var scopeKey: String { SHA256.hash(data: Data(scope.utf8)).map { String(format: "%02x", $0) }.joined() }
}

protocol FamilySessionPersistence {
    func load() -> StoredFamilySession?
    @discardableResult func save(_ session: StoredFamilySession) -> Bool
    func clear()
}

final class FamilySessionStore: FamilySessionPersistence {
    static let shared = FamilySessionStore()
    private let key = "aimemories.simulator.family-session"
    private var query: [String: Any] {
        [kSecClass as String: kSecClassGenericPassword,
         kSecAttrService as String: Bundle.main.bundleIdentifier ?? "com.aimemories.app",
         kSecAttrAccount as String: "family-device-session"]
    }
    func load() -> StoredFamilySession? {
        let data: Data
        #if targetEnvironment(simulator)
        guard let value = UserDefaults.standard.data(forKey: key) else { return nil }; data = value
        #else
        var request = query; request[kSecReturnData as String] = true; request[kSecMatchLimit as String] = kSecMatchLimitOne
        var value: CFTypeRef?
        guard SecItemCopyMatching(request as CFDictionary, &value) == errSecSuccess, let value = value as? Data else { return nil }
        data = value
        #endif
        return try? JSONDecoder().decode(StoredFamilySession.self, from: data)
    }
    @discardableResult func save(_ session: StoredFamilySession) -> Bool {
        guard let data = try? JSONEncoder().encode(session) else { return false }
        #if targetEnvironment(simulator)
        UserDefaults.standard.set(data, forKey: key); return true
        #else
        if load() != nil {
            return SecItemUpdate(query as CFDictionary, [kSecValueData as String: data] as CFDictionary) == errSecSuccess
        }
        var request = query
        request[kSecValueData as String] = data
        request[kSecAttrAccessible as String] = kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly
        return SecItemAdd(request as CFDictionary, nil) == errSecSuccess
        #endif
    }
    func clear() {
        #if targetEnvironment(simulator)
        UserDefaults.standard.removeObject(forKey: key)
        #else
        SecItemDelete(query as CFDictionary)
        #endif
    }
}

/// Captured by each APIClient. Retired clients can never adopt another account's token.
final class FamilySessionContext: @unchecked Sendable {
    let session: StoredFamilySession
    private let lock = NSLock()
    private var active = true
    init(_ session: StoredFamilySession) { self.session = session }
    func invalidate() { lock.lock(); active = false; lock.unlock() }
    var authorization: String? {
        lock.lock(); defer { lock.unlock() }
        return active ? "Bearer " + session.token : nil
    }
}

enum FamilySessionRegistry {
    private static let lock = NSLock()
    private static var value: FamilySessionContext?
    static var current: FamilySessionContext? { lock.lock(); defer { lock.unlock() }; return value }
    static func replace(with session: StoredFamilySession?) {
        lock.lock(); defer { lock.unlock() }
        value?.invalidate()
        value = session.map(FamilySessionContext.init)
    }
    static func authorizationProvider() -> () -> String? {
        let context = current
        return { context?.authorization }
    }
    static var scopeKey: String { current?.session.scopeKey ?? (JournalDemo.isPreview ? "design-preview" : "signed-out") }
    static var displayNameKey: String { "journal.displayName." + scopeKey }
    static var portraitsDirectory: URL {
        FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0]
            .appendingPathComponent("Accounts/" + scopeKey + "/FamilyPortraits", isDirectory: true)
    }
}
