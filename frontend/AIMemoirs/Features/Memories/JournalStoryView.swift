import SwiftUI

struct JournalStoryView: View {
    @State private var current: MemoryEvent
    let api: any MemoryAPI
    @EnvironmentObject private var members: FamilyMemberStore
    @EnvironmentObject private var memories: MemoryListViewModel
    @EnvironmentObject private var navigation: JournalNavigation
    @State private var editing = false
    @State private var deleting = false
    @State private var busy = false
    @State private var error: String?
    @State private var latest: MemoryEvent?
    @State private var needsCacheCleanup = false
    init(memory: MemoryEvent, api: any MemoryAPI) { _current = State(initialValue: memory); self.api = api }
    var body: some View {
        JournalStoryContent(memory: current, identity: current.personName, dateText: nil, location: current.location, photoAPI: api)
            .journalPage().navigationTitle("回忆").navigationBarTitleDisplayMode(.inline).toolbar(.visible, for: .navigationBar)
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Menu { Button("编辑回忆") { Task { await beginEditing() } }; Button("删除整段回忆", role: .destructive) { deleting = true } } label: { Image(systemName: "ellipsis.circle").frame(minWidth: 44, minHeight: 44) }
                        .disabled(busy).accessibilityLabel("回忆操作").accessibilityIdentifier("memory.actions")
                }
            }
            .safeAreaInset(edge: .bottom) {
                if let error {
                    VStack(alignment: .leading) {
                        Text(error).foregroundStyle(.red)
                        if latest != nil { Button("读取最新回忆") { if let latest { current = latest; memories.upsert(latest); self.latest = nil; self.error = nil } } }
                        else if needsCacheCleanup { Button("重试清理本机聊天缓存") { Task { await finishDeletion() } } }
                        else { Button("重试读取回忆") { Task { await refresh() } } }
                    }.font(.footnote).padding().background(JournalTheme.surface)
                }
            }
            .overlay { if busy { ProgressView("正在处理…").padding().background(.regularMaterial, in: RoundedRectangle(cornerRadius: 12)) } }
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
            try ChatDraftStore.current(previewScreen: nil)?.invalidateHistory(personIDs: people, deletedSessionID: current.sourceSessionID)
            needsCacheCleanup = false
            if !navigation.path.isEmpty { navigation.path.removeLast() }
            memories.remove(id: current.id)
            await members.load()
        } catch { self.error = "服务器已删除回忆，本机聊天缓存待清理。未发送内容会保留，请重试。" }
    }

}
