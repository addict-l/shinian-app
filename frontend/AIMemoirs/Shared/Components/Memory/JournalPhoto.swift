import SwiftUI

/// 回忆图片展示与缺省占位，统一裁切和无障碍描述。
struct JournalPhoto: View {
    let memory: MemoryEvent
    let height: CGFloat
    var radius: CGFloat = 18
    var body: some View {
        GeometryReader { proxy in
            Group {
                if let data = memory.imageData, let image = UIImage(data: data) {
                    Image(uiImage: image).resizable().scaledToFill()
                } else if let name = memory.imageName, UIImage(named: name) != nil {
                    Image(name).resizable().scaledToFill()
                } else {
                    ZStack {
                        JournalTheme.soft
                        Image(systemName: "book.closed").font(.system(size: 36, weight: .light))
                            .foregroundStyle(JournalTheme.accent.opacity(0.65))
                    }
                }
            }
            .frame(width: proxy.size.width, height: height).clipped()
        }
        .frame(height: height).clipShape(RoundedRectangle(cornerRadius: radius))
        .accessibilityLabel("回忆照片：\(memory.title)")
    }
}
