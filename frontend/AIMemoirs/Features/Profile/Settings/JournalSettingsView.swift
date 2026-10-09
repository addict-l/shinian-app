import SwiftUI

/// 设置页面：显示名称使用本机 AppStorage 保存。
struct JournalSettingsView: View {
    @AppStorage("journal.displayName") private var name = "回忆的收藏者"
    @EnvironmentObject private var authentication: AuthenticationStore
    
    var body: some View {
        Form {
            Section("个人展示") { TextField("显示名称", text: $name) }
            Section("家庭胶片") { Text("每位家人拥有自己的胶卷，左右滑动翻阅回忆。点击“查看全部家人”可搜索和浏览所有胶卷，长按人物头像可以更换照片。") }
            Section {
                Button("退出家庭账号", role: .destructive) { authentication.logout() }
            }
            Section { Text("拾年 · 留住时光\n界面版本 V1").foregroundStyle(JournalTheme.muted) }
        }.scrollContentBackground(.hidden).journalPage().navigationTitle("设置").navigationBarTitleDisplayMode(.inline)
            .toolbar(.visible, for: .navigationBar)
    }
}
