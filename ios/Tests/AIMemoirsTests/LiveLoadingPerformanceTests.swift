import XCTest
import UIKit
@testable import AIMemoirs

private final class LoadingTaskMetrics: NSObject, URLSessionTaskDelegate, @unchecked Sendable {
    private let lock = NSLock()
    private var records: [[String: Any]] = []
    var values: [[String: Any]] { lock.lock(); defer { lock.unlock() }; return records }
    func urlSession(_ session: URLSession, task: URLSessionTask, didFinishCollecting metrics: URLSessionTaskMetrics) {
        let raw = task.originalRequest?.url?.path ?? ""
        let path = raw.hasPrefix("/api/v1/media/") ? "/api/v1/media/:id" : raw.hasPrefix("/api/v1/family-members/") && task.originalRequest?.httpMethod == "DELETE" ? "/api/v1/family-members/:id" : raw.hasPrefix("/api/v1/memories/") && task.originalRequest?.httpMethod == "DELETE" ? "/api/v1/memories/:id" : raw
        func seconds(_ start: Date?, _ end: Date?) -> Any { if let start, let end { return end.timeIntervalSince(start) }; return NSNull() }
        let value: [String: Any] = ["path": path, "method": task.originalRequest?.httpMethod ?? "", "response_bytes": task.countOfBytesReceived,
            "status": (task.response as? HTTPURLResponse)?.statusCode ?? 0,
            "task_seconds": metrics.taskInterval.duration, "transactions": metrics.transactionMetrics.map { transaction in
                ["dns_seconds": seconds(transaction.domainLookupStartDate, transaction.domainLookupEndDate),
                 "connect_seconds": seconds(transaction.connectStartDate, transaction.connectEndDate),
                 "tls_seconds": seconds(transaction.secureConnectionStartDate, transaction.secureConnectionEndDate),
                 "response_wait_seconds": seconds(transaction.requestEndDate, transaction.responseStartDate),
                 "body_transfer_seconds": seconds(transaction.responseStartDate, transaction.responseEndDate),
                 "network_protocol": transaction.networkProtocolName as Any? ?? NSNull()] as [String: Any]
            }]
        lock.lock(); records.append(value); lock.unlock()
    }
}

/// Explicit disposable Aliyun fixtures, staged only inside the separate simulator App.
@MainActor final class LiveLoadingPerformanceTests: XCTestCase {
    private struct Target: Decodable { let id: UUID }
    private struct Targets: Decodable { let delete_person: Target; let delete_memory: Target }
    private struct Fixture: Decodable {
        let isolated: Bool
        let username: String
        let password: String
        let family_id: UUID
        let fixtures: [String: Targets]
    }
    private let baseURL = URL(string: "http://127.0.0.1:17655")!
    private let metrics = LoadingTaskMetrics()
    private lazy var transport = URLSession(configuration: .ephemeral, delegate: metrics, delegateQueue: nil)
    private var documents: URL { FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0] }
    private func fixture() throws -> Fixture {
        guard Bundle.main.bundleIdentifier == "com.shinian.validation.performance" else { throw XCTSkip("Separate validation App only") }
        let file = documents.appendingPathComponent("loading-live.private.json")
        guard FileManager.default.fileExists(atPath: file.path) else { throw XCTSkip("Explicit disposable fixture is required") }
        let permissions = try FileManager.default.attributesOfItem(atPath: file.path)[.posixPermissions] as? NSNumber
        guard let permissions, permissions.intValue & 0o077 == 0 else { throw XCTSkip("Private fixture permissions are required") }
        let value = try JSONDecoder().decode(Fixture.self, from: Data(contentsOf: file))
        guard value.isolated, value.fixtures["ios"] != nil else { throw XCTSkip("Owned iOS disposable targets are required") }
        return value
    }
    private func login(_ fixture: Fixture) async throws -> (BackendRepository, TimeInterval) {
        let authentication = AuthenticationStore(client: APIClient(baseURL: baseURL, session: transport))
        let start = Date()
        await authentication.login(username: fixture.username, password: fixture.password)
        guard authentication.isAuthenticated, let session = authentication.session, session.familyID == fixture.family_id else {
            XCTFail("Disposable candidate authentication failed"); throw APIError.authenticationRequired
        }
        // The hosted App may still finish restoring its previous device session.
        // Bind this explicit test client to this server-validated login response.
        var client = APIClient(baseURL: baseURL, session: transport)
        client.authorizationProvider = { "Bearer " + session.token }
        return (BackendRepository(client: client), Date().timeIntervalSince(start))
    }
    private func report(_ values: [String: Any], name: String) throws {
        try JSONSerialization.data(withJSONObject: values, options: [.sortedKeys, .prettyPrinted])
            .write(to: documents.appendingPathComponent(name), options: .atomic)
    }

    func testAStageRealLoginHomeAndLazyPhoto() async throws {
        let fixture = try fixture()
        do {
            let (api, loginSeconds) = try await login(fixture)
            let members = FamilyMemberStore(api: api), memories = MemoryListViewModel(api: api)
            let start = Date()
            await members.load(with: memories)
            let homeSeconds = Date().timeIntervalSince(start)
            guard members.errorMessage == nil, memories.errorMessage == nil else { XCTFail("Candidate metadata load failed"); return }
            let target = fixture.fixtures["ios"]!
            guard members.members.contains(where: { $0.id == target.delete_person.id }),
                  let memory = memories.memoryEvents.first(where: { $0.id == target.delete_memory.id }) else {
                XCTFail("Owned candidate fixtures are missing"); return
            }
            XCTAssertNil(memory.imageData, "List completion must not wait for a cover download")
            XCTAssertTrue(memory.hasPhoto)
            let loader = JournalPhotoLoader(), photoStart = Date()
            await loader.load(memory: memory, api: api)
            let photoSeconds = Date().timeIntervalSince(photoStart)
            XCTAssertFalse(loader.failed)
            guard let data = loader.data, UIImage(data: data) != nil else { XCTFail("Candidate private photo did not decode"); return }
            try report(["completed": true, "isolated": true, "platform": "ios", "login_seconds": loginSeconds,
                "home_metadata_seconds": homeSeconds, "lazy_photo_seconds": photoSeconds,
                "photo_bytes": data.count, "people": members.members.count, "memories": memories.memoryEvents.count,
                "photos_do_not_block_list": true, "transport_metrics": metrics.values], name: "loading-live-reads-report.json")
            print("IOS_CANDIDATE_READS_PASS login_seconds=\(loginSeconds) home_metadata_seconds=\(homeSeconds) lazy_photo_seconds=\(photoSeconds)")
        } catch { XCTFail("Candidate read verification failed with category " + String(describing: type(of: error))) }
    }

    func testZRealMemoryAndPersonDeletion() async throws {
        let fixture = try fixture()
        do {
            let (api, _) = try await login(fixture)
            let members = FamilyMemberStore(api: api), memories = MemoryListViewModel(api: api)
            await members.load(with: memories)
            guard members.hasLoaded, memories.hasLoaded, members.errorMessage == nil, memories.errorMessage == nil else {
                try report(["completed": false, "stage": "metadata", "members_loaded": members.hasLoaded,
                    "memories_loaded": memories.hasLoaded, "members_error": members.errorMessage != nil,
                    "memories_error": memories.errorMessage != nil, "transport_metrics": metrics.values], name: "loading-live-deletes-report.json")
                XCTFail("Candidate metadata did not load; no deletion was attempted"); return
            }
            let target = fixture.fixtures["ios"]!
            let person = try XCTUnwrap(members.members.first { $0.id == target.delete_person.id })
            let memory = try XCTUnwrap(memories.memoryEvents.first { $0.id == target.delete_memory.id })
            var cleaned = false
            let start = Date()
            try await memories.delete(memory) {
                let people = memory.primaryPersonID.map { Set([$0]) } ?? Set(memory.personIDs)
                try ChatDraftStore.current(previewScreen: nil)?.invalidateHistory(personIDs: people, deletedSessionID: memory.sourceSessionID)
                cleaned = true
            }
            members.updateMemoryCounts(from: memories.memoryEvents)
            let memorySeconds = Date().timeIntervalSince(start)
            XCTAssertTrue(cleaned)
            XCTAssertFalse(memories.memoryEvents.contains { $0.id == memory.id })
            let personStart = Date()
            let deleted = await members.delete(person, updating: memories)
            let personSeconds = Date().timeIntervalSince(personStart)
            XCTAssertTrue(deleted)
            XCTAssertFalse(members.members.contains { $0.id == person.id })
            let peopleAfter = try await api.members(), memoriesAfter = try await api.list()
            XCTAssertFalse(peopleAfter.contains { $0.id == person.id })
            XCTAssertFalse(memoriesAfter.contains { $0.id == memory.id })
            try report(["completed": true, "isolated": true, "platform": "ios",
                "memory_delete_seconds": memorySeconds, "person_delete_seconds": personSeconds,
                "local_history_cleanup_completed": cleaned, "server_removal_verified": true, "transport_metrics": metrics.values], name: "loading-live-deletes-report.json")
            print("IOS_CANDIDATE_DELETES_PASS memory_seconds=\(memorySeconds) person_seconds=\(personSeconds)")
        } catch { XCTFail("Candidate delete verification failed with category " + String(describing: type(of: error))) }
    }
}
