import SwiftUI

struct CareMemoryReview: View {
    let draft: GeneratedMemory
    let memory: MemoryEvent
    let identity: String
    @ObservedObject var saveModel: MemorySaveViewModel
    let onBack: () -> Void
    let onEdit: () -> Void
    let onRegenerate: () -> Void
    let onSave: () async -> Void
    var body: some View {
        VStack(spacing: 0) {
            CareToolbar(title: "回忆草稿", backTitle: "讲述", onBack: onBack).disabled(saveModel.isSaving)
            ScrollView {
                VStack(alignment: .leading, spacing: 16) {
                    CareHeading(title: "看看这段回忆", subtitle: "看看有没有记错，满意了再保存。")
                    VStack(alignment: .leading, spacing: 14) {
                        Text(identity).font(CareTheme.font(18)).foregroundStyle(JournalTheme.ink2)
                        Text(memory.title).font(CareTheme.font(26, bold: true)).accessibilityAddTraits(.isHeader)
                        Text(memory.dateLabel).font(CareTheme.font(18)).foregroundStyle(JournalTheme.ink2)
                        if memory.imageData != nil || memory.imageName != nil { JournalPhoto(memory: memory, height: 150, radius: 14) }
                        Text(memory.content).font(CareTheme.font()).lineSpacing(5).textSelection(.enabled)
                            .fixedSize(horizontal: false, vertical: true).frame(maxWidth: .infinity, alignment: .leading)
                    }.padding(20).background(JournalTheme.surface, in: RoundedRectangle(cornerRadius: 18))
                    if let error = saveModel.errorMessage { CareError(message: error) }
                    Button("重新整理草稿", action: onRegenerate).font(CareTheme.font(19)).frame(maxWidth: .infinity, minHeight: 48)
                        .disabled(saveModel.isSaving)
                }.padding(20)
            }.scrollIndicators(.hidden)
            VStack(spacing: 8) {
                CareButton(title: "保存这段回忆", symbol: "checkmark", loading: saveModel.isSaving) { Task { await onSave() } }
                    .accessibilityIdentifier("memory.save")
                HStack(spacing: 12) {
                    Button("修改草稿", action: onEdit).accessibilityIdentifier("care.draft.edit")
                    Button("继续讲述", action: onBack)
                }.font(CareTheme.font(19)).frame(minHeight: 48).disabled(saveModel.isSaving)
            }.padding(.horizontal, 20).padding(.vertical, 10).background(CareTheme.paper)
        }.background(CareTheme.paper.ignoresSafeArea()).interactiveDismissDisabled(saveModel.isSaving)
    }
}

struct CareSavedMemoryView: View {
    let memory: MemoryEvent
    let onRead: () -> Void
    let onHome: () -> Void
    let onContinue: () -> Void
    var body: some View {
        ScrollView {
            VStack(spacing: 20) {
                Image(systemName: "checkmark.circle.fill").font(.system(size: 64)).foregroundStyle(JournalTheme.sageInk)
                    .accessibilityHidden(true).padding(.top, 32)
                CareHeading(title: "这段回忆，保存好了。", subtitle: "以后在“回忆”里，随时可以找到。")
                Text(memory.title).font(CareTheme.font(24, bold: true)).multilineTextAlignment(.center)
                    .accessibilityIdentifier("care.saved.title")
                CareButton(title: "打开看看", symbol: "book", action: onRead).accessibilityIdentifier("care.saved.read")
                CareButton(title: "回到首页", secondary: true, action: onHome).accessibilityIdentifier("care.saved.home")
                Button("再聊一段", action: onContinue).font(CareTheme.font(20)).frame(minHeight: 48)
                    .accessibilityIdentifier("care.saved.continue")
            }.padding(24)
        }.background(CareTheme.paper.ignoresSafeArea()).interactiveDismissDisabled()
    }
}
