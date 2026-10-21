import SwiftUI

/// 应用装配入口：创建共享状态、注入 API，并组装主页面及详情路由。
struct JournalAppView: View {
    @StateObject private var members: FamilyMemberStore
    @StateObject private var memories: MemoryListViewModel
    @StateObject private var navigation = JournalNavigation()
    private let chatAPI: any ChatAPI
    private let memoryAPI: any MemoryAPI
    private let memoirAPI: any MemoirAPI
    private let previewScreen: String?
    @State private var previewReady = false
    @AppStorage(JournalCareMode.storageKey) private var careEnabled = false

    init() {
        let screen = JournalDemo.screen
        #if DEBUG
        if let screen {
            let api = JournalDemoAPI(emptyState: screen)
            _members = StateObject(wrappedValue: FamilyMemberStore(api: api))
            _memories = StateObject(wrappedValue: MemoryListViewModel(api: api))
            chatAPI = api; memoryAPI = api; memoirAPI = api
            previewScreen = screen
            return
        }
        #endif
        // 每次登录拥有独立的家庭缓存，四个功能共用同一真实适配器。
        let api = BackendRepository()
        _members = StateObject(wrappedValue: FamilyMemberStore(api: api))
        _memories = StateObject(wrappedValue: MemoryListViewModel(api: api))
        chatAPI = api; memoryAPI = api; memoirAPI = api
        previewScreen = nil
    }

    private var dark: Bool { false }

    /// 设计稿中：添加人物、对话、回忆详情、回忆录、设置和隐私为全屏页面，不显示主导航。
    private var showsTabBar: Bool {
        if careEnabled { return navigation.path.isEmpty && navigation.tab != .compose }
        guard let route = navigation.path.last else {
            return navigation.tab != .compose || navigation.composeStep == .select
        }
        switch route {
        case .memories, .familyFilms, .person: return true
        case .memory, .memoir, .settings, .privacy: return false
        }
    }

    /// The tab content is deliberately kept in one navigation stack so a person or
    /// memory can be opened from any tab without recreating the data stores.
    var body: some View {
        Group {
            if careEnabled {
                VStack(spacing: 0) {
                    content
                    if showsTabBar {
                        CareTabBar(selection: Binding(get: { navigation.tab }, set: { tab in
                            navigation.path.removeAll(); navigation.tab = tab
                        }))
                    }
                }
            } else {
                ZStack(alignment: .bottom) {
                    VStack(spacing: 0) {
                        content
                        if showsTabBar { Color.clear.frame(height: 66) }
                    }
                    if showsTabBar {
                        JournalTabBarFade().ignoresSafeArea(edges: .bottom)
                        JournalTabBar(selection: Binding(get: { navigation.tab }, set: { tab in
                            navigation.path.removeAll(); navigation.tab = tab
                        })).offset(y: 8)
                    }
                }
            }
        }
        .background(JournalTheme.paper.ignoresSafeArea())
        .environmentObject(members).environmentObject(memories).environmentObject(navigation)
        .environment(\.journalCareMode, careEnabled)
        .environment(\.locale, Locale(identifier: "zh_CN"))
        .font(JournalTheme.font(careEnabled ? 22 : 15)).foregroundStyle(JournalTheme.ink)
        .tint(JournalTheme.accent).preferredColorScheme(dark ? .dark : .light)
        .onChange(of: careEnabled) { _, _ in
            navigation.path.removeAll(); navigation.tab = .home; navigation.composeStep = .select
        }
        .task {
            await members.load(); await memories.load()
            guard !previewReady else { return }; previewReady = true
            if let previewScreen {
                #if DEBUG
                if previewScreen == "chat-empty-resume", let person = members.members.first,
                   let store = ChatDraftStore.current(previewScreen: previewScreen) {
                    let session = UUID()
                    let draft = LocalChatDraft(id: person.id, sessionID: session, personID: person.id,
                        personName: person.name, relationship: person.relationship, input: "本机尚未发送的文字",
                        snapshot: ChatSnapshot(sessionID: session, messages: [], canGenerate: false))
                    try? store.save(draft, photos: [])
                }
                #endif
                switch previewScreen {
                case "tree", "film": navigation.tab = .family
                case "profile": navigation.tab = .profile
                case "chat-offline": navigation.compose(with: members.members.first)
                case "add": navigation.compose(step: .add)
                case "select": navigation.compose(step: .select)
                case "chat", "chat-scroll", "chat-slow", "chat-opening", "chat-empty-resume", "chat-pending", "review": navigation.compose(with: members.members.first)
                case "memories": navigation.path = [.memories]
                case "story", "story-actions": if let event = memories.memoryEvents.first { navigation.path = [.memory(event.id)] }
                case "settings": navigation.tab = .profile; navigation.path = [.settings]
                case "privacy": navigation.tab = .profile; navigation.path = [.privacy]
                case "family-all": navigation.tab = .family; navigation.path = [.familyFilms]
                case "memory-edit", "memory-conflict": if let event = memories.memoryEvents.first { navigation.path = [.memory(event.id)] }
                case "person": navigation.tab = .family; if let person = members.members.first { navigation.path = [.person(person.id)] }
                case "memoir": if let person = members.members.first { navigation.path = [.memoir(person.id)] }
                default:
                    if previewScreen.hasPrefix("care-life") { navigation.compose(with: members.members.first) }
                }
            }
        }
    }

    // Reserve actual layout space for the custom tab bar, including on non-scroll pages.
    private var content: some View {
        NavigationStack(path: $navigation.path) {
            Group {
                if careEnabled { careTabs }
                else { TabView(selection: $navigation.tab) {
                JournalHomeView().toolbar(.hidden, for: .tabBar).tag(JournalTab.home)
                JournalComposeView(chatAPI: chatAPI, memoryAPI: memoryAPI, previewScreen: previewScreen).toolbar(.hidden, for: .tabBar).tag(JournalTab.compose)
                JournalFamilyFilmView().toolbar(.hidden, for: .tabBar).tag(JournalTab.family)
                JournalProfileView().toolbar(.hidden, for: .tabBar).tag(JournalTab.profile)
                } }
            }
            .toolbar(.hidden, for: .tabBar).toolbar(.hidden, for: .navigationBar)
            .navigationDestination(for: JournalRoute.self) { route in
                switch route {
                case .memories:
                    if careEnabled { CareMemoriesView() } else { JournalMemoriesView() }
                case .familyFilms: JournalAllFamilyFilmsView()
                case .person(let id):
                    if let person = members.members.first(where: { $0.id == id }) { JournalPersonView(person: person) }
                case .memory(let id):
                    if let event = memories.memoryEvents.first(where: { $0.id == id }) { JournalStoryView(memory: event, api: memoryAPI) }
                case .memoir(let id):
                    if let person = members.members.first(where: { $0.id == id }),
                       let store = MemoirLocalStore.current(personID: id, preview: previewScreen) {
                        JournalMemoirView(person: person, api: memoirAPI, store: store)
                    }
                case .settings: JournalSettingsView()
                case .privacy: JournalPrivacyView()
                }
            }
        }
    }

    @ViewBuilder private var careTabs: some View {
        switch navigation.tab {
        case .home: CareHomeView()
        case .compose: JournalComposeView(chatAPI: chatAPI, memoryAPI: memoryAPI, previewScreen: previewScreen)
        case .family: CareMemoriesView(isRoot: true)
        case .profile: CareMoreView()
        }
    }
}
