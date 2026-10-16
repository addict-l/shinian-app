import SwiftUI

struct JournalLoginView: View {
    @Environment(\.verticalSizeClass) private var verticalSizeClass
    @ObservedObject var authentication: AuthenticationStore
    @State private var username = JournalDemo.isPreview ? "family" : ""
    @State private var password = JournalDemo.isPreview ? "family12" : ""
    @State private var submitted = false
    @State private var showsRegistration = false
    @State private var showsAccountHelp = false
    @FocusState private var focusedField: JournalAuthFieldID?

    private var usernameError: String? {
        submitted && username.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty ? "请输入家庭账号。" : nil
    }
    private var passwordError: String? { submitted && password.isEmpty ? "请输入密码。" : nil }

    var body: some View {
        NavigationStack {
            JournalAuthPage(title: "欢迎回家", subtitle: "把平凡的日子，收藏成家的故事。", focusedField: focusedField) {
                VStack(spacing: 18) {
                    VStack(spacing: 16) {
                        JournalAuthField(title: "家庭账号", placeholder: "请输入家庭账号", icon: "home",
                            text: $username, field: .username, focus: $focusedField, error: usernameError,
                            identifier: "login.username", submitLabel: .next) { focusedField = .password }
                        JournalAuthField(title: "密码", placeholder: "请输入密码", icon: "lock",
                            text: $password, field: .password, focus: $focusedField, error: passwordError,
                            identifier: "login.password", secure: true, submitLabel: .go, onSubmit: submit)
                    }
                    .disabled(authentication.isLoading)

                    Button("账号或密码需要帮助？") { focusedField = nil; showsAccountHelp = true }
                        .font(JournalTheme.font(13)).foregroundStyle(JournalTheme.ink2)
                        .frame(minHeight: 44).frame(maxWidth: .infinity, alignment: .trailing)
                        .buttonStyle(.plain).padding(.top, -12)
                        .disabled(authentication.isLoading).accessibilityIdentifier("login.help")

                    if let error = authentication.errorMessage {
                        JournalAuthNotice(error, isError: true).accessibilityIdentifier("login.error")
                    }

                    JournalAuthButton(title: authentication.isLoading ? "正在登录…" : "登录",
                        loading: authentication.isLoading, action: submit)
                        .accessibilityIdentifier("login.submit")

                    Button {
                        focusedField = nil
                        authentication.errorMessage = nil
                        showsRegistration = true
                    } label: {
                        (Text("还没有账号？ ").foregroundStyle(JournalTheme.ink2)
                         + Text("去注册").foregroundStyle(JournalTheme.authAccent).bold())
                            .font(JournalTheme.font(15)).frame(minHeight: 44)
                    }
                    .buttonStyle(.plain).disabled(authentication.isLoading)
                    .accessibilityIdentifier("login.register")

                    Label(JournalDemo.isPreview ? "离线设计预览 · 使用示例数据" : "一家人的回忆，在这里好好珍藏", systemImage: "lock.shield")
                        .font(JournalTheme.font(12)).foregroundStyle(JournalTheme.ink2)
                        .multilineTextAlignment(.center)
                }
            }
            .toolbar(.hidden, for: .navigationBar)
            .toolbar {
                if !showsRegistration && verticalSizeClass != .compact {
                    ToolbarItemGroup(placement: .keyboard) {
                        Spacer()
                        Button("完成") { focusedField = nil }.tint(JournalTheme.authAccent)
                    }
                }
            }
            .onChange(of: username) { authentication.errorMessage = nil }
            .onChange(of: password) { authentication.errorMessage = nil }
            .navigationDestination(isPresented: $showsRegistration) { JournalRegistrationView() }
            .alert("找回家庭账号", isPresented: $showsAccountHelp) {
                Button("知道了", role: .cancel) { }
            } message: {
                Text("当前使用家庭共享账号。请向为你开通账号的人确认账号或重置密码，再回来登录。")
            }
        }
        .tint(JournalTheme.authAccent)
    }

    private func submit() {
        guard !authentication.isLoading else { return }
        submitted = true
        if usernameError != nil { focusedField = .username; return }
        if passwordError != nil { focusedField = .password; return }
        focusedField = nil
        Task { await authentication.login(username: username, password: password) }
    }
}
