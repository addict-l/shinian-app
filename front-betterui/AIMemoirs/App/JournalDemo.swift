import Foundation

/// 通过 Scheme 环境变量或 --design-screen 参数打开设计稿的指定页面。
/// 仅 Debug 显式指定页面时启用离线设计预览；正常启动始终连接后端。
enum JournalDemo {
    static var isPreview: Bool { screen != nil }
    static var screen: String? {
        #if DEBUG
        if let value = ProcessInfo.processInfo.environment["AI_MEMORIES_DESIGN_SCREEN"] { return value }
        let arguments = ProcessInfo.processInfo.arguments
        guard let index = arguments.firstIndex(of: "--design-screen"), arguments.indices.contains(index + 1) else { return nil }
        return arguments[index + 1]
        #else
        return nil
        #endif
    }
}
