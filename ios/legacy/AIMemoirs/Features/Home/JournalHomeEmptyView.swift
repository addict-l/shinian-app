import SwiftUI

/// 首页空状态区分首次添加家人和已有家人尚未记录的场景。
struct JournalHomeEmptyView: View {
    let hasPeople: Bool
    var minimumHeight: CGFloat = 0
    let onAction: () -> Void

    var body: some View {
        JournalWelcomeEmptyView(symbol: "book.closed",
            title: hasPeople ? "第一段回忆，慢慢说" : "把想念的人，写进第一页",
            message: hasPeople ? "一个熟悉的声音，一顿家常饭。\n从你此刻想起的小事开始。" : "先记下家人的名字，\n再留住那些平凡又珍贵的瞬间。",
            actionTitle: hasPeople ? "记录第一段回忆" : "添加第一位家人",
            actionID: "home.newMemory", minimumHeight: minimumHeight, onAction: onAction)
            .accessibilityElement(children: .contain)
            .accessibilityIdentifier("home.empty")
    }
}
