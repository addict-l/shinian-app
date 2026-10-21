import Foundation
import Testing
import CryptoKit
@testable import AIMemoirs

private final class MemorySessions: FamilySessionPersistence {
    var value: StoredFamilySession?
    var canSave = true
    func load() -> StoredFamilySession? { value }
    func save(_ session: StoredFamilySession) -> Bool { if canSave { value = session }; return canSave }
    func clear() { value = nil }
}
private final class LegacyCredentials: FamilyCredentialPersistence {
    var value: FamilyCredentials?
    func load() -> FamilyCredentials? { value }
    func save(_ credentials: FamilyCredentials) -> Bool { value = credentials; return true }
    func clear() { value = nil }
    var authorizationHeader: String? { nil }
}
private final class LoginProtocol: URLProtocol, @unchecked Sendable {
    nonisolated(unsafe) static var status = 200
    nonisolated(unsafe) static var body = Data()
    nonisolated(unsafe) static var requests: [URLRequest] = []
    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }
    override func startLoading() {
        Self.requests.append(request)
        client?.urlProtocol(self, didReceive: HTTPURLResponse(url: request.url!, statusCode: Self.status,
            httpVersion: nil, headerFields: nil)!, cacheStoragePolicy: .notAllowed)
        client?.urlProtocol(self, didLoad: Self.body)
        client?.urlProtocolDidFinishLoading(self)
    }
    override func stopLoading() {}
}

@Suite(.serialized) struct LiveAuthenticationTests {
    private let account = UUID(uuidString: "11111111-1111-4111-8111-111111111111")!
    private let family = UUID(uuidString: "22222222-2222-4222-8222-222222222222")!
    private var identity: Data { Data("{\"account_id\":\"\(account)\",\"family_id\":\"\(family)\",\"username\":\"family\",\"legacy\":false}".utf8) }
    private var loginResponse: Data { Data("{\"account_id\":\"\(account)\",\"family_id\":\"\(family)\",\"username\":\"family\",\"legacy\":false,\"token\":\"synthetic-device-token\",\"expires_at\":\"2099-01-01T00:00:00Z\"}".utf8) }
    private var saved: StoredFamilySession { StoredFamilySession(server: "https://login.invalid", token: "synthetic-device-token",
        accountID: account, familyID: family, username: "family", legacy: false, expiresAt: "2099-01-01T00:00:00Z") }
    @MainActor private func client() -> APIClient {
        FamilySessionRegistry.replace(with: nil)
        let config = URLSessionConfiguration.ephemeral; config.protocolClasses = [LoginProtocol.self]
        LoginProtocol.requests = []; LoginProtocol.status = 200; LoginProtocol.body = loginResponse
        return APIClient(baseURL: URL(string: "https://login.invalid")!, session: URLSession(configuration: config))
    }
    @Test @MainActor func normalLaunchRequiresServerSessionValidation() async {
        let credentials = MemorySessions()
        let auth = AuthenticationStore(client: client(), credentials: credentials, legacyCredentials: LegacyCredentials())
        #expect(!auth.isAuthenticated && auth.isRestoring)
        await auth.restore()
        #expect(!auth.isAuthenticated && !auth.isRestoring && LoginProtocol.requests.isEmpty)
    }
    @Test @MainActor func loginPostsCredentialsAndStoresOnlyReturnedDeviceSession() async {
        let credentials = MemorySessions(), legacy = LegacyCredentials()
        legacy.value = FamilyCredentials(username: "family", password: "synthetic-old-password")
        let auth = AuthenticationStore(client: client(), credentials: credentials, legacyCredentials: legacy)
        await auth.login(username: " FAMILY ", password: "synthetic-password")
        #expect(auth.isAuthenticated && !auth.isLoading && auth.errorMessage == nil)
        #expect(credentials.value?.familyID == family && credentials.value?.token == "synthetic-device-token")
        #expect(legacy.value == nil)
        #expect(LoginProtocol.requests.first?.url?.path == "/api/v1/auth/login")
        #expect(LoginProtocol.requests.first?.httpMethod == "POST")
        #expect(LoginProtocol.requests.first?.value(forHTTPHeaderField: "Authorization") == nil)
    }
    @Test @MainActor func rejectedLoginAndDuplicateRegistrationNeverEnterFamily() async {
        let credentials = MemorySessions()
        let auth = AuthenticationStore(client: client(), credentials: credentials, legacyCredentials: LegacyCredentials())
        LoginProtocol.status = 401
        await auth.login(username: "family", password: "wrong")
        #expect(!auth.isAuthenticated && credentials.value == nil && auth.errorMessage?.contains("账号或密码") == true)
        LoginProtocol.status = 409; LoginProtocol.body = Data(#"{"detail":"这个账号已被使用。"}"#.utf8)
        await auth.register(username: "new_family", password: "synthetic-password")
        #expect(!auth.isAuthenticated && credentials.value == nil && auth.errorMessage == "这个账号已被使用。")
    }
    @Test @MainActor func registrationUsesRegistrationEndpointAndEntersReturnedFamily() async {
        let auth = AuthenticationStore(client: client(), credentials: MemorySessions(), legacyCredentials: LegacyCredentials())
        await auth.register(username: "new_family", password: "synthetic-password")
        #expect(auth.isAuthenticated && auth.session?.familyID == family)
        #expect(LoginProtocol.requests.first?.url?.path == "/api/v1/auth/register")
    }
    @Test @MainActor func savedSessionIsValidatedBeforeShowingFamily() async {
        let credentials = MemorySessions(); credentials.value = saved
        let auth = AuthenticationStore(client: client(), credentials: credentials, legacyCredentials: LegacyCredentials())
        #expect(!auth.isAuthenticated)
        LoginProtocol.body = identity
        await auth.restore()
        #expect(auth.isAuthenticated && !auth.isRestoring)
        #expect(LoginProtocol.requests.first?.url?.path == "/api/v1/auth/me")
        #expect(LoginProtocol.requests.first?.value(forHTTPHeaderField: "Authorization") == "Bearer " + saved.token)
    }
    @Test @MainActor func expiredSessionDoesNotRestoreFamily() async {
        let credentials = MemorySessions(); credentials.value = saved
        let auth = AuthenticationStore(client: client(), credentials: credentials, legacyCredentials: LegacyCredentials())
        LoginProtocol.status = 401
        await auth.restore()
        #expect(!auth.isAuthenticated && credentials.value == nil && !auth.isRestoring)
    }
    @Test @MainActor func logoutRevokesCurrentSessionAndInvalidatesCapturedClients() async {
        let credentials = MemorySessions()
        let auth = AuthenticationStore(client: client(), credentials: credentials, legacyCredentials: LegacyCredentials())
        await auth.login(username: "family", password: "synthetic-password")
        let oldClient = APIClient(baseURL: URL(string: saved.server)!)
        #expect(oldClient.authorizationProvider() == "Bearer " + saved.token)
        LoginProtocol.status = 204
        await auth.logout()
        #expect(!auth.isAuthenticated && credentials.value == nil && oldClient.authorizationProvider() == nil)
        #expect(LoginProtocol.requests.last?.url?.path == "/api/v1/auth/logout")
        #expect(LoginProtocol.requests.last?.value(forHTTPHeaderField: "Authorization") == "Bearer " + saved.token)
        FamilySessionRegistry.replace(with: StoredFamilySession(server: saved.server, token: "different-device-token",
            accountID: UUID(), familyID: UUID(), username: "other_family", legacy: false, expiresAt: saved.expiresAt))
        #expect(oldClient.authorizationProvider() == nil)
        FamilySessionRegistry.replace(with: nil)
    }
    @Test @MainActor func failedLogoutRetainsSessionForRetry() async {
        let credentials = MemorySessions()
        let auth = AuthenticationStore(client: client(), credentials: credentials, legacyCredentials: LegacyCredentials())
        await auth.login(username: "family", password: "synthetic-password")
        LoginProtocol.status = 503
        await auth.logout()
        #expect(auth.isAuthenticated && credentials.value != nil && auth.errorMessage != nil)
    }
    @Test @MainActor func oldAuthenticationFailuresCannotLogOutNewSession() async {
        let auth = AuthenticationStore(client: client(), credentials: MemorySessions(), legacyCredentials: LegacyCredentials())
        await auth.login(username: "family", password: "synthetic-password")
        auth.handleAuthenticationFailure(Notification(name: .journalAuthenticationRequired,
            userInfo: ["server": saved.server, "authorization": "Bearer stale-token"]))
        #expect(auth.isAuthenticated)
        auth.handleAuthenticationFailure(Notification(name: .journalAuthenticationRequired,
            userInfo: ["server": saved.server, "authorization": "Bearer " + saved.token]))
        #expect(!auth.isAuthenticated && auth.errorMessage != nil)
    }
    @Test @MainActor func emptyFieldsDoNotMakeRequests() async {
        let auth = AuthenticationStore(client: client(), credentials: MemorySessions(), legacyCredentials: LegacyCredentials())
        await auth.login(username: " ", password: "")
        #expect(LoginProtocol.requests.isEmpty && !auth.isAuthenticated)
    }
    @Test func ambiguousStoryYearsDoNotBecomeExactGroups() {
        let memory = MemoryEvent(personName: "家人", date: nil, content: "故事", title: "标题", dateDescription: "1998年到2000年")
        #expect(memoryYear(memory) == nil)
    }
    @Test @MainActor func chatAndMemoirFilesStayWithTheirAccountAcrossLogoutAndReLogin() throws {
        let a = StoredFamilySession(server: saved.server, token: "cache-token-a", accountID: UUID(), familyID: UUID(),
            username: "cache_a", legacy: false, expiresAt: saved.expiresAt)
        let b = StoredFamilySession(server: saved.server, token: "cache-token-b", accountID: UUID(), familyID: UUID(),
            username: "cache_b", legacy: false, expiresAt: saved.expiresAt)
        let person = UUID(), photo = UUID()
        let support = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]
        defer {
            FamilySessionRegistry.replace(with: nil)
            for session in [a, b] {
                for folder in ["PendingStories", "Memoirs"] {
                    try? FileManager.default.removeItem(at: support.appendingPathComponent(folder + "/" + session.scopeKey))
                }
            }
        }
        FamilySessionRegistry.replace(with: a)
        let draftsA = try #require(ChatDraftStore.current(previewScreen: nil))
        let memoirA = try #require(MemoirLocalStore.current(personID: person))
        try draftsA.save(LocalChatDraft(id: person, personID: person, personName: "测试家人", relationship: "家人", input: "A 的未发送输入"), photos: [])
        _ = try memoirA.savePhoto(Data([1, 2, 3]), id: photo)
        FamilySessionRegistry.replace(with: nil)
        #expect(ChatDraftStore.current(previewScreen: nil) == nil)
        FamilySessionRegistry.replace(with: b)
        let draftsB = try #require(ChatDraftStore.current(previewScreen: nil))
        let memoirB = try #require(MemoirLocalStore.current(personID: person))
        #expect(try draftsB.list().isEmpty)
        #expect(!FileManager.default.fileExists(atPath: memoirB.photoURL(photo).path))
        #expect(memoirB.root != memoirA.root)
        // A retained old task writes only into A's captured directory.
        try draftsA.save(LocalChatDraft(id: person, personID: person, personName: "测试家人", relationship: "家人", input: "A 延迟保存的输入"), photos: [])
        #expect(try draftsB.list().isEmpty)
        FamilySessionRegistry.replace(with: a)
        let restored = try #require(ChatDraftStore.current(previewScreen: nil))
        #expect(try restored.draft(for: person)?.input == "A 延迟保存的输入")
        #expect(FileManager.default.fileExists(atPath: memoirA.photoURL(photo).path))
    }
    @Test @MainActor func namesAndPortraitPathsAreScopedToAuthenticatedAccount() {
        let a = StoredFamilySession(server: saved.server, token: "scope-token-a", accountID: UUID(), familyID: UUID(), username: "scope_a", legacy: false, expiresAt: saved.expiresAt)
        let b = StoredFamilySession(server: saved.server, token: "scope-token-b", accountID: UUID(), familyID: UUID(), username: "scope_b", legacy: false, expiresAt: saved.expiresAt)
        defer { FamilySessionRegistry.replace(with: nil) }
        FamilySessionRegistry.replace(with: a)
        let nameKey = FamilySessionRegistry.displayNameKey, portraitPath = FamilySessionRegistry.portraitsDirectory
        UserDefaults.standard.set("A 的显示名称", forKey: nameKey)
        defer { UserDefaults.standard.removeObject(forKey: nameKey) }
        FamilySessionRegistry.replace(with: b)
        #expect(FamilySessionRegistry.displayNameKey != nameKey)
        #expect(UserDefaults.standard.string(forKey: FamilySessionRegistry.displayNameKey) == nil)
        #expect(FamilySessionRegistry.portraitsDirectory != portraitPath)
    }
    @Test @MainActor func legacyMigrationResumesMissingFilesWithoutOverwritingEitherFamily() throws {
        let fm = FileManager.default
        let root = fm.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        let support = root.appendingPathComponent("Support"), documents = root.appendingPathComponent("Documents")
        let suite = "family-auth-test." + UUID().uuidString
        let defaults = try #require(UserDefaults(suiteName: suite))
        defer { try? fm.removeItem(at: root); defaults.removePersistentDomain(forName: suite) }
        let legacy = StoredFamilySession(server: saved.server, token: "migration-test", accountID: UUID(),
            familyID: try #require(UUID(uuidString: "60d34ec1-aa9d-5d17-8e5e-cdf5831747ba")),
            username: "family", legacy: true, expiresAt: saved.expiresAt)
        let oldKey = SHA256.hash(data: Data((legacy.server + "\nfamily").utf8)).map { String(format: "%02x", $0) }.joined()
        let oldDirectory = support.appendingPathComponent("PendingStories/" + oldKey)
        let destination = support.appendingPathComponent("PendingStories/" + legacy.scopeKey)
        try fm.createDirectory(at: oldDirectory, withIntermediateDirectories: true)
        try fm.createDirectory(at: destination, withIntermediateDirectories: true)
        try Data("old draft".utf8).write(to: oldDirectory.appendingPathComponent("draft.json"))
        try Data("old photo".utf8).write(to: oldDirectory.appendingPathComponent("photo.jpg"))
        try Data("newer draft".utf8).write(to: destination.appendingPathComponent("draft.json"))
        defaults.set("原昵称", forKey: "journal.displayName")
        try LegacyFamilyCacheMigration.migrate(legacy, applicationSupport: support, documentDirectory: documents, defaults: defaults)
        #expect(try Data(contentsOf: destination.appendingPathComponent("photo.jpg")) == Data("old photo".utf8))
        #expect(try Data(contentsOf: destination.appendingPathComponent("draft.json")) == Data("newer draft".utf8))
        #expect(try Data(contentsOf: oldDirectory.appendingPathComponent("draft.json")) == Data("old draft".utf8))
        #expect(defaults.string(forKey: "journal.displayName." + legacy.scopeKey) == "原昵称")
        let unrelated = StoredFamilySession(server: saved.server, token: "other", accountID: UUID(),
            familyID: legacy.familyID, username: "other", legacy: false, expiresAt: saved.expiresAt)
        try LegacyFamilyCacheMigration.migrate(unrelated, applicationSupport: support, documentDirectory: documents, defaults: defaults)
        #expect(!fm.fileExists(atPath: support.appendingPathComponent("PendingStories/" + unrelated.scopeKey).path))
    }
    @Test @MainActor func failedLocalCredentialSaveRevokesTheNewServerSession() async {
        let credentials = MemorySessions(); credentials.canSave = false
        let auth = AuthenticationStore(client: client(), credentials: credentials, legacyCredentials: LegacyCredentials())
        await auth.login(username: "family", password: "synthetic-password")
        #expect(!auth.isAuthenticated && credentials.value == nil && auth.errorMessage != nil)
        #expect(LoginProtocol.requests.last?.url?.path == "/api/v1/auth/logout")
        #expect(LoginProtocol.requests.count == 2)
    }

}
