import Foundation
import Testing
@testable import AIMemoirs

private final class MemoryCredentials: FamilyCredentialPersistence {
    var value: FamilyCredentials?
    func load() -> FamilyCredentials? { value }
    func save(_ credentials: FamilyCredentials) -> Bool { value = credentials; return true }
    func clear() { value = nil }
    var authorizationHeader: String? {
        value.map { "Basic " + Data(($0.username + ":" + $0.password).utf8).base64EncodedString() }
    }
}
private final class LoginProtocol: URLProtocol, @unchecked Sendable {
    nonisolated(unsafe) static var status = 200
    nonisolated(unsafe) static var requests: [URLRequest] = []
    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }
    override func startLoading() {
        Self.requests.append(request)
        client?.urlProtocol(self, didReceive: HTTPURLResponse(url: request.url!, statusCode: Self.status,
            httpVersion: nil, headerFields: nil)!, cacheStoragePolicy: .notAllowed)
        client?.urlProtocol(self, didLoad: Data(#"{"status":"ok"}"#.utf8))
        client?.urlProtocolDidFinishLoading(self)
    }
    override func stopLoading() {}
}
@Suite(.serialized) struct LiveAuthenticationTests {
    @MainActor private func client() -> APIClient {
        let config = URLSessionConfiguration.ephemeral; config.protocolClasses = [LoginProtocol.self]
        LoginProtocol.requests = []
        return APIClient(baseURL: URL(string: "https://login.invalid")!, session: URLSession(configuration: config))
    }
    @Test @MainActor func normalLaunchDoesNotEnableDesignPreview() {
        #expect(JournalDemo.screen == nil && !JournalDemo.isPreview)
        #expect(!AuthenticationStore(client: client(), credentials: MemoryCredentials()).isAuthenticated)
    }
    @Test @MainActor func loginWaitsForAuthenticatedServerAndKeepsCredential() async {
        LoginProtocol.status = 200
        let credentials = MemoryCredentials(), client = client()
        let auth = AuthenticationStore(client: client, credentials: credentials)
        await auth.login(username: " family ", password: "synthetic-password")
        #expect(auth.isAuthenticated && !auth.isLoading && auth.errorMessage == nil)
        #expect(credentials.value?.username == "family")
        #expect(LoginProtocol.requests.first?.url?.path == "/health")
        #expect(LoginProtocol.requests.first?.value(forHTTPHeaderField: "Authorization") == credentials.authorizationHeader)
        auth.logout()
        #expect(!auth.isAuthenticated && credentials.value == nil)
    }
    @Test @MainActor func rejectedLoginNeverEntersFamilyOrKeepsRejectedCredential() async {
        LoginProtocol.status = 401
        let credentials = MemoryCredentials()
        let auth = AuthenticationStore(client: client(), credentials: credentials)
        await auth.login(username: "family", password: "synthetic-wrong-password")
        #expect(!auth.isAuthenticated && !auth.isLoading && credentials.value == nil)
        #expect(auth.errorMessage?.contains("账号或密码") == true)
    }
    @Test @MainActor func networkFailurePreservesEarlierCredential() async {
        LoginProtocol.status = 503
        let credentials = MemoryCredentials()
        let previous = FamilyCredentials(username: "family", password: "synthetic-old-password")
        credentials.value = previous
        let auth = AuthenticationStore(client: client(), credentials: credentials)
        await auth.login(username: "family", password: "synthetic-new-password")
        #expect(credentials.value == previous && auth.errorMessage != nil)
    }
    @Test @MainActor func expiredSessionLogsOutButOldRequestsCannotLogOutNewAccount() {
        let credentials = MemoryCredentials(), client = client()
        credentials.value = FamilyCredentials(username: "family", password: "synthetic-password")
        let auth = AuthenticationStore(client: client, credentials: credentials)
        auth.handleAuthenticationFailure(Notification(name: .journalAuthenticationRequired,
            userInfo: ["server": client.baseURL.absoluteString, "authorization": "Basic stale"]))
        #expect(auth.isAuthenticated)
        auth.handleAuthenticationFailure(Notification(name: .journalAuthenticationRequired,
            userInfo: ["server": client.baseURL.absoluteString, "authorization": credentials.authorizationHeader!]))
        #expect(!auth.isAuthenticated && credentials.value == nil && auth.errorMessage != nil)
    }
    @Test @MainActor func emptyFieldsDoNotMakeRequests() async {
        let auth = AuthenticationStore(client: client(), credentials: MemoryCredentials())
        await auth.login(username: " ", password: "")
        #expect(LoginProtocol.requests.isEmpty && !auth.isAuthenticated)
    }
    @Test func ambiguousStoryYearsDoNotBecomeExactGroups() {
        let memory = MemoryEvent(personName: "家人", date: nil, content: "故事", title: "标题", dateDescription: "1998年到2000年")
        #expect(memoryYear(memory) == nil)
    }
}
