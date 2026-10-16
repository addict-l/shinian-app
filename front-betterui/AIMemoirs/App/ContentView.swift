import SwiftUI

struct ContentView: View {
    @StateObject private var authentication = AuthenticationStore()
    var body: some View {
        Group {
            if authentication.isRestoring {
                ProgressView("正在恢复家庭登录…").frame(maxWidth: .infinity, maxHeight: .infinity)
                    .background(JournalTheme.paper)
            } else if authentication.isAuthenticated { JournalAppView().id(authentication.session?.token ?? "preview") }
            else { JournalLoginView(authentication: authentication) }
        }
        .onReceive(NotificationCenter.default.publisher(for: .journalAuthenticationRequired)) { authentication.handleAuthenticationFailure($0) }
        .task { await authentication.restore() }
        .environmentObject(authentication)
        .environment(\.locale, Locale(identifier: "zh_CN"))
        .tint(JournalTheme.accent)
        .preferredColorScheme(.light)
    }
}

#Preview { ContentView() }
