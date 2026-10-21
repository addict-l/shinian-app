import SwiftUI
import PhotosUI

struct ChatMessage: Identifiable, Codable {
    enum Sender: String, Codable {
        case user, ai
    }
    var id = UUID()
    let sender: Sender
    let text: String
    var attachments: [ChatAttachment] = []
}

// MARK: - 分离子视图组件
