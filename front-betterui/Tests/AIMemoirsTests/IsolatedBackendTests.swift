import Foundation
import UIKit
import PDFKit
import Testing
@testable import AIMemoirs

/// Runs only against the disposable API, never against the family's production server.
struct IsolatedBackendTests {
    @Test @MainActor func realHTTPChatPhotoDraftEditMemoirAndDeletion() async throws {
        guard ProcessInfo.processInfo.environment["BETTERUI_ISOLATED_TEST"] == "1" else { return }
        let client = APIClient.local
        #expect(client.baseURL.absoluteString == "http://localhost:17655")
        guard client.baseURL.absoluteString == "http://localhost:17655" else { throw APIError.insecureURL }
        let api = BackendRepository(client: client)
        let person = try await api.addMember(FamilyMemberDraft(realName: "界面联调" + String(UUID().uuidString.prefix(8)),
            relationship: "爷爷", birthDate: APIDate.parseDay("1940-05-12")))
        let root = FileManager.default.temporaryDirectory.appendingPathComponent("BetterUILive-" + UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: root) }
        do {
            #expect(try await api.members().contains { $0.id == person.id })
            let opening = try await api.start(person: person, requestID: UUID())
            #expect(!opening.messages.isEmpty)
            let image = UIGraphicsImageRenderer(size: CGSize(width: 80, height: 60)).image { context in
                UIColor.systemOrange.setFill(); context.fill(CGRect(x: 0, y: 0, width: 80, height: 60))
            }.jpegData(compressionQuality: 0.85)!
            let photo = try await api.uploadPhoto(sessionID: opening.sessionID, image: image, requestID: UUID())
            #expect(UIImage(data: try await api.loadPhoto(photo)) != nil)
            let messageID = UUID()
            let text = "2010年5月1日，我在家门口的小广场教孙子骑自行车。我扶着他的后座，告诉他看前方别害怕。他终于学会了，我觉得特别开心。这是虚构的功能测试故事，已经讲完，请帮我整理成回忆草稿。"
            var reply = try await api.send(sessionID: opening.sessionID, text: text, attachmentIDs: [photo.id], requestID: messageID)
            let replay = try await api.send(sessionID: opening.sessionID, text: text, attachmentIDs: [photo.id], requestID: messageID)
            #expect(replay.messages.filter { $0.id == messageID }.count == 1)
            #expect(replay.messages.first { $0.id == messageID }?.attachments.first?.id == photo.id)
            if !reply.canGenerate {
                reply = try await api.send(sessionID: opening.sessionID,
                    text: "故事已经讲完，没有其他补充，我同意先整理成草稿。", requestID: UUID())
            }
            #expect(reply.canGenerate)
            #expect(try await BackendRepository(client: client).resume(sessionID: opening.sessionID).messages.contains { $0.id == messageID })
            var draft = try await api.generate(sessionID: opening.sessionID)
            draft = try await api.editDraft(draft, title: "界面联调草稿", content: draft.memory.content)
            #expect(draft.manuallyEdited)
            draft = try await api.regenerateDraft(draft)
            draft = try await api.getDraft(id: draft.draftID)
            draft = try await api.editDraft(draft, title: "界面联调回忆", content: "2010年5月1日，我在家门口的小广场教孙子骑自行车。他学会了，我很开心。")
            let saved = try await api.save(draft)
            #expect(try await api.save(draft).id == saved.id)
            let reloaded = try #require(try await BackendRepository(client: client).list().first { $0.id == saved.id })
            #expect(reloaded.title == "界面联调回忆" && reloaded.imageData != nil && reloaded.primaryPersonID == person.id)
            let editor = MemoryEditorModel(memory: reloaded, api: api)
            editor.edit.title = "界面联调修改后"
            editor.append(image)
            var edited = try #require(await editor.save())
            #expect(edited.mediaAssets.count == 2 && edited.title == "界面联调修改后")
            var concurrentEdit = MemoryEdit(edited); concurrentEdit.title = "其他设备的修改"
            let newer = try await api.updateMemory(edited, edit: concurrentEdit)
            editor.edit.title = "版本核对后保留的本机修改"
            #expect(await editor.save() == nil && editor.latest?.version == newer.version)
            editor.acceptLatestVersion()
            edited = try #require(await editor.save())
            let book = MemoirViewModel(person: person, api: api, store: MemoirLocalStore(root: root))
            await book.load()
            #expect(book.stories.contains { $0.id == edited.id })
            book.settings.title = "联调回忆录"
            book.settings.subtitle = "真实服务 · 虚构数据"
            book.settings.coverTemplate = .collage
            book.addCover(MemoirCoverPhoto(id: photo.id, sourceMemoryId: edited.id))
            book.importCover(image)
            #expect(await book.sync())
            let cloudBook = try await BackendRepository(client: client).memoir(personID: person.id)
            #expect(cloudBook.settings == book.settings && cloudBook.settings.coverPhotos.count == 2)
            await book.generatePreview()
            let preview = try #require(book.preview)
            let pdf = try #require(PDFDocument(url: preview.url))
            #expect(pdf.pageCount >= 3 && pdf.string?.contains(edited.title) == true)
            #expect(await book.verifiedShareURL() == preview.url)
            try await api.deleteMemory(edited)
            #expect(try await api.list().allSatisfy { $0.id != edited.id })
            #expect(try await api.memoir(personID: person.id).stories.isEmpty)
            try await api.deleteMember(id: person.id)
            #expect(try await api.members().allSatisfy { $0.id != person.id })
            print("BETTERUI_ISOLATED_FLOW_PASS: real AI, photos, draft revisions, confirmation, editing conflicts, cloud memoir, PDF, deletion")
        } catch {
            try? await api.deleteMember(id: person.id)
            throw error
        }
    }
}
