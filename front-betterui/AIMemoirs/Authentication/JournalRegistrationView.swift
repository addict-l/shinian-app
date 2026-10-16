import SwiftUI

/// 注册表单预备界面：只校验本机输入，不发送请求、保存密码或创建账号。
struct JournalRegistrationView: View {
    @Environment(\.dismiss) private var dismiss
    @Environment(\.verticalSizeClass) private var verticalSizeClass
    @State private var username = ""
    @State private var password = ""
    @State private var confirmation = ""
    @State private var submitted = false
    @State private var showsUnavailable = false
    @FocusState private var focusedField: JournalAuthFieldID?

    private var usernameError: String? {
        submitted && username.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty ? "请填写家庭账号。" : nil
    }
    private var passwordError: String? {
        guard submitted else { return nil }
        if password.isEmpty { return "请设置密码。" }
        if password.count < 8 { return "密码至少需要 8 位。" }
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
            compact: true, focusedField: focusedField) {
            VStack(spacing: 16) {
                JournalAuthNotice("自助注册尚未开放。已有家庭账号，可直接返回登录。")
                    .accessibilityIdentifier("register.notice")
                VStack(spacing: 16) {
                    JournalAuthField(title: "家庭账号", placeholder: "为家庭取一个账号", icon: "home",
                        text: $username, field: .username, focus: $focusedField, error: usernameError,
                        identifier: "register.username", submitLabel: .next) { focusedField = .password }
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
                JournalAuthButton(title: "注册", action: submit).accessibilityIdentifier("register.submit")
                Button {
                    focusedField = nil
                    dismiss()
                } label: {
                    (Text("已有账号？ ").foregroundStyle(JournalTheme.ink2)
                     + Text("返回登录").foregroundStyle(JournalTheme.authAccent).bold())
                        .font(JournalTheme.font(15)).frame(minHeight: 44)
                }
                .buttonStyle(.plain).accessibilityIdentifier("register.login")
            }
        }
        .navigationTitle("创建账号").navigationBarTitleDisplayMode(.inline)
        .toolbar(.visible, for: .navigationBar)
        .toolbarBackground(JournalTheme.paper, for: .navigationBar)
        .toolbar {
            if verticalSizeClass != .compact {
                ToolbarItemGroup(placement: .keyboard) {
                    Spacer()
                    Button("完成") { focusedField = nil }.tint(JournalTheme.authAccent)
                }
            }
        }
        .alert("自助注册尚未开放", isPresented: $showsUnavailable) {
            Button("返回登录") { dismiss() }
            Button("继续查看", role: .cancel) { }
        } message: {
            Text("填写内容已通过检查，但当前还不能创建账号。账号未创建，填写的密码也未保存。已有家庭账号可直接登录。")
        }
    }

    private func submit() {
        submitted = true
        if usernameError != nil { focusedField = .username; return }
        if passwordError != nil { focusedField = .password; return }
        if confirmationError != nil { focusedField = .confirmation; return }
        focusedField = nil
        showsUnavailable = true
    }
}
