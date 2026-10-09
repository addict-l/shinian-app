import SwiftUI

/// 回忆正文的纯展示组件；用于已保存详情与新回忆草稿，不负责生成或保存。
struct JournalStoryContent: View {
    let memory: MemoryEvent
    let identity: String
    var dateText: String? = nil
    var location: String? = nil
    var isDraft = false
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 0) {
                if memory.imageData != nil || memory.imageName != nil { JournalPhoto(memory: memory, height: 246, radius: 0) }
                VStack(alignment: .leading, spacing: 0) {
                    Text(memory.title.replacingOccurrences(of: "，", with: "，\n"))
                        .font(JournalTheme.story(27)).lineSpacing(7).fixedSize(horizontal: false, vertical: true)
                    ViewThatFits(in: .horizontal) {
                        HStack { Text(identity); Spacer(minLength: 12); Text(metadata) }
                        VStack(alignment: .leading, spacing: 6) { Text(identity); Text(metadata) }
                    }.font(JournalTheme.font(12)).foregroundStyle(JournalTheme.muted).padding(.top, 20)
                    Text(memory.content).font(JournalTheme.font(14)).lineSpacing(10)
                        .fixedSize(horizontal: false, vertical: true).padding(.top, 26)
                    if isDraft { Text("根据你的讲述整理，可在保存前编辑。").font(JournalTheme.font(11)).foregroundStyle(JournalTheme.muted).padding(.top, 36) }
                }.padding(.horizontal, 24).padding(.top, 31).padding(.bottom, 30)
            }
        }.scrollIndicators(.hidden)
    }
    private var metadata: String {
        [dateText ?? memory.dateLabel, location].compactMap { $0 }.filter { !$0.isEmpty && $0 != "未提及" }.joined(separator: " · ")
    }
}
