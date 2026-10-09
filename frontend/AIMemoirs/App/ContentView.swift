import SwiftUI

struct ContentView: View {
    @StateObject private var authentication = AuthenticationStore()

    var body: some View {
        Group {
            #if DEBUG
            if ProcessInfo.processInfo.environment["AI_MEMORIES_DESIGN_SCREEN"] != nil {
                // This entry assembles only JournalPreviewAPI fixtures, never the live backend.
                JournalAppView()
            } else { authenticatedContent }
            #else
            authenticatedContent
            #endif
        }
        .environmentObject(authentication)
    }
    @ViewBuilder private var authenticatedContent: some View {
        if authentication.isAuthenticated { JournalAppView() }
        else { JournalLoginView(authentication: authentication) }
    }
}

#Preview { ContentView() }
