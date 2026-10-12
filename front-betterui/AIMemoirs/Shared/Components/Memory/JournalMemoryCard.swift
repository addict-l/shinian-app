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
                if hasPhoto { JournalPhoto(memory: memory, height: 168, radius: 16).padding([.horizontal, .top], 8) }
                VStack(alignment: .leading, spacing: 8) {
                    Text(memory.title).font(JournalTheme.story(hasPhoto ? 19 : 18)).foregroundStyle(JournalTheme.ink)
                        .fixedSize(horizontal: false, vertical: true)
                    HStack(spacing: 6) {
                        Circle().fill(JournalTheme.accent).frame(width: 5, height: 5)
                        Text(subtitle).font(JournalTheme.font(12)).foregroundStyle(JournalTheme.muted)
                    }
                    Text(memory.content).font(JournalTheme.font(13)).foregroundStyle(JournalTheme.secondaryInk).lineLimit(2)
                        .lineSpacing(3)
                }.padding(.horizontal, 16).padding(.top, hasPhoto ? 12 : 16).padding(.bottom, 16)
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .journalCard()
        }.buttonStyle(.plain).accessibilityIdentifier("memory.card.\(memory.id)")
    }
}
