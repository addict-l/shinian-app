import SwiftUI
import PhotosUI

struct ChatMessage: Identifiable {
    enum Sender {
        case user, ai
    }
    var id = UUID()
    let sender: Sender
    let text: String
}

// MARK: - 分离子视图组件
