import SwiftUI

/// 应用装配入口：创建共享状态、注入 API，并组装主页面及详情路由。
struct JournalAppView: View {
    @StateObject private var members: FamilyMemberStore
    @StateObject private var memories: MemoryListViewModel
    @StateObject private var navigation = JournalNavigation()
    private let chatAPI: any ChatAPI
    private let memoryAPI: any MemoryAPI
    private let previewScreen: String?
    @State private var previewReady = false

    init() {
        #if DEBUG
        if let screen = ProcessInfo.processInfo.environment["AI_MEMORIES_DESIGN_SCREEN"] {
            let api = JournalPreviewAPI(familyFilm: ["film", "tree"].contains(screen), emptyState: screen)
            _members = StateObject(wrappedValue: FamilyMemberStore(api: api))
            _memories = StateObject(wrappedValue: MemoryListViewModel(api: api))
            chatAPI = api; memoryAPI = api; previewScreen = screen
            return
        }
        #endif
        _members = StateObject(wrappedValue: FamilyMemberStore())
        _memories = StateObject(wrappedValue: MemoryListViewModel())
        chatAPI = BackendRepository.shared; memoryAPI = BackendRepository.shared; previewScreen = nil
    }

    private var dark: Bool { false }

    /// The tab content is deliberately kept in one navigation stack so a person or
    /// memory can be opened from any tab without recreating the data stores.
    var body: some View {
        VStack(spacing: 0) {
            content
            JournalTabBar(selection: $navigation.tab, dark: dark)
        }
        .background(JournalTheme.paper.ignoresSafeArea())
        .environmentObject(members).environmentObject(memories).environmentObject(navigation)
        .environment(\.locale, Locale(identifier: "zh_CN"))
        .font(JournalTheme.font(15)).foregroundStyle(JournalTheme.ink)
        .tint(JournalTheme.accent).preferredColorScheme(dark ? .dark : .light)
        .onChange(of: navigation.tab) { _, _ in navigation.path.removeAll() }
        .task {
            await members.load(); await memories.load()
            guard !previewReady else { return }; previewReady = true
            if let previewScreen {
                switch previewScreen {
                case "tree", "film": navigation.tab = .family
                case "profile": navigation.tab = .profile
                case "add": navigation.compose()
                case "select": navigation.compose(step: .select)
                case "chat", "review": navigation.compose(with: members.members.first)
                case "memories": navigation.path = [.memories]
                case "person": if let person = members.members.first { navigation.path = [.person(person.id)] }
                default: break
                }
            }
        }
    }

    // Reserve actual layout space for the custom tab bar, including on non-scroll pages.
    private var content: some View {
        NavigationStack(path: $navigation.path) {
            TabView(selection: $navigation.tab) {
                JournalHomeView().toolbar(.hidden, for: .tabBar).tag(JournalTab.home)
                JournalComposeView(chatAPI: chatAPI, memoryAPI: memoryAPI, previewScreen: previewScreen).toolbar(.hidden, for: .tabBar).tag(JournalTab.compose)
                JournalFamilyFilmView().toolbar(.hidden, for: .tabBar).tag(JournalTab.family)
                JournalProfileView().toolbar(.hidden, for: .tabBar).tag(JournalTab.profile)
            }
            .toolbar(.hidden, for: .tabBar).toolbar(.hidden, for: .navigationBar)
            .navigationDestination(for: JournalRoute.self) { route in
                switch route {
                case .memories: JournalMemoriesView()
                case .familyFilms: JournalAllFamilyFilmsView()
                case .person(let id):
                    if let person = members.members.first(where: { $0.id == id }) { JournalPersonView(person: person) }
                case .memory(let id):
                    if let event = memories.memoryEvents.first(where: { $0.id == id }) { JournalStoryView(memory: event) }
                case .settings: JournalSettingsView()
                case .privacy: JournalPrivacyView()
                }
            }
        }
    }
}
