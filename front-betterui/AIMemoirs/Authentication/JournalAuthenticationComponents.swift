import SwiftUI

enum JournalAuthFieldID: Hashable { case username, password, confirmation }

/// 两个认证页面共用暖纸布局；大字和键盘出现时，插画让位给表单。
struct JournalAuthPage<Content: View>: View {
    let title: String
    let subtitle: String
    var compact = false
    let focusedField: FocusState<JournalAuthFieldID?>.Binding
    @ViewBuilder let content: () -> Content
    @Environment(\.dynamicTypeSize) private var dynamicType
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    var body: some View {
        GeometryReader { geometry in
            ScrollViewReader { scroll in
                ScrollView {
                    VStack(spacing: 0) {
                        Image("JournalWelcome")
                            .resizable().scaledToFill()
                            .frame(width: min(geometry.size.width, 600), height: artworkHeight(geometry.size))
                            .clipped()
                            .mask(LinearGradient(stops: [.init(color: .clear, location: 0),
                                .init(color: .black, location: 0.12), .init(color: .black, location: 0.58),
                                .init(color: .clear, location: 1)], startPoint: .top, endPoint: .bottom))
                            .accessibilityHidden(true)
                        VStack(spacing: 24) {
                            VStack(spacing: 10) {
                                Text("拾年 · 留住时光")
                                    .font(JournalTheme.font(12, medium: true)).tracking(2)
                                    .foregroundStyle(JournalTheme.ink2)
                                Text(title).font(JournalTheme.story(32)).foregroundStyle(JournalTheme.ink)
                                    .accessibilityAddTraits(.isHeader)
                                Text(subtitle).font(JournalTheme.font(14)).foregroundStyle(JournalTheme.ink2)
                            }
                            .multilineTextAlignment(.center).fixedSize(horizontal: false, vertical: true)
                            content()
                        }
                        .padding(.horizontal, JournalTheme.gutter).frame(maxWidth: 480)
                        .padding(.top, -8).padding(.bottom, 28)
                    }
                    .frame(maxWidth: .infinity)
                    .frame(minHeight: geometry.size.height, alignment: .top)
                    .background {
                        Color.clear.contentShape(Rectangle())
                            .onTapGesture { focusedField.wrappedValue = nil }
                    }
                }
                .scrollIndicators(.hidden).scrollDismissesKeyboard(.interactively).clipped()
                .onChange(of: focusedField.wrappedValue) { scrollToFocusedField(using: scroll) }
                .onChange(of: geometry.size.height) { scrollToFocusedField(using: scroll) }
            }
        }
        .background(JournalBackdrop().ignoresSafeArea())
    }

    private func artworkHeight(_ size: CGSize) -> CGFloat {
        if dynamicType.isAccessibilitySize { return 72 }
        return min(compact ? 112 : 240, max(72, size.height * (compact ? 0.18 : 0.32)))
    }

    private func scrollToFocusedField(using scroll: ScrollViewProxy) {
        guard let field = focusedField.wrappedValue else { return }
        withAnimation(reduceMotion ? nil : .easeInOut(duration: 0.2)) {
            scroll.scrollTo(field, anchor: .center)
        }
    }
}

struct JournalAuthField: View {
    let title: String
    let placeholder: String
    let icon: String
    @Binding var text: String
    let field: JournalAuthFieldID
    let focus: FocusState<JournalAuthFieldID?>.Binding
    var error: String?
    let identifier: String
    var secure = false
    var newPassword = false
    let submitLabel: SubmitLabel
    let onSubmit: () -> Void
    @State private var revealsPassword = false

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(title).font(JournalTheme.font(13, medium: true)).foregroundStyle(JournalTheme.ink2)
            HStack(spacing: 12) {
                DesignIcon(icon, size: 20).foregroundStyle(JournalTheme.authAccent).accessibilityHidden(true)
                Group {
                    if secure && !revealsPassword {
                        SecureField(title, text: $text, prompt: Text(placeholder).foregroundStyle(JournalTheme.ink2))
                    } else {
                        TextField(title, text: $text, prompt: Text(placeholder).foregroundStyle(JournalTheme.ink2))
                    }
                }
                .font(JournalTheme.font(16)).foregroundStyle(JournalTheme.ink)
                .textInputAutocapitalization(.never).autocorrectionDisabled()
                .keyboardType(secure ? .asciiCapable : .default)
                .textContentType(secure ? (newPassword ? .newPassword : .password) : .username)
                .focused(focus, equals: field).submitLabel(submitLabel).onSubmit(onSubmit)
                .accessibilityIdentifier(identifier).accessibilityHint(error ?? "")
                .padding(.vertical, 16)
                if secure {
                    Button {
                        revealsPassword.toggle()
                        focus.wrappedValue = field
                    } label: {
                        Image(systemName: revealsPassword ? "eye.slash" : "eye")
                            .font(.system(size: 18)).foregroundStyle(JournalTheme.ink2)
                            .frame(width: 44, height: 44)
                    }
                    .buttonStyle(.plain)
                    .accessibilityLabel(revealsPassword ? "隐藏\(title)" : "显示\(title)")
                    .accessibilityIdentifier(identifier + ".visibility")
                }
            }
            .padding(.leading, 16).padding(.trailing, secure ? 6 : 16).frame(minHeight: 56)
            .background(JournalTheme.surface, in: RoundedRectangle(cornerRadius: 16))
            .overlay {
                RoundedRectangle(cornerRadius: 16)
                    .stroke(error != nil ? JournalTheme.danger : focus.wrappedValue == field ? JournalTheme.authAccent : JournalTheme.cardBorder,
                        lineWidth: error != nil || focus.wrappedValue == field ? 1.5 : 1)
            }
            if let error {
                Label(error, systemImage: "exclamationmark.circle")
                    .font(JournalTheme.font(12)).foregroundStyle(JournalTheme.ink)
                    .fixedSize(horizontal: false, vertical: true)
                    .accessibilityIdentifier(identifier + ".error")
            }
        }
        .id(field)
    }
}

struct JournalAuthButton: View {
    let title: String
    var loading = false
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            HStack(spacing: 10) {
                if loading { ProgressView().tint(.white) }
                Text(title).font(JournalTheme.font(16, medium: true))
            }
            .padding(.horizontal, 20).padding(.vertical, 16)
            .frame(maxWidth: .infinity).frame(minHeight: 56)
            .foregroundStyle(.white).background(JournalTheme.authAccent, in: Capsule())
        }
        .buttonStyle(JournalAuthButtonStyle()).disabled(loading)
    }
}

private struct JournalAuthButtonStyle: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View {
        configuration.label.opacity(configuration.isPressed ? 0.8 : 1)
    }
}

struct JournalAuthNotice: View {
    let message: String
    var isError = false
    init(_ message: String, isError: Bool = false) { self.message = message; self.isError = isError }

    var body: some View {
        Label(message, systemImage: isError ? "exclamationmark.circle" : "info.circle")
            .font(JournalTheme.font(13)).foregroundStyle(JournalTheme.ink2)
            .fixedSize(horizontal: false, vertical: true)
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(14).background(JournalTheme.soft.opacity(0.6), in: RoundedRectangle(cornerRadius: 14))
            .accessibilityElement(children: .combine)
    }
}
