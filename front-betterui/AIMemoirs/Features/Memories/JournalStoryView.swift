import SwiftUI

struct JournalStoryView: View {
    @State private var current: MemoryEvent
    let api: any MemoryAPI
    @EnvironmentObject private var members: FamilyMemberStore
    @EnvironmentObject private var memories: MemoryListViewModel
    @EnvironmentObject private var navigation: JournalNavigation
    @Environment(\.dismiss) private var dismiss
    @State private var editing = false
    @State private var deleting = false
    @State private var showingActions = false
    @State private var busy = false
    @State private var error: String?
    @State private var latest: MemoryEvent?
    @State private var needsCacheCleanup = false
    init(memory: MemoryEvent, api: any MemoryAPI) { _current = State(initialValue: memory); self.api = api }
    private var person: FamilyMember? {
        let id = current.primaryPersonID ?? current.personIDs.first
        return members.members.first { $0.id == id }
    }
    private var identity: String {
        guard let person else { return "关于" + current.personName }
        return person.relationship.isEmpty ? "关于\(person.name)" : "关于\(person.relationship) · \(person.name)"
    }
    var body: some View {
        JournalStoryContent(memory: current, identity: identity, person: person, photoAPI: api, topInset: 48)
            .overlay(alignment: .top) {
                JournalNavBar {
                    JournalRoundButton(icon: "back", label: "返回", background: JournalTheme.surface.opacity(0.85)) { dismiss() }
                } trailing: {
                    JournalRoundButton(icon: "more", label: "回忆操作", background: JournalTheme.surface.opacity(0.85)) { showingActions = true }
                        .disabled(busy).accessibilityIdentifier("memory.actions")
                }
            }
            .journalPage()
            .safeAreaInset(edge: .bottom) {
                if let error {
                    VStack(alignment: .leading, spacing: 6) {
                        Text(error).foregroundStyle(JournalTheme.danger)
                        if latest != nil { Button("读取最新回忆") { if let latest { current = latest; memories.upsert(latest); self.latest = nil; self.error = nil } } }
                        else if needsCacheCleanup { Button("重试清理本机聊天缓存") { Task { await finishDeletion() } } }
                        else { Button("重试读取回忆") { Task { await refresh() } } }
                    }.font(JournalTheme.font(13)).foregroundStyle(JournalTheme.accentDeep)
                        .frame(maxWidth: .infinity, alignment: .leading).padding(16).journalCard().padding(.horizontal, 16)
                }
            }
            .overlay { if busy { ProgressView("正在处理…").padding().background(.regularMaterial, in: RoundedRectangle(cornerRadius: 12)) } }
            .overlay {
                if showingActions {
                    JournalActionSheet(title: "回忆操作", onCancel: { showingActions = false }) {
                        JournalActionSheetRow(title: "编辑回忆", icon: "edit") { showingActions = false; Task { await beginEditing() } }
                        JournalActionSheetRow(title: "删除整段回忆", icon: "trash", destructive: true) { showingActions = false; deleting = true }
                    }.transition(.opacity)
                }
            }
            .animation(.easeOut(duration: 0.2), value: showingActions)
            .onAppear { if JournalDemo.screen == "story-actions" { showingActions = true } }
            .sheet(isPresented: $editing) {
                JournalMemoryEditorView(memory: current, api: api, onCancel: { editing = false }, onSaved: { result in
                    current = result; memories.upsert(result); editing = false
                })
            }
            .alert("删除整段回忆？", isPresented: $deleting) {
                Button("保留回忆", role: .cancel) {}
                Button("确认删除整段", role: .destructive) { Task { await remove() } }
            } message: { Text("“\(current.title)”及其对应的讲述、AI 回复、草稿和照片会一并删除。AI 开场白和同一人物的其他回忆会保留，已导出到外部的 PDF 不受影响。此操作无法撤销。") }
    }
    private func refresh() async {
        busy = true; defer { busy = false }
        do { current = try await api.getMemory(id: current.id); memories.upsert(current); error = nil }
        catch { self.error = error.localizedDescription }
    }
    private func beginEditing() async { await refresh(); if error == nil { editing = true } }
    private func remove() async {
        busy = true; error = nil; defer { busy = false }
        do {
            try await api.deleteMemory(current)
            needsCacheCleanup = true
            await finishDeletion()
        } catch {
            self.error = error.localizedDescription
            if isVersionConflict(error) { latest = try? await api.getMemory(id: current.id) }
        }
    }
    private func finishDeletion() async {
        do {
            let people = current.primaryPersonID.map { Set([$0]) } ?? Set(current.personIDs)
            try ChatDraftStore.current(previewScreen: JournalDemo.screen)?.invalidateHistory(personIDs: people, deletedSessionID: current.sourceSessionID)
            needsCacheCleanup = false
            if !navigation.path.isEmpty { navigation.path.removeLast() }
            memories.remove(id: current.id)
            await members.load()
        } catch { self.error = "服务器已删除回忆，本机聊天缓存待清理。未发送内容会保留，请重试。" }
    }

}
