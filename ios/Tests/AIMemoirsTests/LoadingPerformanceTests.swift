import XCTest
@testable import AIMemoirs

private final class LoadingProtocol: URLProtocol, @unchecked Sendable {
    private static let lock = NSLock()
    nonisolated(unsafe) private static var responseHandler: ((URLRequest) -> (Int, Data, TimeInterval))?
    nonisolated(unsafe) private static var recordedPaths: [String] = []
    static var handler: ((URLRequest) -> (Int, Data, TimeInterval))? {
        get { lock.lock(); defer { lock.unlock() }; return responseHandler }
        set { lock.lock(); defer { lock.unlock() }; responseHandler = newValue }
    }
    static var paths: [String] {
        get { lock.lock(); defer { lock.unlock() }; return recordedPaths }
        set { lock.lock(); defer { lock.unlock() }; recordedPaths = newValue }
    }
    private var work: DispatchWorkItem?
    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }
    override func startLoading() {
        Self.lock.lock()
        Self.recordedPaths.append(request.url!.path.trimmingCharacters(in: CharacterSet(charactersIn: "/")))
        Self.lock.unlock()
        let (status, data, delay) = Self.handler!(request)
        let work = DispatchWorkItem { [weak self] in
            guard let self else { return }
            self.client?.urlProtocol(self, didReceive: HTTPURLResponse(url: self.request.url!, statusCode: status,
                httpVersion: nil, headerFields: nil)!, cacheStoragePolicy: .notAllowed)
            self.client?.urlProtocol(self, didLoad: data)
            self.client?.urlProtocolDidFinishLoading(self)
        }
        self.work = work
        DispatchQueue.main.asyncAfter(deadline: .now() + delay, execute: work)
    }
    override func stopLoading() { work?.cancel() }
}

@MainActor final class LoadingPerformanceTests: XCTestCase {
    private let family = "22222222-2222-4222-8222-222222222222"
    private let person = "33333333-3333-4333-8333-333333333333"
    private func repository() -> BackendRepository {
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [LoadingProtocol.self]
        var client = APIClient(baseURL: URL(string: "https://loading.invalid")!, session: URLSession(configuration: configuration))
        client.authorizationProvider = { "Bearer synthetic-performance-session" }
        LoadingProtocol.paths = []
        LoadingProtocol.handler = { [family, person] request in
            let path = request.url!.path.trimmingCharacters(in: CharacterSet(charactersIn: "/"))
            let body: Any
            if path == "api/v1/auth/me" { body = ["family_id": family] }
            else if path == "api/v1/family-members" {
                body = [["id": person, "name": "测试家人", "relationship": "家人"]]
            } else if path == "api/v1/memories" {
                body = (1...4).map { index in
                    ["id": "44444444-4444-4444-8444-44444444444\(index)", "person_ids": [person],
                     "title": "测试回忆\(index)", "raw_content": "合成的测试回忆", "version": 1,
                     "media_urls": ["/api/v1/media/55555555-5555-4555-8555-55555555555\(index)"],
                     "media_assets": [["id": "55555555-5555-4555-8555-55555555555\(index)",
                         "url": "/api/v1/media/55555555-5555-4555-8555-55555555555\(index)",
                         "position": 0]]] as [String: Any]
                }
            } else if path.hasPrefix("api/v1/media/") { return (200, Data([1, 2, 3]), 0.25) }
            else { return (204, Data(), 0.03) }
            return (200, try! JSONSerialization.data(withJSONObject: body), 0.03)
        }
        return BackendRepository(client: client)
    }

    func testHomeMetadataDoesNotWaitForPhotosOrRepeatLists() async throws {
        let api = repository()
        let members = FamilyMemberStore(api: api)
        let memories = MemoryListViewModel(api: api)
        let start = Date()
        // Same call chain used by JournalAppView on first authenticated launch.
        await members.load(with: memories)
        let elapsed = Date().timeIntervalSince(start)
        print("IOS_HOME_METADATA_SECONDS=\(elapsed) REQUESTS=\(LoadingProtocol.paths.count)")
        XCTAssertNil(members.errorMessage)
        XCTAssertNil(memories.errorMessage)
        XCTAssertEqual(members.members.first?.memoryCount, 4)
        XCTAssertEqual(memories.memoryEvents.count, 4)
        XCTAssertTrue(memories.memoryEvents.allSatisfy { $0.personName == "测试家人" })
        XCTAssertLessThan(elapsed, 0.5, "Opening the family must not wait for every photo")
        XCTAssertEqual(LoadingProtocol.paths.filter { $0 == "api/v1/family-members" }.count, 1)
        XCTAssertEqual(LoadingProtocol.paths.filter { $0 == "api/v1/memories" }.count, 1)
        XCTAssertFalse(LoadingProtocol.paths.contains { $0.hasPrefix("api/v1/media/") })
    }

    func testExplicitRefreshReadsChangedServerDataAndEmptyFamilyOnce() async throws {
        let api = repository()
        // Use the same API as the application; separate adapters must never share a cache.
        let people = FamilyMemberStore(api: api), memories = MemoryListViewModel(api: api)
        await people.load(with: memories)
        XCTAssertEqual(memories.memoryEvents.count, 4)
        let original = LoadingProtocol.handler!
        LoadingProtocol.paths = []
        LoadingProtocol.handler = { request in
            if ["/api/v1/family-members", "/api/v1/memories"].contains(request.url!.path) {
                return (200, Data("[]".utf8), 0.03)
            }
            return original(request)
        }
        await people.load(with: memories)
        XCTAssertTrue(people.hasLoaded && memories.hasLoaded)
        XCTAssertTrue(people.members.isEmpty && memories.memoryEvents.isEmpty)
        XCTAssertEqual(LoadingProtocol.paths.filter { $0 == "api/v1/family-members" }.count, 1)
        XCTAssertEqual(LoadingProtocol.paths.filter { $0 == "api/v1/memories" }.count, 1)
        XCTAssertEqual(LoadingProtocol.paths.count, 2)
    }

    func testFailedSharedReadCanRetryWithoutRetainingFailedTask() async throws {
        let api = repository()
        let members = FamilyMemberStore(api: api), memories = MemoryListViewModel(api: api)
        let original = LoadingProtocol.handler!
        LoadingProtocol.handler = { request in
            if request.url!.path == "/api/v1/memories" { return (503, Data(), 0.03) }
            return original(request)
        }
        await members.load(with: memories)
        XCTAssertNotNil(members.errorMessage)
        XCTAssertNotNil(memories.errorMessage)
        LoadingProtocol.handler = original
        LoadingProtocol.paths = []
        await members.load(with: memories)
        XCTAssertNil(members.errorMessage)
        XCTAssertNil(memories.errorMessage)
        XCTAssertEqual(members.members.first?.memoryCount, 4)
        XCTAssertEqual(memories.memoryEvents.count, 4)
        XCTAssertEqual(LoadingProtocol.paths.count, 2)
    }

    func testPersonDeletionWaitsOnlyForDeleteAndPreservesRetainedStories() async throws {
        let api = repository()
        let people = FamilyMemberStore(api: api), memories = MemoryListViewModel(api: api)
        await people.load(with: memories)
        let member = try XCTUnwrap(people.members.first)
        let original = LoadingProtocol.handler!
        LoadingProtocol.handler = { request in
            if request.httpMethod == "DELETE" { return (503, Data(), 0.03) }
            return original(request)
        }
        let failed = await people.delete(member, updating: memories)
        XCTAssertFalse(failed)
        XCTAssertEqual(people.members.count, 1)
        XCTAssertEqual(memories.memoryEvents.count, 4)
        LoadingProtocol.handler = original; LoadingProtocol.paths = []
        let start = Date()
        let deleted = await people.delete(member, updating: memories)
        XCTAssertTrue(deleted)
        XCTAssertLessThan(Date().timeIntervalSince(start), 0.2)
        XCTAssertTrue(people.members.isEmpty)
        XCTAssertEqual(memories.memoryEvents.count, 4)
        XCTAssertTrue(memories.memoryEvents.allSatisfy { $0.personIDs.isEmpty })
        XCTAssertEqual(LoadingProtocol.paths.count, 1, "Deletion must not refresh unrelated lists or photos")
    }

    func testMemoryDeleteFailureConflictCleanupAndCompletion() async throws {
        let api = repository(), members = FamilyMemberStore(api: api), memories = MemoryListViewModel(api: api)
        await members.load(with: memories)
        let memory = try XCTUnwrap(memories.memoryEvents.first)
        let original = LoadingProtocol.handler!
        var cleaned = false
        for status in [503, 409] {
            LoadingProtocol.handler = { request in
                if request.httpMethod == "DELETE" { return (status, Data(#"{"detail":"synthetic deletion rejection"}"#.utf8), 0.03) }
                return original(request)
            }
            do { try await memories.delete(memory) { cleaned = true }; XCTFail("Must reject failed DELETE") }
            catch { if status == 409 { XCTAssertTrue(isVersionConflict(error)) } }
            XCTAssertFalse(cleaned)
            XCTAssertEqual(memories.memoryEvents.count, 4)
        }
        LoadingProtocol.handler = original; LoadingProtocol.paths = []
        enum CleanupFailure: Error { case retry }
        do { try await memories.delete(memory) { throw CleanupFailure.retry }; XCTFail("Must retain cleanup retry") }
        catch { XCTAssertEqual(memories.memoryEvents.count, 4) }
        let start = Date()
        try await memories.delete(memory) { cleaned = true }
        members.updateMemoryCounts(from: memories.memoryEvents)
        XCTAssertTrue(cleaned)
        XCTAssertLessThan(Date().timeIntervalSince(start), 0.2)
        XCTAssertEqual(memories.memoryEvents.count, 3)
        XCTAssertEqual(members.members.first?.memoryCount, 3)
        XCTAssertEqual(LoadingProtocol.paths.count, 2)
    }

    func testOldRefreshCannotResurrectDeletedMemory() async throws {
        let api = repository(), memories = MemoryListViewModel(api: api)
        await memories.load()
        let memory = try XCTUnwrap(memories.memoryEvents.first)
        let original = LoadingProtocol.handler!
        LoadingProtocol.paths = []
        LoadingProtocol.handler = { request in
            let result = original(request)
            return (result.0, result.1, 0.15)
        }
        let refresh = Task { await memories.load() }
        while !LoadingProtocol.paths.contains("api/v1/memories") { try await Task.sleep(nanoseconds: 1_000_000) }
        memories.remove(id: memory.id)
        await refresh.value
        XCTAssertFalse(memories.memoryEvents.contains { $0.id == memory.id })
        XCTAssertEqual(memories.memoryEvents.count, 3)
    }

    func testUnlinkPreservesSharedStoryAndOtherParticipants() {
        let deleted = UUID(), retained = FamilyMember(id: UUID(), name: "保留家人", gender: .unspecified)
        var memory = MemoryEvent(personName: "两位家人", personIDs: [deleted, retained.id], date: nil, content: "原文", title: "共同回忆")
        memory.primaryPersonID = deleted; memory.sourceSessionID = UUID(); memory.version = 3
        let result = memory.removing(personID: deleted, remainingMembers: [retained])
        XCTAssertEqual(result.id, memory.id)
        XCTAssertEqual(result.personIDs, [retained.id])
        XCTAssertEqual(result.personName, retained.name)
        XCTAssertNil(result.primaryPersonID)
        XCTAssertEqual(result.sourceSessionID, memory.sourceSessionID)
        XCTAssertEqual(result.content, memory.content)
        XCTAssertEqual(result.version, 3)
    }

    func testLazyPhotoSwapAndRemovalCannotKeepOldImage() async throws {
        let api = repository()
        let photos = try await api.list()
        let loader = JournalPhotoLoader()
        let original = LoadingProtocol.handler!
        let first = photos[0], second = photos[1]
        LoadingProtocol.handler = { request in
            if request.url!.path.contains(first.mediaAssets[0].id.uuidString.lowercased()) { return (200, Data([1]), 0.15) }
            if request.url!.path.contains(second.mediaAssets[0].id.uuidString.lowercased()) { return (200, Data([2]), 0.02) }
            return original(request)
        }
        let older = Task { await loader.load(memory: first, api: api) }
        try await Task.sleep(nanoseconds: 10_000_000)
        await loader.load(memory: second, api: api)
        XCTAssertEqual(loader.data, Data([2]))
        await older.value
        XCTAssertEqual(loader.data, Data([2]))
        var withoutPhoto = second; withoutPhoto.mediaAssets = []
        await loader.load(memory: withoutPhoto, api: api)
        XCTAssertNil(loader.data)
        XCTAssertFalse(loader.failed)
    }
}
