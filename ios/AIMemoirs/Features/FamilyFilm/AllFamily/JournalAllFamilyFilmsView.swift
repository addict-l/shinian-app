import SwiftUI

/// 全部家人的胶卷目录，保留主导航，支持姓名与家庭身份搜索。
struct JournalAllFamilyFilmsView: View {
    var body: some View {
        FamilyFilmCollectionView(showsAll: true)
    }
}
