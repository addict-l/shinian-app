import SwiftUI

struct PendingMemoryPhoto: Identifiable {
    let id: UUID
    let data: Data
    var attachment: ChatAttachment?
}

@MainActor final class MemoryEditorModel: ObservableObject {
    @Published var edit: MemoryEdit
    @Published private(set) var base: MemoryEvent
    @Published private(set) var latest: MemoryEvent?
    @Published private(set) var added: [PendingMemoryPhoto] = []
    @Published private(set) var busy = false
    @Published var error: String?
    private let api: any MemoryAPI
    private let originalPhotos: [ChatAttachment]
    private var discarded: [UUID] = []
    init(memory: MemoryEvent, api: any MemoryAPI) {
        base = memory; edit = MemoryEdit(memory); self.api = api; originalPhotos = memory.mediaAssets
    }
    var changed: Bool { edit != MemoryEdit(base) || !added.isEmpty }
    var selected: [ChatAttachment] {
        let candidates = originalPhotos + base.mediaAssets.filter { photo in !originalPhotos.contains { $0.id == photo.id } }
        return candidates.filter { edit.mediaIDs.contains($0.id) }
    }
    func append(_ data: Data) { added.append(PendingMemoryPhoto(id: UUID(), data: data)) }
    func remove(id: UUID) {
        edit.mediaIDs.removeAll { $0 == id }
        if let photo = added.first(where: { $0.id == id }), photo.attachment != nil { discarded.append(id) }
        added.removeAll { $0.id == id }
    }
    func readLatest() async {
        busy = true; defer { busy = false }
        do { latest = try await api.getMemory(id: base.id) }
        catch { self.error = "读取最新版本失败；本机修改仍保留。" + error.localizedDescription }
    }
    /// Explicit confirmation adopts only the concurrency token; local edits stay intact.
    func acceptLatestVersion() {
        if let latest { base = latest; self.latest = nil }
    }
    func save() async -> MemoryEvent? {
        guard !busy, edit.isValid, latest == nil else { return nil }
        busy = true; error = nil; defer { busy = false }
        do {
            for index in added.indices where added[index].attachment == nil {
                let photo = added[index]
                let receipt = try await api.uploadMemoryPhoto(id: base.id, data: photo.data, requestID: photo.id)
                added[index].attachment = receipt
            }
            var values = edit
            values.mediaIDs += added.map(\.id)
            // Complete canceled uploads before committing the edit, so a timeout
            // retains the form and cleanup identities for manual retry.
            for id in discarded { try await discard(id) }
            discarded = []
            let result = try await api.updateMemory(base, edit: values)
            added = []; base = result; edit = MemoryEdit(result)
            return result
        } catch {
            self.error = error.localizedDescription
            if isVersionConflict(error) {
                do { latest = try await api.getMemory(id: base.id) }
                catch { self.error = "读取最新版本失败；本机修改仍保留。" + error.localizedDescription }
            }
            return nil
        }
    }
    func cancel() async -> Bool {
        guard !busy else { return false }
        busy = true; defer { busy = false }
        do {
            // Include unacknowledged uploads: the server may have committed before a timeout.
            for id in Set(discarded + added.map(\.id)) { try await discard(id) }
            return true
        } catch { self.error = "取消尚未完成，新照片仍待清理，请重试。" + error.localizedDescription; return false }
    }
    private func discard(_ id: UUID) async throws {
        do { try await api.discardMemoryPhoto(id: base.id, photoID: id) }
        catch APIError.rejected(let status, _) where status == 404 || status == 409 {
            // Another device deleted the story or saved this photo. Never remove
            // an attached photo merely because this local editor is canceled.
        } catch APIError.httpStatus(let status) where status == 404 || status == 409 {
        }
    }

}
