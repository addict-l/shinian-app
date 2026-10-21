import SwiftUI

struct CareTabBar: View {
    @Binding var selection: JournalTab
    private let tabs: [JournalTab] = [.home, .family, .profile]
    private func title(_ tab: JournalTab) -> String { tab == .home ? "首页" : tab == .family ? "回忆" : "更多" }
    private func symbol(_ tab: JournalTab) -> String { tab == .home ? "house" : tab == .family ? "book" : "square.grid.2x2" }
    var body: some View {
        HStack(spacing: 8) {
            ForEach(tabs) { tab in
                Button { selection = tab } label: {
                    VStack(spacing: 4) {
                        Image(systemName: symbol(tab)).font(.title2).accessibilityHidden(true)
                        Text(title(tab)).font(CareTheme.font(20, bold: selection == tab))
                    }.frame(maxWidth: .infinity, minHeight: 72).padding(.vertical, 4)
                        .foregroundStyle(selection == tab ? CareTheme.accent : JournalTheme.ink2)
                        .background(selection == tab ? JournalTheme.soft : .clear, in: RoundedRectangle(cornerRadius: 14))
                        .contentShape(Rectangle())
                }.buttonStyle(.plain).accessibilityLabel(title(tab))
                    .accessibilityIdentifier("care.tab.\(tab.rawValue)").accessibilityAddTraits(selection == tab ? .isSelected : [])
            }
        }.padding(.horizontal, 12).padding(.top, 8).padding(.bottom, 4)
            .background(JournalTheme.surface).overlay(alignment: .top) { CareTheme.border.frame(height: 1) }
    }
}

struct CareHomeView: View {
    @EnvironmentObject private var members: FamilyMemberStore
    @EnvironmentObject private var memories: MemoryListViewModel
    @EnvironmentObject private var navigation: JournalNavigation
    private var events: [MemoryEvent] {
        FamilyMemoryCollection(members: members.members, memories: memories.memoryEvents).events.sorted { $0.createdAt > $1.createdAt }
    }
    var body: some View {
        ScrollView {
            VStack(spacing: 12) {
                Text("拾年 · 关怀模式").font(CareTheme.font(18)).foregroundStyle(CareTheme.accent).padding(.top, 4)
                illustration
                CareHeading(title: "慢慢讲，都是好时光。", subtitle: "把您的故事，好好留下来。")
                CareButton(title: "开始讲述", symbol: "mic.fill") {
                    navigation.compose(step: members.members.isEmpty && members.hasLoaded ? .add : .select)
                }.accessibilityIdentifier("home.newMemory")
                if let event = events.first {
                    HStack {
                        Text("最近的回忆").font(CareTheme.font(24, bold: true))
                        Spacer()
                        Button("全部") { navigation.tab = .family }.font(CareTheme.font(20)).frame(minWidth: 64, minHeight: 48)
                    }
                    CareMemoryCard(memory: event, showsPhoto: false) { navigation.path.append(.memory(event.id)) }
                } else if !members.hasLoaded || !memories.hasLoaded {
                    ProgressView("正在打开回忆…").font(CareTheme.font(20)).padding(24)
                } else if members.errorMessage == nil && memories.errorMessage == nil {
                    Text("还没有回忆。点“开始讲述”，留下第一段故事。").font(CareTheme.font()).foregroundStyle(JournalTheme.ink2)
                        .multilineTextAlignment(.center).padding(.vertical, 20)
                }
                if let error = members.errorMessage ?? memories.errorMessage {
                    CareError(message: error) { Task { await members.load(); await memories.load() } }
                }
            }.padding(.horizontal, 20).padding(.bottom, 16)
        }.scrollIndicators(.hidden).refreshable { await members.load(); await memories.load() }
            .background(CareTheme.paper.ignoresSafeArea())
    }

    private var illustration: some View {
        GeometryReader { proxy in
            Image("JournalWelcome").resizable().scaledToFill()
                .frame(width: proxy.size.width, height: proxy.size.width * 4 / 3)
                .offset(y: -(proxy.size.width * 4 / 3 - 160) * 0.62)
                .frame(width: proxy.size.width, height: 160, alignment: .top).clipped()
                .mask {
                    EllipticalGradient(colors: [.black, .black, .clear], center: .center,
                        startRadiusFraction: 0, endRadiusFraction: 0.65)
                }
        }.frame(height: 160).padding(.horizontal, -8).accessibilityHidden(true)
    }
}

struct CareMemoryCard: View {
    let memory: MemoryEvent
    var showsPhoto = true
    let onOpen: () -> Void
    var body: some View {
        Button(action: onOpen) {
            VStack(alignment: .leading, spacing: 10) {
                if showsPhoto && (memory.imageData != nil || memory.imageName != nil) { JournalPhoto(memory: memory, height: 140, radius: 12) }
                Text(memory.personName + " · " + memory.dateLabel).font(CareTheme.font(18)).foregroundStyle(JournalTheme.ink2)
                    .fixedSize(horizontal: false, vertical: true)
                Text(memory.title).font(CareTheme.font(24, bold: true)).fixedSize(horizontal: false, vertical: true)
                Text(memory.content).font(CareTheme.font(20)).foregroundStyle(JournalTheme.ink2).lineLimit(2)
                HStack { Text("打开看看"); Spacer(); Image(systemName: "arrow.right").accessibilityHidden(true) }
                    .font(CareTheme.font(20, bold: true)).foregroundStyle(CareTheme.accent).padding(.top, 4)
            }.padding(18).frame(maxWidth: .infinity, alignment: .leading)
                .background(JournalTheme.surface, in: RoundedRectangle(cornerRadius: 18))
                .overlay { RoundedRectangle(cornerRadius: 18).stroke(CareTheme.border, lineWidth: 1) }
                .contentShape(RoundedRectangle(cornerRadius: 18))
        }.buttonStyle(.plain).foregroundStyle(JournalTheme.ink).accessibilityIdentifier("care.memory.\(memory.id)")
    }
}

struct CareMemoriesView: View {
    var isRoot = false
    @EnvironmentObject private var members: FamilyMemberStore
    @EnvironmentObject private var memories: MemoryListViewModel
    @EnvironmentObject private var navigation: JournalNavigation
    @Environment(\.dismiss) private var dismiss
    @State private var search = ""
    @State private var searching = false
    private var events: [MemoryEvent] {
        FamilyMemoryCollection(members: members.members, memories: memories.memoryEvents).events
            .filter { search.isEmpty || "\($0.title) \($0.personName) \($0.content)".localizedStandardContains(search) }
            .sorted { $0.createdAt > $1.createdAt }
    }
    var body: some View {
        VStack(spacing: 0) {
            if !isRoot { CareToolbar(title: "珍藏的回忆", onBack: { dismiss() }) }
            ScrollView {
                LazyVStack(spacing: 16) {
                    if isRoot { CareHeading(title: "珍藏的回忆", subtitle: "点开一段，慢慢看看。").padding(.top, 12) }
                    if searching {
                        TextField("搜索回忆、人物或一句话", text: $search).font(CareTheme.font()).padding(14)
                            .background(JournalTheme.surface, in: RoundedRectangle(cornerRadius: 14))
                            .accessibilityLabel("搜索回忆").accessibilityIdentifier("care.memories.search")
                    } else if !events.isEmpty {
                        Button { searching = true } label: { Label("找一段回忆", systemImage: "magnifyingglass").font(CareTheme.font(20)).frame(minHeight: 48) }
                            .buttonStyle(.plain).foregroundStyle(CareTheme.accent)
                    }
                    if memories.isLoading { ProgressView("正在打开回忆…").font(CareTheme.font(20)) }
                    if let error = members.errorMessage ?? memories.errorMessage {
                        CareError(message: error) { Task { await members.load(); await memories.load() } }
                    }
                    ForEach(events) { event in CareMemoryCard(memory: event) { navigation.path.append(.memory(event.id)) } }
                    if members.hasLoaded && memories.hasLoaded && events.isEmpty && members.errorMessage == nil && memories.errorMessage == nil {
                        Text(search.isEmpty ? "还没有回忆，先讲一段故事吧。" : "没有找到，换一句话试试。").font(CareTheme.font()).multilineTextAlignment(.center).padding(24)
                        if search.isEmpty { CareButton(title: "开始讲述", symbol: "mic.fill") { navigation.compose(step: members.members.isEmpty ? .add : .select) } }
                    }
                }.padding(20)
            }.scrollIndicators(.hidden).refreshable { await members.load(); await memories.load() }
        }.background(CareTheme.paper.ignoresSafeArea())
    }
}

struct CareMoreView: View {
    @EnvironmentObject private var navigation: JournalNavigation
    @Environment(\.dynamicTypeSize) private var typeSize
    @AppStorage(JournalCareMode.storageKey) private var enabled = false
    @State private var confirmSwitch = false
    var body: some View {
        GeometryReader { proxy in
            let rowHeight = typeSize.isAccessibilitySize ? 64 : max(64, min(120, (proxy.size.height - 248) / 4))
            ScrollView {
                VStack(spacing: 16) {
                    CareHeading(title: "更多", subtitle: "常用设置，都在这里。").padding(.top, 12).padding(.bottom, 8)
                    CareButton(title: "家人管理", symbol: "person.2", secondary: true, minimumHeight: rowHeight) { navigation.path.append(.familyFilms) }
                    CareButton(title: "设置与账号", symbol: "gearshape", secondary: true, minimumHeight: rowHeight) { navigation.path.append(.settings) }
                    CareButton(title: "隐私与数据", symbol: "hand.raised", secondary: true, minimumHeight: rowHeight) { navigation.path.append(.privacy) }
                    CareButton(title: "切换普通模式", symbol: "textformat.size", secondary: true, minimumHeight: rowHeight) { confirmSwitch = true }
                        .accessibilityIdentifier("care.switchStandard")
                    Text("当前使用：关怀模式").font(CareTheme.font(18)).foregroundStyle(JournalTheme.ink2).padding(.top, 8)
                }.padding(20)
            }.scrollIndicators(.hidden)
        }.background(CareTheme.paper.ignoresSafeArea())
            .alert("切换到普通模式？", isPresented: $confirmSwitch) {
                Button("继续使用关怀模式", role: .cancel) {}
                Button("切换普通模式") { enabled = false }
            } message: { Text("家人和回忆都会保留。之后可以在设置中重新开启关怀模式。") }
    }
}

struct CarePersonSelectionView: View {
    @EnvironmentObject private var members: FamilyMemberStore
    @EnvironmentObject private var navigation: JournalNavigation
    let onSelect: (FamilyMember) -> Void
    let onAdd: () -> Void
    var body: some View {
        VStack(spacing: 0) {
            CareToolbar(title: "选择家人", backTitle: "首页", onBack: { navigation.tab = .home })
            ScrollView {
                VStack(spacing: 14) {
                    CareHeading(title: "这次记录谁的故事？", subtitle: "点一下名字，就可以开始。")
                    ForEach(members.members) { person in
                        Button { onSelect(person) } label: {
                            HStack(spacing: 14) {
                                JournalAvatar(person: person, size: 52)
                                VStack(alignment: .leading, spacing: 4) {
                                    Text(person.name).font(CareTheme.font(24, bold: true))
                                    if !person.relationship.isEmpty { Text(person.relationship).font(CareTheme.font(18)).foregroundStyle(JournalTheme.ink2) }
                                }.frame(maxWidth: .infinity, alignment: .leading)
                                Image(systemName: "chevron.right").accessibilityHidden(true)
                            }.padding(16).frame(maxWidth: .infinity, minHeight: 84)
                                .background(JournalTheme.surface, in: RoundedRectangle(cornerRadius: 16))
                                .overlay { RoundedRectangle(cornerRadius: 16).stroke(CareTheme.border, lineWidth: 1) }
                        }.buttonStyle(.plain).accessibilityIdentifier("care.person.\(person.id)")
                    }
                    if members.isLoading { ProgressView("正在打开家人…").font(CareTheme.font(20)) }
                    if let error = members.errorMessage { CareError(message: error) { Task { await members.load() } } }
                    CareButton(title: "添加一位家人", symbol: "plus", secondary: true, action: onAdd)
                        .accessibilityIdentifier("members.addAnother")
                }.padding(20)
            }.scrollIndicators(.hidden)
        }.background(CareTheme.paper.ignoresSafeArea())
    }
}

struct CareStoryReading: View {
    let memory: MemoryEvent
    let identity: String
    var api: (any MemoryAPI)? = nil
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 18) {
                Text(identity).font(CareTheme.font(18)).foregroundStyle(JournalTheme.ink2)
                Text(memory.title).font(CareTheme.font(28, bold: true)).accessibilityAddTraits(.isHeader)
                Text(memory.dateLabel).font(CareTheme.font(18)).foregroundStyle(JournalTheme.ink2)
                if memory.imageData != nil || memory.imageName != nil { JournalPhoto(memory: memory, height: 200, radius: 16) }
                Text(memory.content).font(CareTheme.font()).lineSpacing(6).textSelection(.enabled)
                    .fixedSize(horizontal: false, vertical: true).frame(maxWidth: .infinity, alignment: .leading)
                    .accessibilityIdentifier("care.story.body")
                if let api {
                    ForEach(memory.mediaAssets.dropFirst(memory.imageData != nil || memory.imageName != nil ? 1 : 0)) { photo in
                        MemoryPhotoView(attachment: photo, api: api).frame(maxWidth: .infinity, minHeight: 160)
                            .clipShape(RoundedRectangle(cornerRadius: 16))
                    }
                }
            }.padding(20).frame(maxWidth: .infinity, alignment: .leading)
        }.scrollIndicators(.hidden)
    }
}
