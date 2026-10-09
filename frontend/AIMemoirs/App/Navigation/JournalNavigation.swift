import SwiftUI

/// 全局导航状态：四个主标签共用同一条详情路径，切换页面时保留人物和回忆数据源。
enum JournalTab: String, CaseIterable, Identifiable {
    case home, compose, family, profile
    var id: String { rawValue }
    var title: String { switch self { case .home: "首页"; case .compose: "新的回忆"; case .family: "家庭胶片"; case .profile: "我的" } }
    var symbol: String { switch self { case .home: "house"; case .compose: "plus"; case .family: "film"; case .profile: "person" } }
    var designIcon: String { switch self { case .home: "home"; case .compose: "plus"; case .family: "film"; case .profile: "person" } }
}
/// Routes that sit above the four persistent tabs.
enum JournalRoute: Hashable { case memories, familyFilms, person(UUID), memory(UUID), settings, privacy }
enum JournalComposeStep { case add, select, chat }

@MainActor final class JournalNavigation: ObservableObject {
    @Published var tab: JournalTab = .home
    @Published var path: [JournalRoute] = []
    @Published var composeStep: JournalComposeStep = .add
    @Published var person: FamilyMember?
    func compose(with person: FamilyMember? = nil, step: JournalComposeStep = .add) {
        path.removeAll(); self.person = person; composeStep = person == nil ? step : .chat; tab = .compose
    }
}
