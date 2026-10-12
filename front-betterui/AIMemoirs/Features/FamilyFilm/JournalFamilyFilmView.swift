import SwiftUI

/// 主标签页展示三位家人的胶卷预览；更多家人通过独立入口查看，避免首页无限堆叠。
struct JournalFamilyFilmView: View {
    var body: some View {
        FamilyFilmCollectionView(showsAll: false)
    }
}
