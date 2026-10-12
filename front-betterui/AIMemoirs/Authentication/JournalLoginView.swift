import SwiftUI

struct JournalLoginView: View {
    @ObservedObject var authentication: AuthenticationStore
    @State private var username = "family"
    @State private var password = JournalDemo.isPreview ? "family12" : ""
    @State private var revealsPassword = false
    @FocusState private var focusedField: Field?

    private enum Field { case username, password }

    var body: some View {
        ZStack(alignment: .top) {
            JournalBackdrop().ignoresSafeArea()
            ScrollView {
                VStack(spacing: 0) {
                    Color.clear.frame(height: 378)
                    VStack(spacing: 0) {
                        Text("拾 年 · 留 住 时 光").font(JournalTheme.font(12)).tracking(2.2).foregroundStyle(JournalTheme.muted)
                        Text("欢迎回家").font(JournalTheme.story(34)).tracking(0.7).foregroundStyle(JournalTheme.ink).padding(.top, 8)
                        Text("登录后，与家人一起收藏珍贵的回忆。").font(JournalTheme.font(14)).foregroundStyle(JournalTheme.ink2)
                            .multilineTextAlignment(.center).padding(.top, 4)

                        VStack(spacing: 0) {
                            fieldRow("家庭账号", icon: "home") {
                                TextField("", text: $username, prompt: Text("请输入账号").foregroundStyle(JournalTheme.placeholder))
                                    .textInputAutocapitalization(.never)
                                    .autocorrectionDisabled()
                                    .textContentType(.username)
                                    .accessibilityIdentifier("login.username")
                                    .focused($focusedField, equals: .username)
                                    .submitLabel(.next)
                                    .onSubmit { focusedField = .password }
                            }
                            JournalTheme.line.frame(height: 1)
                            fieldRow("家庭密码", icon: "lock") {
                                Group {
                                    if revealsPassword {
                                        TextField("", text: $password, prompt: Text("请输入密码").foregroundStyle(JournalTheme.placeholder))
                                            .textInputAutocapitalization(.never).autocorrectionDisabled()
                                    } else {
                                        SecureField("", text: $password, prompt: Text("请输入密码").foregroundStyle(JournalTheme.placeholder))
                                    }
                                }
                                .textContentType(.password)
                                .accessibilityIdentifier("login.password")
                                .focused($focusedField, equals: .password)
                                .submitLabel(.go)
                                .onSubmit { submit() }
                            } accessory: {
                                Button { revealsPassword.toggle() } label: {
                                    DesignIcon("eye").foregroundStyle(JournalTheme.muted).frame(width: 44, height: 44)
                                }.buttonStyle(.plain).accessibilityLabel(revealsPassword ? "隐藏密码" : "显示密码")
                            }
                        }
                        .padding(.horizontal, 18).padding(.vertical, 6)
                        .journalCard()
                        .padding(.top, 22)
                        .accessibilityIdentifier("login.submit")

                        if let error = authentication.errorMessage {
                            Text(error).font(JournalTheme.font(13)).foregroundStyle(JournalTheme.danger)
                                .multilineTextAlignment(.center).padding(.top, 14)
                        }

                        JournalButton(
                            title: "进入我的家庭",
                            loading: authentication.isLoading,
                            disabled: username.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || password.isEmpty,
                            action: submit
                        )
                        .padding(.top, 22)

                        HStack(spacing: 6) {
                            DesignIcon("shield", size: 14)
                            Text(JournalDemo.isPreview ? "离线设计预览，使用示例数据" : "登录后，安全访问你的家庭回忆")
                        }
                        .font(JournalTheme.font(12)).foregroundStyle(JournalTheme.muted)
                        .padding(.top, 16)
                    }
                    .padding(.horizontal, JournalTheme.gutter)
                    .padding(.bottom, 32)
                }
                .background(alignment: .top) {
                    Image("JournalWelcome").resizable().scaledToFill()
                        .frame(height: 470).frame(maxWidth: .infinity).clipped()
                        .mask(LinearGradient(stops: [.init(color: .black, location: 0.62), .init(color: .clear, location: 1)], startPoint: .top, endPoint: .bottom))
                        .accessibilityHidden(true)
                }
            }
            .scrollIndicators(.hidden)
            .ignoresSafeArea(edges: .top)
        }

    }

    /// 字段标签保留在可见文字中，图标只做装饰。
    private func fieldRow<Input: View>(_ title: String, icon: String, @ViewBuilder field: () -> Input) -> some View {
        fieldRow(title, icon: icon, field: field) { EmptyView() }
    }

    private func fieldRow<Input: View, Accessory: View>(_ title: String, icon: String, @ViewBuilder field: () -> Input, @ViewBuilder accessory: () -> Accessory) -> some View {
        HStack(spacing: 12) {
            DesignIcon(icon).foregroundStyle(JournalTheme.accent)
            VStack(alignment: .leading, spacing: 2) {
                Text(title).font(JournalTheme.font(12)).foregroundStyle(JournalTheme.muted)
                field().font(JournalTheme.font(16)).foregroundStyle(JournalTheme.ink)
            }
            Spacer(minLength: 0)
            accessory()
        }.frame(minHeight: 58)
    }

    private func submit() {
        guard !authentication.isLoading else { return }
        focusedField = nil
        Task { await authentication.login(username: username, password: password) }
    }
}
