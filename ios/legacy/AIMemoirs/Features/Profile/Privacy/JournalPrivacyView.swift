import SwiftUI

/// 隐私与数据说明页面，明确当前服务器数据及本机头像的保存方式。
struct JournalPrivacyView: View {
    var body: some View {
        Form {
            Section("回忆数据") {
                Text("人物与回忆通过当前配置的服务器保存。卸载 App 不会自动删除服务器上的记录。")
                Text("只有点击“保存这段回忆”后，草稿才会成为正式回忆。")
            }
            Section("照片与 AI 对话") {
                Text("你选择的照片会作为回忆附件上传。聊天内容会发送至服务器配置的 AI 服务，用于整理回忆。")
                Text("照片选择使用系统照片选择器，无需开放整个相册。")
                Text("家庭胶片中的人物头像保存在这台设备上，不会自动上传或同步。")
            }
            Section("数据管理") { Text("批量导出、删除和账号权限管理尚未接入当前服务端接口。").foregroundStyle(JournalTheme.muted) }
        }.font(JournalTheme.font(15)).scrollContentBackground(.hidden).journalPage()
            .navigationTitle("隐私与数据").navigationBarTitleDisplayMode(.inline).toolbar(.visible, for: .navigationBar)
    }
}
