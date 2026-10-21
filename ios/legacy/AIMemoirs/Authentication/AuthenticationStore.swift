import SwiftUI

@MainActor
final class AuthenticationStore: ObservableObject {
    @Published private(set) var isAuthenticated: Bool
    @Published private(set) var isLoading = false
    @Published var errorMessage: String?

    private let credentials = BasicCredentialStore.shared

    init() {
        isAuthenticated = credentials.load() != nil
    }

    func login(username: String, password: String) async {
        let username = username.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !username.isEmpty, !password.isEmpty else {
            errorMessage = "请输入账号和密码。"
            return
        }

        isLoading = true
        errorMessage = nil
        let previous = credentials.load()
        guard credentials.save(FamilyCredentials(username: username, password: password)) else {
            isLoading = false
            errorMessage = "无法安全保存登录信息，请重试。"
            return
        }

        do {
            _ = try await APIClient.local.send(
                path: "health",
                method: "GET",
                as: LoginHealthResponse.self
            )
            isAuthenticated = true
        } catch {
            if let previous { _ = credentials.save(previous) } else { credentials.clear() }
            errorMessage = "账号或密码不正确，或服务器暂时无法连接。"
        }
        isLoading = false
    }

    func logout() {
        credentials.clear()
        errorMessage = nil
        isAuthenticated = false
    }
}

private struct LoginHealthResponse: Decodable {
    let status: String
}
