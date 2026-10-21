import SwiftUI

/// 可复用的左滑删除交互，与页面的删除请求和确认流程分离。
extension View {
    /// 左滑露出右侧删除按钮；横向滑动时不触发行点击。
    func journalSwipeDelete(initiallyRevealed: Bool = false, onSelect: @escaping () -> Void, onDelete: @escaping () -> Void) -> some View {
        modifier(JournalSwipeDeleteModifier(initiallyRevealed: initiallyRevealed, onSelect: onSelect, onDelete: onDelete))
    }
}

private struct JournalSwipeDeleteModifier: ViewModifier {
    let onSelect: () -> Void
    let onDelete: () -> Void
    @State private var offset: CGFloat = 0
    @State private var isSwiping = false
    private let reveal: CGFloat = 84
    init(initiallyRevealed: Bool, onSelect: @escaping () -> Void, onDelete: @escaping () -> Void) {
        self.onSelect = onSelect; self.onDelete = onDelete
        _offset = State(initialValue: initiallyRevealed ? -84 : 0)
    }
    private var isOpen: Bool { offset < -8 }

    func body(content: Content) -> some View {
        ZStack(alignment: .trailing) {
            RoundedRectangle(cornerRadius: JournalTheme.cardRadius, style: .continuous).fill(JournalTheme.swipeDelete)
                .opacity(offset < 0 ? 1 : 0)
            Button {
                withAnimation(.easeOut(duration: 0.18)) { offset = 0 }
                onDelete()
            } label: {
                VStack(spacing: 2) {
                    DesignIcon("trash", size: 20)
                    Text("删除").font(JournalTheme.font(12))
                }
                .foregroundStyle(.white)
                .frame(width: reveal)
                .frame(maxHeight: .infinity)
                .contentShape(Rectangle())
            }
            .buttonStyle(.plain)
            .opacity(offset < 0 ? 1 : 0)
            .accessibilityLabel("删除")
            .allowsHitTesting(isOpen)
            .zIndex(isOpen ? 2 : 0)

            content
                .padding(.trailing, -offset)
                .allowsHitTesting(!isOpen)
                .contentShape(Rectangle())
                .onTapGesture {
                    guard !isSwiping, !isOpen else { return }
                    onSelect()
                }
                .zIndex(1)
        }
        .contentShape(Rectangle())
        .accessibilityAddTraits(.isButton)
        .accessibilityAction(named: "选择人物", onSelect)
        .accessibilityAction(named: "删除人物", onDelete)
        .simultaneousGesture(
            DragGesture(minimumDistance: 12, coordinateSpace: .local)
                .onChanged { value in
                    let dx = value.translation.width
                    let dy = value.translation.height
                    guard abs(dx) > abs(dy) else { return }
                    isSwiping = true
                    if offset < 0 || dx < 0 {
                        offset = max(-reveal, min(0, dx < 0 ? dx : -reveal + dx))
                    } else if offset < 0 {
                        offset = min(0, -reveal + dx)
                    }
                }
                .onEnded { value in
                    let dx = value.translation.width
                    let dy = value.translation.height
                    withAnimation(.easeOut(duration: 0.18)) {
                        if abs(dx) >= abs(dy), dx < -reveal / 2 || value.predictedEndTranslation.width < -reveal {
                            offset = -reveal
                        } else if offset < -reveal / 2 {
                            offset = -reveal
                        } else {
                            offset = 0
                        }
                    }
                    DispatchQueue.main.asyncAfter(deadline: .now() + 0.25) {
                        isSwiping = false
                    }
                }
        )
    }
}
