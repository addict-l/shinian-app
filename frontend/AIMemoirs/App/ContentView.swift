import SwiftUI

struct ContentView: View {
    @StateObject private var authentication = AuthenticationStore()

    var body: some View {
        Group {
            if authentication.isAuthenticated {
                JournalAppView()
            } else {
                JournalLoginView(authentication: authentication)
            }
        }
        .environmentObject(authentication)
    }
}

#Preview { ContentView() }
