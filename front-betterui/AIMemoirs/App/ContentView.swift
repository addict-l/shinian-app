import SwiftUI

struct ContentView: View {
    @StateObject private var authentication = AuthenticationStore()
    var body: some View {
        Group {
            if authentication.isAuthenticated { JournalAppView() }
            else { JournalLoginView(authentication: authentication) }
        }
        .onReceive(NotificationCenter.default.publisher(for: .journalAuthenticationRequired)) { authentication.handleAuthenticationFailure($0) }
        .environmentObject(authentication)
        .environment(\.locale, Locale(identifier: "zh_CN"))
        .tint(JournalTheme.accent)
        .preferredColorScheme(.light)
    }
}

#Preview { ContentView() }
