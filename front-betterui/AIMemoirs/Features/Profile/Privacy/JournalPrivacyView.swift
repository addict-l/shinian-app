import SwiftUI

/// 当前功能的数据去向说明。
struct JournalPrivacyView: View {
    var body: some View {
        VStack(spacing: 0) {
            JournalBackBar(title: "隐私与数据")
            ScrollView {
                VStack(spacing: 0) {
                    HStack(spacing: 12) {
                        DesignIcon("shield").foregroundStyle(JournalTheme.sageInk)
                            .frame(width: 46, height: 46).background(.white, in: Circle())
                        VStack(alignment: .leading, spacing: 4) {
                            Text("你的回忆，只属于你的家。").font(JournalTheme.story(16)).foregroundStyle(Color(hex: 0x4D5E41))
                            Text("只有点击“保存这段回忆”后，草稿才会成为正式回忆。")
                                .font(JournalTheme.font(12.5)).foregroundStyle(Color(hex: 0x6E8160)).lineSpacing(5)
                        }
                    }.frame(maxWidth: .infinity, alignment: .leading).padding(18)
                        .background(JournalTheme.sageSoft, in: RoundedRectangle(cornerRadius: 24))
                    card("照片与 AI 对话", icon: "image", paragraphs: [
                        "照片选择使用系统照片选择器，无需开放整个相册。",
                        "对话文字由服务器调用 AI 整理。照片上传到家庭服务器，用于聊天展示、回忆和回忆录，不发送给 AI 分析。"
                    ]).padding(.top, 14)
                    card("回忆数据", icon: "heart", paragraphs: [
                        "人物和已保存回忆通过家庭账号同步到服务器。草稿需经你确认保存，才会出现在回忆列表中。",
                        "尚未发送的对话、制作缓存、显示名称和人物头像保存在本机；头像不会自动上传或同步。"
                    ]).padding(.top, 12)
                    card("数据管理", icon: "gear", paragraphs: [
                        "可在人物列表和回忆详情中删除相应记录；回忆录支持 PDF 预览与导出。批量导出和账号权限管理暂无服务端接口。"
                    ]).padding(.top, 12)
                }.padding(.horizontal, JournalTheme.gutter).padding(.top, 6).padding(.bottom, 24)
            }.scrollIndicators(.hidden)
        }.journalPage()
    }
    private func card(_ title: String, icon: String, paragraphs: [String]) -> some View {
        VStack(alignment: .leading, spacing: 0) {
            HStack(spacing: 8) {
                DesignIcon(icon, size: 19).foregroundStyle(JournalTheme.accent)
                Text(title).font(JournalTheme.font(15.5, medium: true))
            }
            ForEach(Array(paragraphs.enumerated()), id: \.offset) { index, paragraph in
                Text(paragraph).font(JournalTheme.font(13)).foregroundStyle(JournalTheme.ink2).lineSpacing(7)
                    .fixedSize(horizontal: false, vertical: true).padding(.top, index == 0 ? 8 : 6)
            }
        }.frame(maxWidth: .infinity, alignment: .leading).padding(16).journalCard()
    }
}
