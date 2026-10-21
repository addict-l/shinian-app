import SwiftUI

/// 注册成功后进入服务端新建的独立家庭。
struct JournalRegistrationView: View {
    @ObservedObject var authentication: AuthenticationStore
    @Environment(\.dismiss) private var dismiss
    @State private var username = ""
    @State private var password = ""
    @State private var confirmation = ""
    @State private var submitted = false
    @FocusState private var focusedField: JournalAuthFieldID?

    private var usernameError: String? {
        guard submitted else { return nil }
        let value = username.trimmingCharacters(in: .whitespacesAndNewlines)
        if value.isEmpty { return "请填写家庭账号。" }
        return value.range(of: "^[A-Za-z0-9_]{3,32}$", options: .regularExpression) == nil
            ? "账号须为 3–32 位字母、数字或下划线。" : nil
    }
    private var passwordError: String? {
        guard submitted else { return nil }
        if password.isEmpty { return "请设置密码。" }
        if password.count < 8 || password.count > 128 { return "密码需要 8–128 位。" }
        if password.allSatisfy(\.isWhitespace) { return "密码不能只包含空格。" }
        return nil
    }
    private var confirmationError: String? {
        guard submitted else { return nil }
        if confirmation.isEmpty { return "请再次输入密码。" }
        return confirmation != password ? "两次输入的密码不一致。" : nil
    }

    var body: some View {
        JournalAuthPage(title: "开启家庭回忆", subtitle: "从今天起，一起留下值得珍藏的时光。",
            compact: true, focusedField: $focusedField) {
            VStack(spacing: 16) {
                JournalAuthNotice("一家人共用一个账号，在各自的设备上记录和查看家庭回忆。")
                    .accessibilityIdentifier("register.notice")
                VStack(spacing: 16) {
                    JournalAuthField(title: "家庭账号", placeholder: "为家庭取一个账号", icon: "home",
                        text: $username, field: .username, focus: $focusedField, error: usernameError,
                        identifier: "register.username", submitLabel: .next) { focusedField = .password }
                    Text("3–32 位字母、数字或下划线，不区分大小写。")
                        .font(JournalTheme.font(12)).foregroundStyle(JournalTheme.ink2)
                    VStack(alignment: .leading, spacing: 7) {
                        JournalAuthField(title: "设置密码", placeholder: "至少 8 位密码", icon: "lock",
                            text: $password, field: .password, focus: $focusedField, error: passwordError,
                            identifier: "register.password", secure: true, newPassword: true,
                            submitLabel: .next) { focusedField = .confirmation }
                        if passwordError == nil {
                            Text("建议组合使用字母、数字和符号。")
                                .font(JournalTheme.font(12)).foregroundStyle(JournalTheme.ink2)
                        }
                    }
                    JournalAuthField(title: "确认密码", placeholder: "请再次输入密码", icon: "lock",
                        text: $confirmation, field: .confirmation, focus: $focusedField, error: confirmationError,
                        identifier: "register.confirmation", secure: true, newPassword: true,
                        submitLabel: .done, onSubmit: submit)
                }
                .disabled(authentication.isLoading)
                if let error = authentication.errorMessage {
                    JournalAuthNotice(error, isError: true).accessibilityIdentifier("register.error")
                }
                JournalAuthButton(title: authentication.isLoading ? "正在创建家庭…" : "注册并进入家庭",
                    loading: authentication.isLoading, action: submit).accessibilityIdentifier("register.submit")
                Button {
                    focusedField = nil
                    dismiss()
                } label: {
                    (Text("已有账号？ ").foregroundStyle(JournalTheme.ink2)
                     + Text("返回登录").foregroundStyle(JournalTheme.authAccent).bold())
                        .font(JournalTheme.font(15)).frame(minHeight: 44)
                }
                .buttonStyle(.plain).disabled(authentication.isLoading).accessibilityIdentifier("register.login")
            }
        }
        .navigationTitle("创建账号").navigationBarTitleDisplayMode(.inline)
        .toolbar(.visible, for: .navigationBar)
        .toolbarBackground(JournalTheme.paper, for: .navigationBar)
        .onChange(of: username) { authentication.errorMessage = nil }
        .onChange(of: password) { authentication.errorMessage = nil }
        .onChange(of: confirmation) { authentication.errorMessage = nil }
        .onDisappear { authentication.errorMessage = nil }
    }

    private func submit() {
        guard !authentication.isLoading else { return }
        submitted = true
        if usernameError != nil { focusedField = .username; return }
        if passwordError != nil { focusedField = .password; return }
        if confirmationError != nil { focusedField = .confirmation; return }
        focusedField = nil
        Task { await authentication.register(username: username, password: password) }
    }
}
