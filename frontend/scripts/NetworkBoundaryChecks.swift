import Foundation

private final class StubProtocol: URLProtocol {
    static var handler: (URLRequest) throws -> (Int, Data) = { _ in (200, Data()) }
    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }
    override func startLoading() {
        do {
            let (status, data) = try Self.handler(request)
            let response = HTTPURLResponse(url: request.url!, statusCode: status, httpVersion: nil, headerFields: nil)!
            client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
            client?.urlProtocol(self, didLoad: data)
            client?.urlProtocolDidFinishLoading(self)
        } catch { client?.urlProtocol(self, didFailWithError: error) }
    }
    override func stopLoading() {}
}

@main
struct NetworkBoundaryChecks {
    struct Payload: Codable { let value: Int }
    static func main() async throws {
        let config = URLSessionConfiguration.ephemeral
        config.protocolClasses = [StubProtocol.self]
        let client = APIClient(baseURL: URL(string: "https://example.invalid/api")!, session: URLSession(configuration: config))
        // Reserved .invalid domain: all requests intercepted, no external network.
        StubProtocol.handler = { request in
            precondition(request.url?.path == "/api/fixture")
            precondition(request.httpMethod == "POST")
            precondition(request.value(forHTTPHeaderField: "Content-Type") == "application/json")
            precondition(request.httpBody != nil || request.httpBodyStream != nil)
            return (201, Data(#"{"value":7}"#.utf8))
        }
        let value = try await client.send(path: "fixture", method: "POST", body: JSONEncoder().encode(Payload(value: 3)), as: Payload.self)
        precondition(value.value == 7)
        print("PASS typed 201 response, method/path/body/headers")
        for status in [400, 401, 404, 500, 503] {
            StubProtocol.handler = { _ in (status, Data()) }
            do { _ = try await client.request(path: "fixture", method: "GET"); fatalError("expected status error") }
            catch APIError.httpStatus(let actual) { precondition(actual == status) }
        }
        print("PASS 4xx/5xx errors")
        StubProtocol.handler = { _ in (204, Data()) }
        let empty = try await client.request(path: "fixture", method: "DELETE")
        precondition(empty.isEmpty)
        print("PASS empty 204 response")
        StubProtocol.handler = { _ in (200, Data("invalid".utf8)) }
        do { let _: Payload = try await client.send(path: "fixture", method: "GET", as: Payload.self); fatalError("expected decoding error") }
        catch APIError.decoding { }
        print("PASS decoding error")
        StubProtocol.handler = { _ in throw URLError(.timedOut) }
        do { _ = try await client.request(path: "fixture", method: "GET"); fatalError("expected timeout") }
        catch APIError.timeout { }
        print("PASS timeout")
        StubProtocol.handler = { _ in throw URLError(.notConnectedToInternet) }
        do { _ = try await client.request(path: "fixture", method: "GET"); fatalError("expected network error") }
        catch APIError.network { }
        print("PASS network error")
        StubProtocol.handler = { _ in throw URLError(.cancelled) }
        do { _ = try await client.request(path: "fixture", method: "GET"); fatalError("expected cancellation") }
        catch is CancellationError { }
        print("PASS cancellation")
        let insecure = APIClient(baseURL: URL(string: "http://example.invalid")!)
        do { _ = try await insecure.request(path: "fixture", method: "GET"); fatalError("expected HTTPS enforcement") }
        catch APIError.insecureURL { }
        print("PASS HTTPS enforcement")
    }
}
