import SwiftUI

/// 对话请求状态：负责会话、消息和草稿生成，页面通过注入的 ChatAPI 访问后端。
@MainActor
final class ChatViewModel: ObservableObject {
    @Published private(set) var isLoading = false
    @Published private(set) var canGenerate = false
    @Published var errorMessage: String?
    private let api: any ChatAPI
    private var sessionID: UUID?
    private var startID = UUID()
    private var pendingMessage: (text: String, id: UUID)?
    private var uploadID = UUID()
    private var uploadedImage: Data?
    private var pendingImage: Data?

    init(api: (any ChatAPI)? = nil) { self.api = api ?? BackendRepository.shared }

    func reset() {
        sessionID = nil; startID = UUID(); pendingMessage = nil
        uploadedImage = nil; uploadID = UUID(); canGenerate = false
    }

    func start(person: FamilyMember) async -> ChatSnapshot? {
        guard !isLoading else { return nil }
        isLoading = true; errorMessage = nil
        defer { isLoading = false }
        do {
            let value = try await api.start(person: person, requestID: startID)
            sessionID = value.sessionID; canGenerate = value.canGenerate
            return value
        } catch is CancellationError {
            return nil
        } catch {
            errorMessage = error.localizedDescription; return nil
        }
    }

    func send(text: String, person: FamilyMember) async -> ChatSnapshot? {
        if sessionID == nil, await start(person: person) == nil { return nil }
        guard !isLoading, let sessionID else { return nil }
        isLoading = true; errorMessage = nil
        defer { isLoading = false }
        if pendingMessage?.text != text { pendingMessage = (text, UUID()) }
        guard let request = pendingMessage else { return nil }
        do {
            let value = try await api.send(sessionID: sessionID, text: request.text, requestID: request.id)
            pendingMessage = nil; canGenerate = value.canGenerate
            return value
        } catch is CancellationError {
            return nil
        } catch {
            errorMessage = error.localizedDescription; return nil
        }
    }

    func generate(image: Data?) async -> GeneratedMemory? {
        guard !isLoading, canGenerate, let sessionID else { return nil }
        isLoading = true; errorMessage = nil
        defer { isLoading = false }
        do {
            if image != pendingImage { uploadID = UUID(); pendingImage = image }
            if image == nil || uploadedImage != image {
                try await api.upload(sessionID: sessionID, image: image, requestID: uploadID)
                uploadedImage = image
            }
            return try await api.generate(sessionID: sessionID)
        } catch is CancellationError {
            return nil
        } catch {
            errorMessage = error.localizedDescription; return nil
        }
    }
}
