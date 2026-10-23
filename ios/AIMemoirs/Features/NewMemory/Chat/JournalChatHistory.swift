import SwiftUI
import Observation

@MainActor @Observable
final class JournalChatAutoFollow {
    var following = true
    var atBottom = true
    private(set) var request = 0

    func resume() {
        following = true
        request += 1
    }
}

private struct ChatViewport: Equatable {
    let contentHeight: CGFloat
    let viewportHeight: CGFloat
    let bottomGap: CGFloat

    init(_ geometry: ScrollGeometry) {
        contentHeight = geometry.contentSize.height
        viewportHeight = geometry.containerSize.height
        // ScrollPosition's edge already accounts for safe areas; do not count their insets twice.
        bottomGap = max(0, geometry.contentSize.height - geometry.contentOffset.y - geometry.containerSize.height)
    }

    var atBottom: Bool { bottomGap <= 20 }
}

/// Follow actual layout changes, including the keyboard and asynchronously sized photos.
/// A user's drag takes precedence until they return to the bottom or explicitly resume.
struct JournalChatHistory<Content: View>: View {
    let follow: JournalChatAutoFollow
    let identifier: String
    @ViewBuilder var content: () -> Content
    @State private var position = ScrollPosition(edge: .bottom)
    @State private var phase = ScrollPhase.idle
    @State private var scrollTask: Task<Void, Never>?

    private var userScrolling: Bool {
        phase == .tracking || phase == .interacting || phase == .decelerating
    }

    var body: some View {
        ScrollView {
            content()
        }
        .scrollIndicators(.hidden)
        .scrollDismissesKeyboard(.interactively)
        .defaultScrollAnchor(.bottom, for: .initialOffset)
        // Following the newest message must not bottom-align a short conversation.
        .defaultScrollAnchor(.top, for: .alignment)
        .scrollPosition($position)
        .accessibilityIdentifier(identifier)
        .accessibilityValue(follow.atBottom ? "最新消息" : "历史消息")
        .onScrollGeometryChange(for: ChatViewport.self) { ChatViewport($0) } action: { _, viewport in
            follow.atBottom = viewport.atBottom
            if !userScrolling && phase == .idle && viewport.atBottom { follow.following = true }
            if follow.following && !userScrolling && phase == .idle && viewport.bottomGap > 1 {
                scrollToBottom()
            }
        }
        .onScrollPhaseChange { _, next in
            phase = next
            if next == .interacting {
                follow.following = false
                scrollTask?.cancel()
            } else if next == .idle {
                if follow.atBottom { follow.following = true }
                if follow.following { scrollToBottom() }
            }
        }
        .onChange(of: follow.request) { _, _ in scrollToBottom() }
        .onAppear { scrollToBottom() }
        .onDisappear { scrollTask?.cancel() }
        .overlay(alignment: .bottomTrailing) {
            if !follow.following && !follow.atBottom {
                Button(action: follow.resume) {
                    Label("回到最新", systemImage: "arrow.down")
                        .font(JournalTheme.font(14, medium: true))
                        .padding(.horizontal, 14).frame(minHeight: 44)
                        .background(JournalTheme.surface, in: Capsule())
                        .overlay { Capsule().stroke(JournalTheme.line, lineWidth: 1) }
                }
                .buttonStyle(.plain).foregroundStyle(JournalTheme.accentDeep)
                .accessibilityIdentifier(identifier + ".latest")
                .padding(12)
            }
        }
    }

    private func scrollToBottom() {
        scrollTask?.cancel()
        scrollTask = Task { @MainActor in
            await Task.yield()
            guard !Task.isCancelled, follow.following, !userScrolling else { return }
            var transaction = Transaction()
            transaction.disablesAnimations = true
            withTransaction(transaction) { position.scrollTo(edge: .bottom) }
        }
    }
}
