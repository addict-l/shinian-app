import SwiftUI

/// 统一设计图标，使用资源目录中的模板图片。
struct JournalIcon: View {
    let name: String
    var size: CGFloat = 22
    var body: some View {
        Image("JournalIcon-" + name).resizable().renderingMode(.template)
            .scaledToFit().frame(width: size, height: size).accessibilityHidden(true)
    }
}

/// 设计稿中的 1.7pt 线性图标（DesignIcon-*）。
struct DesignIcon: View {
    let name: String
    var size: CGFloat = 22
    init(_ name: String, size: CGFloat = 22) { self.name = name; self.size = size }
    var body: some View {
        Image("DesignIcon-" + name).resizable().renderingMode(.template)
            .scaledToFit().frame(width: size, height: size).accessibilityHidden(true)
    }
}
