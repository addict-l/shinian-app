import SwiftUI

/// 已保存回忆的详情页面，正文布局与保存前预览共用。
struct JournalStoryView: View {
    let memory: MemoryEvent
    var dateText: String? = nil
    var location: String? = nil
    @EnvironmentObject private var members: FamilyMemberStore
    var body: some View {
            JournalStoryContent(memory: memory, identity: memory.personName, dateText: dateText, location: location ?? memory.location)
            .journalPage().navigationTitle("回忆").navigationBarTitleDisplayMode(.inline).toolbar(.visible, for: .navigationBar)
    }
}
