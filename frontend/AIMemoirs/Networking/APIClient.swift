import Foundation

enum APIError: LocalizedError {
    case contractUnavailable, insecureURL, invalidResponse, decoding, timeout, network, authenticationRequired
    case httpStatus(Int)
    case server(String)
    var errorDescription: String? {
        switch self {
        case .contractUnavailable: return "此功能尚未接入后端。"
        case .insecureURL: return "请配置 HTTPS 服务器；本机调试仅允许 localhost。"
        case .invalidResponse: return "服务器响应无效。"
        case .httpStatus(let code): return "请求失败（HTTP \(code)）。"
        case .server(let message): return message
        case .decoding: return "服务器返回的数据格式不匹配。"
        case .timeout: return "请求超时，请重试；重复提交不会重复保存。"
        case .network: return "无法连接本机服务器，请确认后端正在运行。"
        case .authenticationRequired: return "登录已失效，请重新登录。"
        }
    }
}

struct APIClient {
    let baseURL: URL
    var session: URLSession = .shared

    static var local: APIClient {
        #if DEBUG
        let fallback = "http://localhost:8000"
        #else
        let fallback = ""
        #endif
        let address = ProcessInfo.processInfo.environment["AI_MEMORIES_API_URL"]
            ?? Bundle.main.object(forInfoDictionaryKey: "AI_MEMORIES_API_URL") as? String ?? fallback
        return APIClient(baseURL: URL(string: address) ?? URL(string: "about:blank")!)
    }

    func send<Response: Decodable>(path: String, method: String, body: Data? = nil,
                                   query: [URLQueryItem] = [], as: Response.Type) async throws -> Response {
        let data = try await request(path: path, method: method, body: body, query: query)
        do { return try JSONDecoder().decode(Response.self, from: data) }
        catch { throw APIError.decoding }
    }

    func request(path: String, method: String, body: Data? = nil,
                 query: [URLQueryItem] = [], contentType: String = "application/json") async throws -> Data {
        var allowed = baseURL.scheme == "https" && baseURL.host != nil
        #if DEBUG
        allowed = allowed || (baseURL.scheme == "http" && ["localhost", "127.0.0.1"].contains(baseURL.host ?? ""))
        #endif
        guard allowed else { throw APIError.insecureURL }
        var components = URLComponents(url: baseURL.appendingPathComponent(path), resolvingAgainstBaseURL: false)!
        if !query.isEmpty { components.queryItems = query }
        guard let url = components.url else { throw APIError.insecureURL }
        var request = URLRequest(url: url, timeoutInterval: 120)
        request.httpMethod = method
        request.httpBody = body
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        if let authorization = BasicCredentialStore.shared.authorizationHeader {
            request.setValue(authorization, forHTTPHeaderField: "Authorization")
        }
        if body != nil { request.setValue(contentType, forHTTPHeaderField: "Content-Type") }
        do {
            let (data, response) = try await session.data(for: request)
            guard let http = response as? HTTPURLResponse else { throw APIError.invalidResponse }
            if http.statusCode == 401 { throw APIError.authenticationRequired }
            guard (200..<300).contains(http.statusCode) else {
                if let detail = (try? JSONSerialization.jsonObject(with: data)) as? [String: Any],
                   let message = detail["detail"] as? String { throw APIError.server(message) }
                if http.statusCode == 422 { throw APIError.server("填写的信息不符合要求，请检查姓名、身份和生日。") }
                throw APIError.httpStatus(http.statusCode)
            }
            return data
        } catch is CancellationError { throw CancellationError() }
        catch let error as URLError where error.code == .cancelled { throw CancellationError() }
        catch let error as APIError { throw error }
        catch let error as URLError where error.code == .timedOut { throw APIError.timeout }
        catch { throw APIError.network }
    }
}
