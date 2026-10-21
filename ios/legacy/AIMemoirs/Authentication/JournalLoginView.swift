import SwiftUI

struct JournalLoginView: View {
    @ObservedObject var authentication: AuthenticationStore
    @State private var username = "family"
    @State private var password = ""
    @FocusState private var focusedField: Field?

    private enum Field { case username, password }

    var body: some View {
        ZStack {
            JournalTheme.paper.ignoresSafeArea()
            ScrollView {
                VStack(alignment: .leading, spacing: 0) {
                    Text("AI MEMORIES")
                        .font(JournalTheme.font(12, medium: true))
                        .tracking(2)
                        .foregroundStyle(JournalTheme.accent)
                    Text("欢迎回家")
                        .font(JournalTheme.story(34))
                        .foregroundStyle(JournalTheme.ink)
                        .padding(.top, 14)
                    Text("登录后，与家人一起收藏珍贵的回忆。")
                        .font(JournalTheme.font(15))
                        .foregroundStyle(JournalTheme.muted)
                        .padding(.top, 12)

                    VStack(spacing: 16) {
                        fieldLabel("家庭账号")
                        TextField("请输入账号", text: $username)
                            .textInputAutocapitalization(.never)
                            .autocorrectionDisabled()
                            .textContentType(.username)
                            .focused($focusedField, equals: .username)
                            .submitLabel(.next)
                            .onSubmit { focusedField = .password }
                            .journalLoginField()

                        fieldLabel("家庭密码")
                        SecureField("请输入密码", text: $password)
                            .textContentType(.password)
                            .focused($focusedField, equals: .password)
                            .submitLabel(.go)
                            .onSubmit { submit() }
                            .journalLoginField()
                    }
                    .padding(.top, 38)

                    if let error = authentication.errorMessage {
                        Text(error)
                            .font(JournalTheme.font(13))
                            .foregroundStyle(.red)
                            .padding(.top, 14)
                    }

                    JournalButton(
                        title: "进入我的家庭",
                        loading: authentication.isLoading,
                        disabled: username.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || password.isEmpty,
                        action: submit
                    )
                    .padding(.top, 28)

                    Label("登录信息仅保存在此设备的系统钥匙串中", systemImage: "lock.shield")
                        .font(JournalTheme.font(12))
                        .foregroundStyle(JournalTheme.muted)
                        .frame(maxWidth: .infinity)
                        .padding(.top, 24)
                }
                .padding(.horizontal, 28)
                .padding(.top, 80)
            }
        }
        .onAppear { focusedField = .username }
    }

    private func fieldLabel(_ title: String) -> some View {
        Text(title)
            .font(JournalTheme.font(13, medium: true))
            .foregroundStyle(JournalTheme.ink)
            .frame(maxWidth: .infinity, alignment: .leading)
    }

    private func submit() {
        guard !authentication.isLoading else { return }
        focusedField = nil
        Task { await authentication.login(username: username, password: password) }
    }
}

private extension View {
    func journalLoginField() -> some View {
        padding(.horizontal, 16)
            .frame(height: 54)
            .background(JournalTheme.surface, in: RoundedRectangle(cornerRadius: 14))
            .overlay(RoundedRectangle(cornerRadius: 14).stroke(JournalTheme.line, lineWidth: 1))
    }
}
