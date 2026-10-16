import SwiftUI

private struct AccountIdentityResponse: Decodable {
    let account_id: UUID
    let family_id: UUID
    let username: String
    let legacy: Bool
}
private struct AccountLoginResponse: Decodable {
    let account_id: UUID
    let family_id: UUID
    let username: String
    let legacy: Bool
    let token: String
    let expires_at: String
}

@MainActor final class AuthenticationStore: ObservableObject {
    @Published private(set) var isAuthenticated = false
    @Published private(set) var isRestoring = true
    @Published private(set) var isLoading = false
    @Published private(set) var session: StoredFamilySession?
    @Published var errorMessage: String?
    private let credentials: any FamilySessionPersistence
    private let legacyCredentials: any FamilyCredentialPersistence
    private let client: APIClient
    private var restored = false

    init(client: APIClient = .local, credentials: any FamilySessionPersistence = FamilySessionStore.shared,
         legacyCredentials: any FamilyCredentialPersistence = BasicCredentialStore.shared) {
        self.credentials = credentials; self.legacyCredentials = legacyCredentials
        var anonymous = client; anonymous.authorizationProvider = { nil }; anonymous.timeoutInterval = 15; self.client = anonymous
        if JournalDemo.isPreview { isAuthenticated = JournalDemo.screen != "login"; isRestoring = false }
    }

    func restore() async {
        guard !restored else { return }; restored = true
        guard !JournalDemo.isPreview else { return }
        isRestoring = true
        defer { isRestoring = false }
        if let saved = credentials.load(), saved.server == client.baseURL.absoluteString {
            var authenticated = client; authenticated.authorizationProvider = { "Bearer " + saved.token }
            do {
                let identity = try await authenticated.send(path: "api/v1/auth/me", method: "GET", as: AccountIdentityResponse.self)
                guard identity.account_id == saved.accountID, identity.family_id == saved.familyID else { throw APIError.invalidResponse }
                activate(saved)
            } catch {
                if case APIError.authenticationRequired = error { credentials.clear() }
                errorMessage = "暂时无法恢复登录，请重新登录。"
            }
        } else if let previous = legacyCredentials.load() {
            await login(username: previous.username, password: previous.password)
        }
    }

    func login(username: String, password: String) async { await authenticate(username: username, password: password, registering: false) }
    func register(username: String, password: String) async { await authenticate(username: username, password: password, registering: true) }

    private func authenticate(username: String, password: String, registering: Bool) async {
        guard !isLoading else { return }
        let name = username.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        guard !name.isEmpty, !password.isEmpty else { errorMessage = "请输入账号和密码。"; return }
        errorMessage = nil
        // Preview may demonstrate existing login, but must never pretend to register an account.
        if JournalDemo.isPreview {
            if registering { errorMessage = "离线预览无法注册，请在联网版本中创建家庭账号。" }
            else { isAuthenticated = true }
            return
        }
        isLoading = true; defer { isLoading = false }
        do {
            let body = try JSONSerialization.data(withJSONObject: ["username": name, "password": password])
            let result = try await client.send(path: "api/v1/auth/" + (registering ? "register" : "login"),
                method: "POST", body: body, as: AccountLoginResponse.self)
            let value = StoredFamilySession(server: client.baseURL.absoluteString, token: result.token,
                accountID: result.account_id, familyID: result.family_id, username: result.username,
                legacy: result.legacy, expiresAt: result.expires_at)
            do {
                if value.legacy { try LegacyFamilyCacheMigration.migrate(value) }
                guard credentials.save(value) else { throw APIError.server("登录信息无法保存在这台设备上，请重试。") }
            } catch {
                var cleanup = client; cleanup.authorizationProvider = { "Bearer " + result.token }
                _ = try? await cleanup.request(path: "api/v1/auth/logout", method: "POST")
                throw error
            }
            legacyCredentials.clear()
            activate(value)
        } catch {
            if case APIError.authenticationRequired = error { errorMessage = "账号或密码不正确，请重新输入。" }
            else if case APIError.timeout = error { errorMessage = "请求超时，请稍后重试。" }
            else { errorMessage = error.localizedDescription }
        }
    }

    private func activate(_ value: StoredFamilySession) {
        FamilySessionRegistry.replace(with: value)
        URLCache.shared.removeAllCachedResponses()
        session = value
        JournalProfileAvatarStore.shared.reload()
        isAuthenticated = true
    }

    func logout() async {
        guard !isLoading else { return }
        errorMessage = nil
        if JournalDemo.isPreview { finishLogout(); return }
        guard let session else { finishLogout(); return }
        isLoading = true; defer { isLoading = false }
        var authenticated = client; authenticated.authorizationProvider = { "Bearer " + session.token }
        do {
            _ = try await authenticated.request(path: "api/v1/auth/logout", method: "POST")
            finishLogout()
        } catch {
            if case APIError.authenticationRequired = error { finishLogout() }
            else { errorMessage = "暂时无法退出登录，请检查网络后重试。" }
        }
    }

    private func finishLogout() {
        FamilySessionRegistry.replace(with: nil)
        if !JournalDemo.isPreview { credentials.clear(); legacyCredentials.clear() }
        session = nil; isAuthenticated = false
        URLCache.shared.removeAllCachedResponses()
        JournalProfileAvatarStore.shared.reload()
    }

    func handleAuthenticationFailure(_ notification: Notification) {
        guard !JournalDemo.isPreview, isAuthenticated, !isLoading, let session,
              notification.userInfo?["authorization"] as? String == "Bearer " + session.token,
              notification.userInfo?["server"] as? String == client.baseURL.absoluteString else { return }
        finishLogout(); errorMessage = "登录已失效，请重新登录。"
    }
}
