import SwiftUI

/// 回忆摘要卡片；通过回调交给使用页面决定导航行为。
struct JournalMemoryCard: View {
    let memory: MemoryEvent
    let subtitle: String
    let action: () -> Void
    private var hasPhoto: Bool { memory.imageData != nil || memory.imageName != nil }
    var body: some View {
        Button(action: action) {
            VStack(alignment: .leading, spacing: 0) {
                if hasPhoto { JournalPhoto(memory: memory, height: 177) }
                VStack(alignment: .leading, spacing: 9) {
                    Text(memory.title).font(JournalTheme.story(hasPhoto ? 20 : 18)).foregroundStyle(JournalTheme.ink)
                        .fixedSize(horizontal: false, vertical: true)
                    Text(subtitle).font(JournalTheme.font(12)).foregroundStyle(JournalTheme.muted)
                    Text(memory.content).font(JournalTheme.font(13)).foregroundStyle(JournalTheme.muted).lineLimit(1)
                }.padding(16)
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(JournalTheme.surface, in: RoundedRectangle(cornerRadius: 18))
        }.buttonStyle(.plain).accessibilityIdentifier("memory.card.\(memory.id)")
    }
}
