import SwiftUI

private struct LoginHealthResponse: Decodable { let status: String }

/// 登录成功后才进入家庭；设备使用 Keychain，模拟器使用独立的本机凭据存储。
@MainActor final class AuthenticationStore: ObservableObject {
    @Published private(set) var isAuthenticated: Bool
    @Published private(set) var isLoading = false
    @Published var errorMessage: String?
    private let credentials: any FamilyCredentialPersistence
    private let client: APIClient

    init(client: APIClient = .local, credentials: any FamilyCredentialPersistence = BasicCredentialStore.shared) {
        self.credentials = credentials
        var authenticatedClient = client
        authenticatedClient.authorizationProvider = { credentials.authorizationHeader }
        self.client = authenticatedClient
        isAuthenticated = JournalDemo.isPreview
            ? JournalDemo.screen != "login"
            : credentials.load() != nil
    }

    func login(username: String, password: String) async {
        guard !isLoading else { return }
        let name = username.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !name.isEmpty, !password.isEmpty else {
            errorMessage = "请输入账号和密码。"; return
        }
        errorMessage = nil
        if JournalDemo.isPreview { isAuthenticated = true; return }
        isLoading = true
        defer { isLoading = false }
        let previous = credentials.load()
        guard credentials.save(FamilyCredentials(username: name, password: password)) else {
            errorMessage = "登录信息无法保存在这台设备上，请重试。"; return
        }
        do {
            let health = try await client.send(path: "health", method: "GET", as: LoginHealthResponse.self)
            guard health.status == "ok" else { throw APIError.server("服务器暂时无法连接。") }
            isAuthenticated = true
        } catch {
            if let previous { credentials.save(previous) } else { credentials.clear() }
            if case APIError.authenticationRequired = error {
                errorMessage = "账号或密码不正确，请重新输入。"
            } else if case APIError.timeout = error {
                errorMessage = "登录超时，请检查网络后重试。"
            } else { errorMessage = error.localizedDescription }
        }
    }

    func logout() {
        if !JournalDemo.isPreview { credentials.clear() }
        errorMessage = nil; isAuthenticated = false
    }

    func handleAuthenticationFailure(_ notification: Notification) {
        // 忽略旧账号尚未完成的请求，避免退出刚刚登录的新账号。
        guard !JournalDemo.isPreview, isAuthenticated, !isLoading,
              let authorization = notification.userInfo?["authorization"] as? String,
              authorization == credentials.authorizationHeader,
              notification.userInfo?["server"] as? String == client.baseURL.absoluteString else { return }
        logout()
        errorMessage = "登录已失效，请重新登录。"
    }
}
