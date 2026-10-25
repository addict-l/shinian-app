import SwiftUI
import PhotosUI

/// 主页面与全部目录共用数据和交互。仅一个纵向滚动容器，各家人的胶卷独立横向浏览。
struct FamilyFilmCollectionView: View {
    let showsAll: Bool
    @EnvironmentObject private var members: FamilyMemberStore
    @EnvironmentObject private var memories: MemoryListViewModel
    @EnvironmentObject private var navigation: JournalNavigation
    @StateObject private var portraits = FamilyFilmPortraitStore()
    @State private var search = ""
    @State private var viewportHeight: CGFloat = 0
    @State private var headerHeight: CGFloat = 0
    @State private var portraitPerson: UUID?
    @State private var selectedPhoto: PhotosPickerItem?
    @State private var pickingPortrait = false
    @State private var loadingPortrait = false

    private var timeline: FamilyFilmTimeline {
        FamilyFilmTimeline(members: members.members, memories: memories.memoryEvents)
    }
    private var visibleLanes: [FamilyFilmTimeline.Lane] {
        if !showsAll { return Array(timeline.lanes.prefix(3)) }
        let query = search.trimmingCharacters(in: .whitespacesAndNewlines)
        return timeline.lanes.filter {
            query.isEmpty || "\($0.person.name) \($0.person.relationship)".localizedStandardContains(query)
        }
    }
    private var memoryCount: Int { Set(timeline.lanes.flatMap { $0.moments.map(\.id) }).count }

    var body: some View {
        VStack(spacing: 0) {
        if showsAll { JournalBackBar() }
        ScrollView {
            LazyVStack(alignment: .leading, spacing: 14) {
                header.padding(.horizontal, JournalTheme.gutter)
                    .onGeometryChange(for: CGFloat.self) { $0.size.height } action: { headerHeight = $0 }
                if showsAll {
                    JournalSearch(prompt: "搜索家人的姓名或身份", text: $search).padding(.horizontal, JournalTheme.gutter)
                } else if !members.members.isEmpty {
                    JournalSectionHeader(title: "家人的胶卷") {
                        Text("一人一卷，慢慢翻阅。").font(JournalTheme.font(12)).foregroundStyle(JournalTheme.muted)
                    }.padding(.top, -16).padding(.bottom, -14).padding(.horizontal, JournalTheme.gutter)
                }
                if !members.hasLoaded && members.errorMessage == nil {
                    ProgressView("正在打开家庭胶片…").frame(maxWidth: .infinity).padding(.vertical, 80)
                } else if !members.hasLoaded {
                    JournalEmptyState(title: "暂时没能打开家庭胶片", message: "请检查连接后重试。")
                        .padding(.horizontal, 24)
                } else if members.members.isEmpty {
                    JournalWelcomeEmptyView(symbol: "film", title: "第一卷，留给谁？",
                        message: "先记下家人的名字，\n再慢慢收集你们的故事。",
                        actionTitle: "添加一位家人", actionID: "film.addFirstPerson",
                        minimumHeight: showsAll ? 0 : max(0, viewportHeight - headerHeight - 56)) { navigation.compose() }
                        .padding(.horizontal, 24)
                } else if visibleLanes.isEmpty {
                    JournalEmptyState(title: "没有找到这位家人", message: "试试姓名，或是你对家人的称呼。")
                        .frame(maxWidth: .infinity)
                } else {
                    ForEach(visibleLanes) { lane in
                        FamilyFilmRollView(lane: lane, portrait: portraits.images[lane.person.id],
                            isLoading: memories.isLoading,
                            onPerson: { navigation.path.append(.person(lane.person.id)) },
                            onMemory: { navigation.path.append(.memory($0)) },
                            onAdd: { navigation.compose(with: lane.person) },
                            onPortrait: { portraitPerson = lane.person.id; pickingPortrait = true })
                            .disabled(loadingPortrait)
                    }
                }
                if let error = members.errorMessage ?? memories.errorMessage {
                    JournalError(message: error) { Task { await reload() } }.padding(.horizontal, 24)
                }
            }.padding(.top, 6).padding(.bottom, 28)
        }
        .scrollIndicators(.hidden).scrollDismissesKeyboard(.interactively)
        }
        .journalPage()
        .onGeometryChange(for: CGFloat.self) { $0.size.height } action: { viewportHeight = $0 }
        .accessibilityIdentifier(showsAll ? "film.allPeople" : "film.overview")
        .refreshable { await reload() }
        .task { portraits.load(members.members.map(\.id)) }
        .onChange(of: members.members.map(\.id)) { _, ids in portraits.load(ids) }
        .photosPicker(isPresented: $pickingPortrait, selection: $selectedPhoto, matching: .images)
        .onChange(of: selectedPhoto) { _, item in
            guard let item, let id = portraitPerson else { return }
            loadingPortrait = true
            Task {
                defer { loadingPortrait = false; selectedPhoto = nil }
                do {
                    guard let data = try await item.loadTransferable(type: Data.self) else {
                        throw APIError.server("照片读取失败，请重新选择。")
                    }
                    try portraits.save(data, for: id)
                } catch { portraits.errorMessage = error.localizedDescription }
            }
        }
        .alert("人物照片", isPresented: Binding(get: { portraits.errorMessage != nil }, set: { if !$0 { portraits.errorMessage = nil } })) {
            Button("确定") { portraits.errorMessage = nil }
        } message: { Text(portraits.errorMessage ?? "") }
    }

    private var header: some View {
        VStack(alignment: .leading, spacing: 0) {
            JournalEyebrow(lead: "家庭胶片")
            JournalTitle(showsAll ? "家人的胶卷" : "我们的家庭").padding(.top, 8)
            JournalSubtitle(showsAll ? "一人一卷，慢慢翻阅。" : "把日子连起来，就成了我们的故事。").padding(.top, 2)
            if !members.members.isEmpty {
                ViewThatFits(in: .horizontal) {
                    HStack(spacing: 12) { familyStatistics; Spacer(minLength: 8); if !showsAll { directoryLink } }
                    VStack(alignment: .leading, spacing: 8) { familyStatistics; if !showsAll { directoryLink } }
                }.padding(.top, 14)
            }
        }
    }

    private var familyStatistics: some View {
        Text("\(members.members.count) 位家人 · \(memoryCount) 段回忆")
            .font(JournalTheme.font(13)).foregroundStyle(JournalTheme.ink2)
            .fixedSize(horizontal: false, vertical: true)
    }
    private var directoryLink: some View {
        Button { navigation.path.append(.familyFilms) } label: {
            HStack(spacing: 4) { Text("查看全部家人"); DesignIcon("chev", size: 14).accessibilityHidden(true) }
                .font(JournalTheme.font(13)).foregroundStyle(JournalTheme.ink2).frame(minHeight: 44)
        }.buttonStyle(.plain)
            .accessibilityIdentifier(timeline.lanes.count > 3 ? "film.moreFamily" : "film.allFamily")
    }

    private func reload() async {
        await members.load(with: memories)
        portraits.load(members.members.map(\.id))
    }
}
