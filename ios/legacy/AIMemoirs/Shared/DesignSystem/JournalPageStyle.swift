import SwiftUI

/// 统一页面底色和滚动边缘效果，使内容与底部导航连续衔接。
extension View {
    @ViewBuilder
    fileprivate func journalBottomScrollEdge() -> some View {
        if #available(iOS 26.0, *) {
            scrollEdgeEffectHidden(true, for: .bottom)
        } else {
            self
        }
    }

    func journalPage() -> some View {
        journalBottomScrollEdge()
            .frame(maxWidth: .infinity, maxHeight: .infinity)
            .background(JournalTheme.paper.ignoresSafeArea())
            .toolbarBackground(JournalTheme.paper, for: .navigationBar)
            .toolbarBackground(.visible, for: .navigationBar)
            .toolbarColorScheme(.light, for: .navigationBar)
    }
}
