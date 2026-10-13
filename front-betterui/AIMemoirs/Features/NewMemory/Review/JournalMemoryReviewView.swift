import SwiftUI

/// 保存前预览：展示草稿与保存状态，返回、编辑和保存通过回调交由聊天流程处理。
struct JournalMemoryReviewView: View {
    let draft: GeneratedMemory
    let imageData: Data?
    let identity: String
    @ObservedObject var saveModel: MemorySaveViewModel
    let onBack: () -> Void
    let onEdit: () -> Void
    let onRegenerate: () -> Void
    let onSave: () async -> Void

    private var memory: MemoryEvent { draft.memory.copy(imageData: imageData ?? draft.memory.imageData) }
    private var hasPhoto: Bool { memory.imageData != nil || memory.imageName != nil }
    private var feeling: String? {
        [draft.memory.information.feeling.value, draft.preview.emotion].compactMap { $0 }.first { !$0.isEmpty && $0 != "未提及" }
    }
    private func valid(_ value: String?) -> String? {
        guard let value, !value.isEmpty, value != "未提及", value != "待补充" else { return nil }
        return value
    }

    var body: some View {
        VStack(spacing: 0) {
            JournalNavBar(title: "回忆预览") {
                JournalRoundButton(icon: "back", label: "返回对话", action: onBack).disabled(saveModel.isSaving)
            } trailing: {
                Menu { Button("编辑文字与时间", action: onEdit); Button("重新生成草稿", action: onRegenerate) } label: {
                    DesignIcon("more").foregroundStyle(JournalTheme.ink)
                        .frame(width: 40, height: 40).background(JournalTheme.surface, in: Circle())
                        .shadow(color: JournalTheme.shadow.opacity(0.08), radius: 7, x: 0, y: 4)
                        .frame(width: 44, height: 44)
                }
                .disabled(saveModel.isSaving).accessibilityLabel("草稿操作").accessibilityIdentifier("draft.actions")
            }
            ScrollView {
                VStack(spacing: 0) {
                    letter
                    HStack(spacing: 10) {
                        action("编辑文字与时间", icon: "edit", perform: onEdit)
                        action("重新生成草稿", icon: "refresh", perform: onRegenerate)
                        action("返回对话", icon: "chat", perform: onBack)
                    }.padding(.top, 16).disabled(saveModel.isSaving)
                    if let error = saveModel.errorMessage {
                        Text(error).font(JournalTheme.font(12)).foregroundStyle(JournalTheme.danger).padding(.top, 12)
                    }
                    JournalButton(title: "保存这段回忆", icon: "heart", loading: saveModel.isSaving) {
                        Task { await onSave() }
                    }.padding(.top, 16).accessibilityIdentifier("memory.save")
                    Text("只在你确认后，成为正式回忆").font(JournalTheme.font(12)).foregroundStyle(JournalTheme.muted).padding(.top, 8)
                }
                .padding(.horizontal, JournalTheme.gutter).padding(.top, 6).padding(.bottom, 24)
            }
            .scrollIndicators(.hidden)
        }
        .journalPage()
        .preferredColorScheme(.light).interactiveDismissDisabled(saveModel.isSaving)
    }

    private var letter: some View {
        VStack(alignment: .leading, spacing: 0) {
            Text("关于" + identity).font(JournalTheme.font(12)).foregroundStyle(JournalTheme.muted).padding(.trailing, 56)
            Text(memory.title).font(JournalTheme.story(23)).lineSpacing(0).foregroundStyle(JournalTheme.ink)
                .fixedSize(horizontal: false, vertical: true).padding(.top, 8)
            JournalFlowLayout(spacing: 6) {
                if let date = valid(draft.preview.date) ?? valid(memory.dateDescription) { metaChip(date, icon: "cal") }
                if let place = valid(draft.preview.location) ?? valid(memory.location) { metaChip(place, icon: "pin") }
                if let feeling { metaChip(feeling, icon: "heart", rose: true) }
            }.padding(.top, 10)
            if hasPhoto { JournalPhoto(memory: memory, height: 150, radius: 16).padding(.top, 14) }
            Text(memory.content).font(JournalTheme.story(15)).lineSpacing(7).foregroundStyle(JournalTheme.storyInk)
                .fixedSize(horizontal: false, vertical: true).padding(.top, 14)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(.leading, 26).padding(.trailing, 20).padding(.top, 20).padding(.bottom, 18)
        .overlay(alignment: .topTrailing) {
            JournalChip(text: "草稿", style: .butter, compact: true).padding(.top, 16).padding(.trailing, 16).accessibilityHidden(true)
        }
        .background(alignment: .leading) {
            UnevenRoundedRectangle(topLeadingRadius: 6, bottomLeadingRadius: 6, bottomTrailingRadius: 26, topTrailingRadius: 26, style: .continuous)
                .fill(Color(hex: 0xFFFCF5))
                .overlay(alignment: .leading) { JournalTheme.soft.frame(width: 6) }
                .clipShape(UnevenRoundedRectangle(topLeadingRadius: 6, bottomLeadingRadius: 6, bottomTrailingRadius: 26, topTrailingRadius: 26, style: .continuous))
                .journalLiftedShadow()
        }
    }

    private func metaChip(_ text: String, icon: String, rose: Bool = false) -> some View {
        HStack(spacing: 5) {
            DesignIcon(icon, size: 14)
            Text(text).lineLimit(1)
        }
        .font(JournalTheme.font(12)).foregroundStyle(rose ? JournalTheme.roseInk : JournalTheme.ink2)
        .padding(.horizontal, 10).frame(height: 26)
        .background(rose ? JournalTheme.roseSoft : JournalTheme.surface, in: Capsule())
        .overlay { if !rose { Capsule().stroke(JournalTheme.line, lineWidth: 1) } }
    }

    private func action(_ title: String, icon: String, perform: @escaping () -> Void) -> some View {
        Button(action: perform) {
            VStack(spacing: 4) {
                DesignIcon(icon).foregroundStyle(JournalTheme.accent)
                Text(title).font(JournalTheme.font(12.5)).foregroundStyle(JournalTheme.ink2).lineLimit(1).minimumScaleFactor(0.8)
            }
            .frame(maxWidth: .infinity).padding(.vertical, 12)
            .journalCard()
            .contentShape(Rectangle())
        }.buttonStyle(JournalActionButtonStyle())
    }
}
