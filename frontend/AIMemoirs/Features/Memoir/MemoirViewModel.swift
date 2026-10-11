import SwiftUI
import Network

struct MemoirPhotoFailure: Identifiable { let id: UUID; let label: String; let cover: Bool }
struct MemoirPreview {
    let url: URL
    let revision: String
    let settings: MemoirSettings
    let pageCount: Int
}
@MainActor final class MemoirViewModel: ObservableObject {
    let person: FamilyMember
    let api: any MemoirAPI
    let store: MemoirLocalStore
    @Published var settings: MemoirSettings { didSet { if observing { changed() } } }
    @Published private(set) var snapshot: MemoirSnapshot?
    @Published private(set) var busy = false
    @Published private(set) var syncLabel = "正在读取"
    @Published private(set) var thumbnails: [UUID: UIImage] = [:]
    @Published private(set) var failures: [MemoirPhotoFailure] = []
    @Published private(set) var preview: MemoirPreview?
    @Published private(set) var conflict: MemoirSnapshot?
    @Published var error: String?
    @Published var needsNewPreview = false
    private var observing = false
    private var dirty = false
    private var pending: MemoirSaveRequest?
    private var syncTask: Task<Void, Never>?
    private var saving = false
    private var persistFailed = false
    private let connection = NWPathMonitor()
    private var sawInitialPath = false

    init(person: FamilyMember, api: any MemoirAPI, store: MemoirLocalStore) {
        self.person = person; self.api = api; self.store = store
        settings = MemoirSettings(title: person.name + "的回忆录")
        snapshot = MemoirSnapshot(personId: person.id, personName: person.name, version: 0,
            settings: settings, stories: [], contentRevision: "")
        do {
            if let value = try store.load() {
                snapshot = value.snapshot; settings = value.settings; pending = value.pending; dirty = value.dirty
                syncLabel = dirty ? "待同步" : "已保存"
            }
        } catch { self.error = "本机制作设置暂时无法读取，请重试。" }
        observing = true
        connection.pathUpdateHandler = { [weak self] path in
            let connected = path.status == .satisfied
            Task { @MainActor [weak self] in
                guard let self else { return }
                if !self.sawInitialPath { self.sawInitialPath = true; return }
                guard connected, self.snapshot != nil else { return }; _ = await self.sync()
            }
        }
        connection.start(queue: DispatchQueue(label: "shinian.memoir.connection"))
    }
    deinit { connection.cancel(); syncTask?.cancel() }
    var stories: [MemoryEvent] { settings.ordered(snapshot?.stories ?? []) }
    var activeCover: [MemoirCoverPhoto] { Array(settings.coverPhotos.prefix(settings.coverTemplate.limit)) }
    var invalidCover: Bool {
        activeCover.contains { photo in
            guard let source = photo.sourceMemoryId else { return false }
            return !(snapshot?.stories.contains { $0.id == source && $0.mediaAssets.contains { $0.id == photo.id } } ?? false)
        } || activeCover.count < (settings.coverTemplate == .text ? 0 : 1)
    }
    private func persist() {
        guard let snapshot else { return }
        do {
            try store.save(MemoirLocalState(snapshot: snapshot, settings: settings, pending: pending, dirty: dirty))
            persistFailed = false
        } catch {
            persistFailed = true; syncLabel = "本机保存失败"
            self.error = "无法保存本机设置，请腾出空间后重试；当前修改仍在页面中。"
        }
    }
    private func changed() {
        dirty = true; syncLabel = "待同步"; persist()
        syncTask?.cancel()
        syncTask = Task { [weak self] in
            try? await Task.sleep(for: .milliseconds(650))
            guard !Task.isCancelled else { return }; _ = await self?.sync()
        }
    }
    func load() async {
        guard !busy else { return }; busy = true; defer { busy = false }
        do {
            let remote = try await api.memoir(personID: person.id)
            reconcile(remote)
            if conflict == nil { _ = await sync() }
            Task { await loadThumbnails() }
        } catch { syncLabel = dirty ? "待同步" : "暂时离线"; self.error = error.localizedDescription }
    }
    private func reconcile(_ remote: MemoirSnapshot) {
        if dirty, let old = snapshot {
            if let pending, remote.version == pending.version + 1, remote.settings == pending.settings {
                acknowledge(remote, sent: pending)
            } else if remote.version != old.version {
                conflict = remote; syncLabel = "需要核对版本"; return
            } else { snapshot = remote; persist() }
        } else {
            observing = false; settings = remote.settings; observing = true
            snapshot = remote; syncLabel = "已保存"; persist()
        }
    }
    private func acknowledge(_ remote: MemoirSnapshot, sent: MemoirSaveRequest) {
        snapshot = remote; pending = nil; dirty = settings != sent.settings
        syncLabel = dirty ? "待同步" : "已保存"; persist()
    }
    @discardableResult func sync() async -> Bool {
        while saving {
            do { try await Task.sleep(for: .milliseconds(30)) } catch { return false }
        }
        guard conflict == nil, settings.valid, snapshot != nil, !Task.isCancelled else { return false }
        persist(); guard !persistFailed else { return false }
        saving = true; defer { saving = false }
        do {
            while dirty || pending != nil {
                if pending == nil {
                    pending = MemoirSaveRequest(version: snapshot!.version, settings: settings); persist()
                    guard !persistFailed else { return false }
                }
                let sent = pending!
                // Imported photos survive restart with the same upload identity.
                // Upload is idempotent, including a response lost before settings save.
                for photo in sent.settings.coverPhotos.prefix(sent.settings.coverTemplate.limit) where photo.sourceMemoryId == nil {
                    let url = store.photoURL(photo.id)
                    if FileManager.default.fileExists(atPath: url.path) {
                        _ = try await api.uploadMemoirCover(personID: person.id, data: Data(contentsOf: url), requestID: photo.id)
                    }
                }
                let remote = try await api.saveMemoir(personID: person.id, request: sent)
                guard remote.version == sent.version + 1, remote.settings == sent.settings else {
                    conflict = remote; syncLabel = "需要核对版本"; return false
                }
                acknowledge(remote, sent: sent)
                guard !persistFailed else { return false }
            }
            return true
        } catch {
            syncLabel = "待同步"
            if error is CancellationError { return false }
            if isVersionConflict(error) {
                do {
                    let remote = try await api.memoir(personID: person.id)
                    reconcile(remote)
                    if conflict == nil { syncLabel = dirty ? "待同步" : "已保存" }
                }
                catch { self.error = "版本核对暂时失败，本机设置已保留，请重试同步。" }
            } else {
                if case APIError.rejected(let status, _) = error, status == 422 {
                    pending = nil; persist() // Rejected writes did not commit; allow corrected settings to replace them.
                }
                self.error = error.localizedDescription
            }
            return false
        }
    }
    func chooseCloud() {
        guard let remote = conflict else { return }
        observing = false; settings = remote.settings; observing = true
        snapshot = remote; pending = nil; dirty = false; conflict = nil; syncLabel = "已保存"; persist()
        Task { await loadThumbnails() }
    }
    func chooseLocal() async {
        guard let remote = conflict else { return }
        snapshot = remote; pending = nil; conflict = nil; dirty = true; persist(); _ = await sync()
    }
    func moveStory(from: IndexSet, to: Int) {
        var ids = stories.map(\.id); ids.move(fromOffsets: from, toOffset: to)
        var value = settings; value.ordering = "manual"; value.storyOrder = ids; settings = value
    }
    func movePhoto(story: MemoryEvent, from: IndexSet, to: Int) {
        var ids = settings.photos(story).map(\.id); ids.move(fromOffsets: from, toOffset: to)
        settings.photoOrders[story.id.uuidString.lowercased()] = ids
    }
    func togglePhoto(_ id: UUID) {
        if settings.excludedPhotoIds.contains(id) { settings.excludedPhotoIds.removeAll { $0 == id } }
        else { settings.excludedPhotoIds.append(id) }
    }
    func addCover(_ photo: MemoirCoverPhoto) {
        guard settings.coverTemplate.limit > 0 else { return }
        var photos = activeCover.filter { $0.id != photo.id }
        if photos.count >= settings.coverTemplate.limit { photos.removeLast() }
        photos.append(photo); settings.coverPhotos = photos
        Task { await loadThumbnails() }
    }
    func importCover(_ data: Data) {
        do {
            let data = try PhotoCompression.compress(data), id = UUID()
            _ = try store.savePhoto(data, id: id)
            thumbnails[id] = PhotoCompression.thumbnail(data)
            addCover(MemoirCoverPhoto(id: id))
        } catch { self.error = error.localizedDescription }
    }
    private func attachment(_ id: UUID) -> ChatAttachment {
        ChatAttachment(id: id, url: "/api/v1/media/" + id.uuidString.lowercased(), position: 0)
    }
    private func imageURL(_ id: UUID) async throws -> URL {
        let url = store.photoURL(id)
        if let data = try? Data(contentsOf: url), PhotoCompression.thumbnail(data) != nil { return url }
        let data = try await api.loadPhoto(attachment(id))
        guard PhotoCompression.thumbnail(data) != nil else { throw APIError.server("照片无法读取，请重试或重新选择。") }
        return try store.savePhoto(data, id: id)
    }
    func loadThumbnails() async {
        let ids = Set((snapshot?.stories.flatMap { $0.mediaAssets.map(\.id) } ?? []) + activeCover.map(\.id) + (conflict?.settings.coverPhotos.map(\.id) ?? []))
        for id in ids where thumbnails[id] == nil {
            if let url = try? await imageURL(id), let data = try? Data(contentsOf: url) {
                thumbnails[id] = PhotoCompression.thumbnail(data)
            }
        }
    }
    func generatePreview() async {
        guard !busy else { return }; busy = true; defer { busy = false }
        error = nil; failures = []; needsNewPreview = false
        guard await sync() else { return }
        do {
            reconcile(try await api.memoir(personID: person.id))
            guard conflict == nil else { return }
            guard !stories.isEmpty else { throw APIError.server("先保存一段回忆，就可以制作回忆录。") }
            guard !invalidCover else { throw APIError.server("封面照片尚未选择或原故事照片已被移除，请更换照片或选择纯文字封面。") }
            let captured = settings
            let current = snapshot!
            var urls: [UUID: URL] = [:]
            var required: [UUID: (String, Bool)] = [:]
            for story in stories { for photo in captured.selectedPhotos(story) { required[photo.id] = (story.title, false) } }
            for photo in activeCover { required[photo.id] = ("封面照片", true) }
            for (id, label) in required {
                do { urls[id] = try await imageURL(id) }
                catch { failures.append(MemoirPhotoFailure(id: id, label: label.0, cover: label.1)) }
            }
            guard failures.isEmpty else { throw APIError.server("部分照片未能准备好，请重试，或取消选择失败照片。") }
            guard settings == captured else { throw APIError.server("设置已调整，请重新生成预览。") }
            let directory = store.root.appendingPathComponent("PDFs/\(UUID())")
            try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
            let filename = captured.title.components(separatedBy: CharacterSet(charactersIn: "/\\:\n\r")).joined(separator: " ").trimmingCharacters(in: .whitespacesAndNewlines)
            let output = directory.appendingPathComponent(String(filename.prefix(80)) + ".pdf")
            let result = try await Task.detached(priority: .userInitiated) {
                try MemoirPDFRenderer.render(snapshot: current, settings: captured, photos: urls, to: output)
            }.value
            try FileManager.default.setAttributes([.protectionKey: FileProtectionType.completeUntilFirstUserAuthentication], ofItemAtPath: output.path)
            let previous = preview?.url
            preview = MemoirPreview(url: output, revision: current.contentRevision, settings: captured, pageCount: result)
            if let previous { try? FileManager.default.removeItem(at: previous) }
        } catch { self.error = error.localizedDescription }
    }
    func verifiedShareURL() async -> URL? {
        guard let preview, !busy else { return nil }; busy = true; defer { busy = false }
        error = nil
        guard await sync() else { return nil }
        do {
            let remote = try await api.memoir(personID: person.id)
            reconcile(remote); guard conflict == nil else { return nil }
            guard remote.contentRevision == preview.revision, settings == preview.settings else {
                needsNewPreview = true; return nil
            }
            return preview.url
        } catch { self.error = error.localizedDescription; return nil }
    }
}
