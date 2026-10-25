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
    @Environment(\.dynamicTypeSize) private var typeSize
    @Environment(\.verticalSizeClass) private var verticalSizeClass
    private var inlineActions: Bool { typeSize.isAccessibilitySize || verticalSizeClass == .compact }

    var body: some View {
        VStack(spacing: 0) {
            CareToolbar(title: "回忆草稿", backTitle: "讲述", onBack: onBack)
                .disabled(saveModel.isSaving)
            ScrollView {
                VStack(alignment: .leading, spacing: 14) {
                    HStack(alignment: .top, spacing: 10) {
                        Image(systemName: "eye").accessibilityHidden(true)
                        Text("看看有没有记错，满意了再保存。")
                            .fixedSize(horizontal: false, vertical: true)
                    }.font(CareTheme.font(20, bold: true)).foregroundStyle(CareTheme.sageInk)
                        .frame(maxWidth: .infinity, alignment: .leading).padding(16)
                        .background(CareTheme.sageSoft, in: RoundedRectangle(cornerRadius: 22))
                    if let error = saveModel.errorMessage { CareError(message: error) }
                    letter
                    if inlineActions { actions.padding(.top, 4) }
                }.padding(.horizontal, 20).padding(.top, 4).padding(.bottom, 16)
            }.scrollIndicators(.hidden).accessibilityIdentifier("care.draft.scroll")
        }
        .safeAreaInset(edge: .bottom, spacing: 0) { if !inlineActions { actions.careDock() } }
        .carePage().interactiveDismissDisabled(saveModel.isSaving)
        .overlay { if saveModel.isSaving { CareBusyOverlay(text: "正在处理草稿…") } }
    }

    private var letter: some View {
        VStack(alignment: .leading, spacing: 16) {
            ViewThatFits(in: .horizontal) {
                HStack(alignment: .top, spacing: 10) { about; Spacer(minLength: 0); draftChip }
                VStack(alignment: .leading, spacing: 10) { about; draftChip }
            }
            Text(memory.title).font(JournalTheme.story(28)).foregroundStyle(CareTheme.ink)
                .fixedSize(horizontal: false, vertical: true).accessibilityAddTraits(.isHeader)
            JournalFlowLayout(spacing: 8) {
                metaChip(valid(draft.preview.date) ?? memory.dateLabel, symbol: "calendar")
                if let place = valid(draft.preview.location) ?? valid(memory.location) {
                    metaChip(place, symbol: "mappin.and.ellipse")
                }
            }
            if memory.hasPhoto {
                JournalPhoto(memory: memory, height: 150, radius: 20)
            }
            Text(memory.content).font(JournalTheme.story(22)).foregroundStyle(CareTheme.ink)
                .lineSpacing(10).textSelection(.enabled)
                .fixedSize(horizontal: false, vertical: true).frame(maxWidth: .infinity, alignment: .leading)
        }.padding(20).frame(maxWidth: .infinity, alignment: .leading)
            .journalCard(radius: 26, fill: CareTheme.surface)
    }

    private var about: some View {
        Text("关于" + identity).font(CareTheme.font(18)).foregroundStyle(CareTheme.ink2)
            .fixedSize(horizontal: false, vertical: true)
    }
    private var draftChip: some View {
        Text("草稿").font(CareTheme.font(17, bold: true)).foregroundStyle(CareTheme.butterInk)
            .padding(.horizontal, 13).padding(.vertical, 7).background(CareTheme.butterSoft, in: Capsule())
    }
    private func metaChip(_ text: String, symbol: String) -> some View {
        HStack(alignment: .firstTextBaseline, spacing: 6) {
            Image(systemName: symbol).foregroundStyle(CareTheme.accent).accessibilityHidden(true)
            Text(text).fixedSize(horizontal: false, vertical: true)
        }.font(CareTheme.font(17, bold: true)).foregroundStyle(CareTheme.ink2)
            .padding(.horizontal, 12).padding(.vertical, 8).background(CareTheme.paper2, in: RoundedRectangle(cornerRadius: 18))
    }
    private func valid(_ value: String?) -> String? {
        guard let value, !value.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
              value != "未提及", value != "待补充" else { return nil }
        return value
    }
    private var actions: some View {
        VStack(spacing: 12) {
            CareButton(title: "保存这段回忆", symbol: "heart", loading: saveModel.isSaving) { Task { await onSave() } }
                .accessibilityIdentifier("memory.save")
            if typeSize.isAccessibilitySize {
                editButton
                regenerateButton
            } else {
                HStack(spacing: 12) { editButton; regenerateButton }
            }
        }.disabled(saveModel.isSaving)
    }
    private var editButton: some View {
        CareButton(title: "修改草稿", symbol: "pencil", secondary: true, fontSize: 21, action: onEdit)
            .accessibilityIdentifier("care.draft.edit")
    }
    private var regenerateButton: some View {
        CareButton(title: "重新整理", symbol: "arrow.clockwise", secondary: true, fontSize: 21, action: onRegenerate)
    }
}

struct CareSavedMemoryView: View {
    let memory: MemoryEvent
    var photoAPI: (any MemoryAPI)? = nil
    let onRead: () -> Void
    let onHome: () -> Void
    let onContinue: () -> Void
    @Environment(\.dynamicTypeSize) private var typeSize
    @Environment(\.verticalSizeClass) private var verticalSizeClass
    @EnvironmentObject private var memories: MemoryListViewModel
    @EnvironmentObject private var members: FamilyMemberStore
    private var inlineActions: Bool { typeSize.isAccessibilitySize || verticalSizeClass == .compact }

    private var person: FamilyMember? {
        if let primaryID = memory.primaryPersonID { return members.members.first { $0.id == primaryID } }
        guard memory.personIDs.count == 1, let personID = memory.personIDs.first else { return nil }
        return members.members.first { $0.id == personID }
    }
    private var personLabel: String {
        guard let person else { return memory.personName }
        return person.relationship.isEmpty ? person.name : person.relationship
    }
    private var memoryCount: Int? {
        guard memories.hasLoaded, let person else { return nil }
        return memories.memoryEvents.filter { $0.primaryPersonID.map { $0 == person.id } ?? $0.personIDs.contains(person.id) }.count
    }
    var body: some View {
        ScrollView {
            VStack(spacing: 22) {
                ZStack {
                    Circle().fill(CareTheme.sageSoft).frame(width: 116, height: 116)
                    Circle().fill(CareTheme.sage).frame(width: 80, height: 80)
                    Image(systemName: "checkmark").font(.system(size: 42, weight: .medium)).foregroundStyle(.white)
                }.accessibilityHidden(true).padding(.top, 24)
                VStack(spacing: 12) {
                    Text("这段回忆，保存好了").font(CareTheme.font(30, bold: true)).foregroundStyle(CareTheme.ink)
                        .accessibilityAddTraits(.isHeader)
                    Text("以后在「回忆」里，随时可以找到。")
                        .font(CareTheme.font(19)).foregroundStyle(CareTheme.ink2)
                }.multilineTextAlignment(.center).fixedSize(horizontal: false, vertical: true)
                savedCard
                if let memoryCount {
                    HStack(alignment: .top, spacing: 8) {
                        Image(systemName: "book").accessibilityHidden(true)
                        Text("\(personLabel)的回忆，现在有 \(memoryCount) 段了")
                            .fixedSize(horizontal: false, vertical: true)
                    }.font(CareTheme.font(19, bold: true)).foregroundStyle(CareTheme.sageInk)
                        .padding(.horizontal, 16).padding(.vertical, 12)
                        .background(CareTheme.sageSoft, in: RoundedRectangle(cornerRadius: 22))
                }
                if inlineActions { actions.padding(.top, 4) }
            }.padding(.horizontal, 20).padding(.bottom, 24)
        }.scrollIndicators(.hidden).accessibilityIdentifier("care.saved.scroll")
            .safeAreaInset(edge: .bottom, spacing: 0) { if !inlineActions { actions.careDock() } }
            .carePage().interactiveDismissDisabled()
    }
    private var savedCard: some View {
        Group {
            if typeSize.isAccessibilitySize {
                VStack(alignment: .leading, spacing: 14) { savedPhoto; savedDescription }
            } else {
                HStack(alignment: .center, spacing: 14) { savedPhoto; savedDescription }
            }
        }.padding(14).frame(maxWidth: .infinity, alignment: .leading)
            .journalCard(radius: 26, fill: CareTheme.surface)
    }
    @ViewBuilder private var savedPhoto: some View {
        if memory.imageData != nil || memory.imageName != nil {
            JournalPhoto(memory: memory, height: 92, radius: 18).frame(width: 92)
        } else if let photoAPI, let photo = memory.mediaAssets.first {
            MemoryPhotoView(attachment: photo, api: photoAPI).frame(width: 92, height: 92)
                .background(CareTheme.paper2, in: RoundedRectangle(cornerRadius: 18))
                .clipShape(RoundedRectangle(cornerRadius: 18)).accessibilityLabel("回忆照片：\(memory.title)")
        } else {
            CareIconTile(symbol: "book", tone: .butter, size: 92)
        }
    }
    private var savedDescription: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text([personLabel, memory.dateLabel].filter { !$0.isEmpty }.joined(separator: " · "))
                .font(CareTheme.font(18)).foregroundStyle(CareTheme.ink2)
            Text(memory.title).font(JournalTheme.story(24)).foregroundStyle(CareTheme.ink)
                .accessibilityIdentifier("care.saved.title")
        }.fixedSize(horizontal: false, vertical: true).frame(maxWidth: .infinity, alignment: .leading)
    }
    private var actions: some View {
        VStack(spacing: 12) {
            CareButton(title: "打开看看", symbol: "book", action: onRead).accessibilityIdentifier("care.saved.read")
            if typeSize.isAccessibilitySize {
                continueButton
                homeButton
            } else {
                HStack(spacing: 12) { continueButton; homeButton }
            }
        }
    }
    private var continueButton: some View {
        CareButton(title: "再讲一段", symbol: "mic", secondary: true, fontSize: 21, action: onContinue)
            .accessibilityIdentifier("care.saved.continue")
    }
    private var homeButton: some View {
        CareButton(title: "回到首页", symbol: "house", secondary: true, fontSize: 21, action: onHome)
            .accessibilityIdentifier("care.saved.home")
    }
}
