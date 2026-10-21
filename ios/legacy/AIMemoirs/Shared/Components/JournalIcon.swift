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
