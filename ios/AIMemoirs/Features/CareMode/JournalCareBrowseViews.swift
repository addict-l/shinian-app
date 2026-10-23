import SwiftUI
import AVFoundation

struct CareTabBar: View {
    @Binding var selection: JournalTab
    private let tabs: [JournalTab] = [.home, .family, .profile]
    private func title(_ tab: JournalTab) -> String { tab == .home ? "首页" : tab == .family ? "回忆" : "更多" }
    var body: some View {
        HStack(spacing: 8) {
            ForEach(tabs) { tab in
                Button { selection = tab } label: {
                    VStack(spacing: 6) {
                        Group {
                            if tab == .profile { Image(systemName: "square.grid.2x2").font(.system(size: 29, weight: .regular)) }
                            else { DesignIcon(tab == .home ? "home" : "book", size: 30) }
                        }.accessibilityHidden(true)
                        Text(title(tab)).font(CareTheme.font(20, bold: selection == tab))
                            .fixedSize(horizontal: false, vertical: true)
                    }.frame(maxWidth: .infinity, minHeight: 76).padding(.vertical, 5)
                        .foregroundStyle(selection == tab ? CareTheme.accent : CareTheme.ink2)
                        .background(selection == tab ? CareTheme.soft : .clear, in: RoundedRectangle(cornerRadius: 22))
                        .contentShape(Rectangle())
                }.buttonStyle(CarePressStyle()).accessibilityLabel(title(tab))
                    .accessibilityIdentifier("care.tab.\(tab.rawValue)").accessibilityAddTraits(selection == tab ? .isSelected : [])
            }
        }.padding(.horizontal, 14).padding(.top, 10).padding(.bottom, 4)
            .background {
                UnevenRoundedRectangle(topLeadingRadius: 30, topTrailingRadius: 30)
                    .fill(CareTheme.surface).ignoresSafeArea(edges: .bottom)
                    .shadow(color: JournalTheme.shadow.opacity(0.10), radius: 18, x: 0, y: -6)
            }
    }
}

struct CareHomeView: View {
    @EnvironmentObject private var members: FamilyMemberStore
    @EnvironmentObject private var memories: MemoryListViewModel
    @EnvironmentObject private var navigation: JournalNavigation
    @Environment(\.scenePhase) private var scenePhase
    @State private var continuation: CareContinuation?
    private var events: [MemoryEvent] {
        FamilyMemoryCollection(members: members.members, memories: memories.memoryEvents).events.sorted { $0.createdAt > $1.createdAt }
    }
    private var today: String {
        let formatter = DateFormatter(); formatter.locale = Locale(identifier: "zh_CN"); formatter.dateFormat = "M月d日 EEEE"
        return formatter.string(from: Date())
    }
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 18) {
                ViewThatFits(in: .horizontal) {
                    HStack { brand; Spacer(minLength: 8); date }.fixedSize(horizontal: true, vertical: false)
                    VStack(alignment: .leading, spacing: 6) { brand; date }
                }
                Text("慢慢讲，\n都是好时光。").font(JournalTheme.story(34)).lineSpacing(4)
                    .fixedSize(horizontal: false, vertical: true).accessibilityAddTraits(.isHeader)
                VStack(alignment: .leading, spacing: 14) {
                    illustration
                    Text("今天想起了谁？说给我听听。").font(CareTheme.font(19)).foregroundStyle(CareTheme.ink2)
                        .fixedSize(horizontal: false, vertical: true)
                    CareButton(title: "开始讲述", symbol: "mic") {
                        navigation.compose(step: members.members.isEmpty && members.hasLoaded ? .add : .select)
                    }.accessibilityIdentifier("home.newMemory")
                }.padding(18).journalCard(radius: 26)
                if let continuation, let person = members.members.first(where: { $0.id == continuation.personID }) {
                    Button { navigation.compose(with: person) } label: {
                        HStack(spacing: 14) {
                            JournalAvatar(person: person, size: 56)
                            VStack(alignment: .leading, spacing: 4) {
                                Text("接着上次讲").font(CareTheme.font(22, bold: true))
                                Text((person.relationship.isEmpty ? person.name : person.relationship) + " · " + continuation.hint)
                                    .font(CareTheme.font(18)).fixedSize(horizontal: false, vertical: true)
                            }.frame(maxWidth: .infinity, alignment: .leading)
                            Image(systemName: "arrow.right").font(.system(size: 23)).frame(width: 48, height: 48)
                                .background(CareTheme.surface, in: Circle()).accessibilityHidden(true)
                        }.padding(16).frame(maxWidth: .infinity, minHeight: 92, alignment: .leading)
                            .foregroundStyle(CareTheme.sageInk).background(CareTheme.sageSoft, in: RoundedRectangle(cornerRadius: 24))
                    }.buttonStyle(CarePressStyle()).accessibilityIdentifier("care.home.continue")
                }
                HStack(spacing: 12) {
                    Text("最近的回忆").font(CareTheme.font(24, bold: true)).accessibilityAddTraits(.isHeader)
                    Spacer(minLength: 0)
                    CareMiniButton(title: "全部", symbol: "chevron.right") { navigation.tab = .family }
                }.padding(.top, 4)
                if let event = events.first {
                    CareMemoryCard(memory: event, showsPhoto: false) { navigation.path.append(.memory(event.id)) }
                } else if !members.hasLoaded || !memories.hasLoaded {
                    ProgressView("正在打开回忆…").font(CareTheme.font(20)).frame(maxWidth: .infinity).padding(24)
                } else if members.errorMessage == nil && memories.errorMessage == nil {
                    Text("还没有回忆。点“开始讲述”，留下第一段故事。").font(CareTheme.font()).foregroundStyle(CareTheme.ink2)
                        .fixedSize(horizontal: false, vertical: true).padding(20).frame(maxWidth: .infinity, alignment: .leading).journalCard(radius: 26)
                }
                if let error = members.errorMessage ?? memories.errorMessage {
                    CareError(message: error) { Task { await members.load(); await memories.load() } }
                }
            }.padding(.horizontal, 20).padding(.top, 12).padding(.bottom, 24)
        }.scrollIndicators(.hidden).refreshable { await members.load(); await memories.load(); loadContinuation() }
            .carePage().onAppear(perform: loadContinuation)
            .onChange(of: members.members.map(\.id)) { _, _ in loadContinuation() }
            .onChange(of: scenePhase) { _, phase in if phase == .active { loadContinuation() } }
    }
    private var brand: some View {
        Text("拾年 · 关怀模式").font(CareTheme.font(18, bold: true)).tracking(1).foregroundStyle(CareTheme.accent)
    }
    private var date: some View { Text(today).font(CareTheme.font(18)).foregroundStyle(CareTheme.ink2) }
    private var illustration: some View {
        GeometryReader { proxy in
            Image("JournalWelcome").resizable().scaledToFill()
                .frame(width: proxy.size.width, height: proxy.size.width * 4 / 3)
                .offset(y: -(proxy.size.width * 4 / 3 - 128) * 0.62)
                .frame(width: proxy.size.width, height: 128, alignment: .top).clipped()
                .mask { LinearGradient(stops: [.init(color: .black, location: 0), .init(color: .black, location: 0.65), .init(color: .clear, location: 1)], startPoint: .top, endPoint: .bottom) }
        }.frame(height: 128).clipShape(UnevenRoundedRectangle(topLeadingRadius: 18, topTrailingRadius: 18)).accessibilityHidden(true)
    }
    private func loadContinuation() {
        continuation = nil
        let validIDs = Set(members.members.map(\.id))
        if let drafts = try? ChatDraftStore.current(previewScreen: JournalDemo.screen)?.list(),
           let draft = drafts.first(where: { validIDs.contains($0.personID) && (!$0.input.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || $0.pendingText != nil || !$0.photos.isEmpty) }) {
            continuation = CareContinuation(personID: draft.personID, hint: draft.pendingText != nil ? "有一段待重试" : "有没发出的话")
            return
        }
        // 人生骨架的输入沿用现有家庭隔离键；不读取其他家庭，也不创建会话。
        guard !JournalDemo.isPreview, FamilySessionRegistry.current != nil else { return }
        let defaults = UserDefaults.standard
        for person in members.members {
            let key = FamilySessionRegistry.scopeKey + ".life-outline-"
            let pending = defaults.data(forKey: key + "request-" + person.id.uuidString) != nil
            let input = defaults.string(forKey: key + "input-" + person.id.uuidString) ?? ""
            if pending || !input.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                continuation = CareContinuation(personID: person.id, hint: pending ? "有一段待重试" : "有没发出的话")
                return
            }
        }
    }
}

private struct CareContinuation { let personID: UUID; let hint: String }

struct CareMemoryCard: View {
    let memory: MemoryEvent
    var showsPhoto = true
    let onOpen: () -> Void
    @EnvironmentObject private var members: FamilyMemberStore
    private var person: FamilyMember? { carePerson(for: memory, members: members.members) }
    private var hasPhoto: Bool { memory.imageData != nil || memory.imageName != nil }
    var body: some View {
        Button(action: onOpen) {
            Group {
                if !showsPhoto {
                    HStack(spacing: 14) {
                        if hasPhoto { JournalPhoto(memory: memory, height: 96, radius: 18).frame(width: 96) }
                        else { CareIconTile(symbol: "book", tone: .butter, size: 76).frame(width: 96, height: 96) }
                        VStack(alignment: .leading, spacing: 8) {
                            Text(memorySubtitle(memory, members: members.members)).font(CareTheme.font(18)).foregroundStyle(CareTheme.ink2)
                                .fixedSize(horizontal: false, vertical: true)
                            Text(memory.title).font(JournalTheme.story(23)).fixedSize(horizontal: false, vertical: true)
                        }.frame(maxWidth: .infinity, alignment: .leading)
                    }.padding(14)
                } else {
                    VStack(alignment: .leading, spacing: 0) {
                        if hasPhoto { JournalPhoto(memory: memory, height: 158, radius: 0) }
                        VStack(alignment: .leading, spacing: 12) {
                            HStack(spacing: 9) {
                                if let person { JournalAvatar(person: person, size: 32) }
                                Text(memorySubtitle(memory, members: members.members)).font(CareTheme.font(18)).foregroundStyle(CareTheme.ink2)
                                    .fixedSize(horizontal: false, vertical: true)
                            }
                            Text(memory.title).font(JournalTheme.story(25)).fixedSize(horizontal: false, vertical: true)
                            ViewThatFits(in: .horizontal) {
                                HStack(spacing: 12) { details; Spacer(minLength: 0); openLabel }
                                VStack(alignment: .leading, spacing: 10) { details; openLabel }
                            }
                        }.padding(18)
                    }
                }
            }.frame(maxWidth: .infinity, alignment: .leading).background(CareTheme.surface)
                .clipShape(RoundedRectangle(cornerRadius: 26)).journalCard(radius: 26)
                .contentShape(RoundedRectangle(cornerRadius: 26))
        }.buttonStyle(CarePressStyle()).foregroundStyle(CareTheme.ink).accessibilityIdentifier("care.memory.\(memory.id)")
    }
    @ViewBuilder private var details: some View {
        let text = [careMeaningful(memory.information.place.value) ?? careMeaningful(memory.location), careMeaningful(memory.information.feeling.value)]
            .compactMap { $0 }.joined(separator: " · ")
        if !text.isEmpty { Text(text).font(CareTheme.font(18)).foregroundStyle(CareTheme.ink2).fixedSize(horizontal: false, vertical: true) }
    }
    private var openLabel: some View {
        Label("打开看看", systemImage: "arrow.right").font(CareTheme.font(20, bold: true)).foregroundStyle(CareTheme.accent)
            .fixedSize(horizontal: false, vertical: true)
    }
}

struct CareMemoriesView: View {
    var isRoot = false
    @EnvironmentObject private var members: FamilyMemberStore
    @EnvironmentObject private var memories: MemoryListViewModel
    @EnvironmentObject private var navigation: JournalNavigation
    @Environment(\.dismiss) private var dismiss
    @Environment(\.scenePhase) private var scenePhase
    @StateObject private var dictation = JournalDictation()
    @State private var search = ""
    @State private var selectedPerson: UUID?
    @FocusState private var searchFocused: Bool
    private var all: [MemoryEvent] { FamilyMemoryCollection(members: members.members, memories: memories.memoryEvents).events }
    private var events: [MemoryEvent] {
        all.filter { event in
            let matchesPerson = selectedPerson.map { id in event.primaryPersonID.map { $0 == id } ?? event.personIDs.contains(id) } ?? true
            return matchesPerson && (search.isEmpty || "\(event.title) \(event.personName) \(event.content)".localizedStandardContains(search))
        }.sorted { $0.createdAt > $1.createdAt }
    }
    private var groups: [(year: Int?, events: [MemoryEvent])] {
        let values = Dictionary(grouping: events, by: memoryYear)
        return values.keys.sorted { ($0 ?? Int.min) > ($1 ?? Int.min) }.map { ($0, values[$0] ?? []) }
    }
    var body: some View {
        VStack(spacing: 0) {
            if !isRoot { CareToolbar(title: "珍藏的回忆", onBack: { dismiss() }) }
            ScrollView {
                LazyVStack(alignment: .leading, spacing: 16) {
                    if isRoot {
                        ViewThatFits(in: .horizontal) {
                            HStack(spacing: 12) { title; count }.fixedSize(horizontal: true, vertical: false)
                            VStack(alignment: .leading, spacing: 8) { title; count }
                        }.padding(.top, 8)
                    }
                    searchField
                    ScrollView(.horizontal) {
                        HStack(spacing: 10) {
                            personFilter(nil)
                            ForEach(members.members) { person in personFilter(person) }
                        }.padding(.vertical, 2)
                    }.scrollIndicators(.hidden)
                    if dictation.isBusy { Text(dictation.statusText).font(CareTheme.font(18)).foregroundStyle(CareTheme.accent) }
                    if memories.isLoading { ProgressView("正在打开回忆…").font(CareTheme.font(20)).frame(maxWidth: .infinity).padding(12) }
                    if let error = members.errorMessage ?? memories.errorMessage {
                        CareError(message: error) { Task { await members.load(); await memories.load() } }
                    }
                    ForEach(Array(groups.enumerated()), id: \.offset) { _, group in
                        HStack(spacing: 12) {
                            Text(group.year.map { "\($0) 年" } ?? "时间待补充").font(CareTheme.font(20, bold: true)).foregroundStyle(CareTheme.ink2)
                            CareTheme.line.frame(height: 1)
                        }.padding(.top, 8).accessibilityAddTraits(.isHeader)
                        ForEach(group.events) { event in CareMemoryCard(memory: event) { navigation.path.append(.memory(event.id)) } }
                    }
                    if members.hasLoaded && memories.hasLoaded && events.isEmpty && members.errorMessage == nil && memories.errorMessage == nil {
                        Text(all.isEmpty ? "还没有回忆，先讲一段故事吧。" : "没有找到，换一句话或另一位家人试试。")
                            .font(CareTheme.font()).foregroundStyle(CareTheme.ink2).fixedSize(horizontal: false, vertical: true).padding(.vertical, 20)
                        if all.isEmpty { CareButton(title: "开始讲述", symbol: "mic") { navigation.compose(step: members.members.isEmpty ? .add : .select) } }
                    }
                }.padding(20)
            }.scrollIndicators(.hidden).refreshable { await members.load(); await memories.load() }
                .scrollDismissesKeyboard(.interactively)
        }.carePage().onDisappear { dictation.cancel() }
            .onChange(of: scenePhase) { _, phase in if phase == .background { dictation.cancel() } }
            .onChange(of: dictation.transcript) { _, text in
                if !text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty { search = text }
            }
            .alert("语音输入", isPresented: Binding(get: { dictation.errorMessage != nil }, set: { if !$0 { dictation.errorMessage = nil } })) {
                Button("确定") { dictation.errorMessage = nil }
            } message: { Text(dictation.errorMessage ?? "") }
    }
    private var title: some View { Text("珍藏的回忆").font(CareTheme.font(32, bold: true)).accessibilityAddTraits(.isHeader) }
    private var count: some View {
        Text("共 \(all.count) 段").font(CareTheme.font(18, bold: true)).foregroundStyle(CareTheme.accent)
            .padding(.horizontal, 14).padding(.vertical, 8).background(CareTheme.soft, in: Capsule())
    }
    private var searchField: some View {
        HStack(spacing: 12) {
            DesignIcon("search", size: 26).foregroundStyle(CareTheme.accent).accessibilityHidden(true)
            TextField("找一段回忆", text: $search).font(CareTheme.font(22)).focused($searchFocused)
                .accessibilityLabel("搜索回忆").accessibilityIdentifier("care.memories.search")
                .submitLabel(.search).onSubmit { searchFocused = false }
            Button {
                searchFocused = false
                if dictation.phase == .preparing { dictation.cancel() }
                else if dictation.isRecording { dictation.stop() }
                else { Task { await dictation.start(existingText: "") } }
            } label: {
                Image(systemName: dictation.isBusy ? "stop.circle" : "mic").font(.system(size: 25)).frame(width: 48, height: 48)
            }.buttonStyle(CarePressStyle()).foregroundStyle(CareTheme.accent).disabled(dictation.phase == .finishing)
                .accessibilityLabel(dictation.isBusy ? "停止语音搜索" : "语音搜索").accessibilityIdentifier("care.memories.dictation")
        }.padding(.leading, 18).padding(.trailing, 8).padding(.vertical, 8).frame(minHeight: 64)
            .background(CareTheme.surface, in: RoundedRectangle(cornerRadius: 22))
            .overlay { RoundedRectangle(cornerRadius: 22).stroke(CareTheme.border, lineWidth: 1.5) }
    }
    private func personFilter(_ person: FamilyMember?) -> some View {
        let selected = selectedPerson == person?.id
        return Button { selectedPerson = person?.id } label: {
            HStack(spacing: 8) {
                if let person { JournalAvatar(person: person, size: 42) }
                Text(person.map { $0.relationship.isEmpty ? $0.name : $0.relationship } ?? "全部").font(CareTheme.font(21, bold: selected))
            }.padding(.leading, person == nil ? 22 : 6).padding(.trailing, 20).padding(.vertical, 6).frame(minHeight: 56)
                .foregroundStyle(selected ? .white : CareTheme.ink)
                .background(selected ? CareTheme.accent : CareTheme.surface, in: Capsule())
                .overlay { Capsule().stroke(selected ? CareTheme.accent : CareTheme.border, lineWidth: 1.5) }
        }.buttonStyle(CarePressStyle()).accessibilityAddTraits(selected ? .isSelected : [])
            .accessibilityIdentifier("care.memories.filter." + (person?.id.uuidString ?? "all"))
    }
}

struct CareMoreView: View {
    @EnvironmentObject private var navigation: JournalNavigation
    @EnvironmentObject private var members: FamilyMemberStore
    @EnvironmentObject private var memories: MemoryListViewModel
    @Environment(\.dynamicTypeSize) private var typeSize
    @AppStorage(JournalCareMode.storageKey) private var enabled = false
    @State private var confirmSwitch = false
    private var memoryCount: Int { FamilyMemoryCollection(members: members.members, memories: memories.memoryEvents).events.count }
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 18) {
                Text("更多").font(CareTheme.font(32, bold: true)).accessibilityAddTraits(.isHeader).padding(.bottom, 2)
                ViewThatFits(in: .horizontal) {
                    HStack(spacing: 14) { portraits; familySummary }
                    VStack(alignment: .leading, spacing: 14) { portraits; familySummary }
                }.padding(20).frame(maxWidth: .infinity, alignment: .leading).journalCard(radius: 26)
                VStack(spacing: 0) {
                    menu(title: "家人管理", detail: "添加家人、换头像", symbol: "person.2", tone: .rose, route: .familyFilms)
                    CareTheme.line.frame(height: 1)
                    menu(title: "设置与账号", detail: "名字、退出家庭账号", symbol: "gearshape", tone: .butter, route: .settings)
                    CareTheme.line.frame(height: 1)
                    menu(title: "隐私与数据", detail: "回忆只属于您的家", symbol: "checkmark.shield", tone: .sage, route: .privacy)
                }.journalCard(radius: 26)
                VStack(alignment: .leading, spacing: 16) {
                    Text("显示方式").font(CareTheme.font(24, bold: true)).accessibilityAddTraits(.isHeader)
                    let layout = typeSize.isAccessibilitySize ? AnyLayout(VStackLayout(spacing: 8)) : AnyLayout(HStackLayout(spacing: 4))
                    layout {
                        Button { confirmSwitch = true } label: { modeLabel("普通模式", selected: false) }
                            .buttonStyle(CarePressStyle()).accessibilityIdentifier("care.switchStandard")
                        modeLabel("关怀模式", selected: true).accessibilityAddTraits(.isSelected)
                    }.padding(5).background(CareTheme.paper2, in: RoundedRectangle(cornerRadius: 22))
                }.padding(20).journalCard(radius: 26)
                Text("拾年 · 留住时光").font(CareTheme.font(18)).foregroundStyle(CareTheme.ink2)
                    .frame(maxWidth: .infinity).padding(.vertical, 8)
            }.padding(20)
        }.scrollIndicators(.hidden).carePage()
            .alert("切换到普通模式？", isPresented: $confirmSwitch) {
                Button("继续使用关怀模式", role: .cancel) {}
                Button("切换普通模式") { enabled = false }
            } message: { Text("家人和回忆都会保留。之后可以在设置中重新开启关怀模式。") }
    }
    private var portraits: some View {
        HStack(spacing: -16) {
            ForEach(Array(members.members.prefix(3).enumerated()), id: \.element.id) { index, person in
                JournalAvatar(person: person, size: 54).zIndex(Double(index))
            }
            if members.members.isEmpty { CareIconTile(symbol: "person.2", tone: .rose, size: 54) }
        }.accessibilityHidden(true)
    }
    private var familySummary: some View {
        VStack(alignment: .leading, spacing: 7) {
            Text("我们家的回忆").font(CareTheme.font(23, bold: true))
            Text("\(members.members.count) 位家人 · \(memoryCount) 段回忆").font(CareTheme.font(18)).foregroundStyle(CareTheme.ink2)
        }.fixedSize(horizontal: false, vertical: true)
    }
    private func menu(title: String, detail: String, symbol: String, tone: CareTone, route: JournalRoute) -> some View {
        Button { navigation.path.append(route) } label: {
            HStack(spacing: 14) {
                CareIconTile(symbol: symbol, tone: tone, size: 56)
                VStack(alignment: .leading, spacing: 5) {
                    Text(title).font(CareTheme.font(23, bold: true))
                    Text(detail).font(CareTheme.font(18)).foregroundStyle(CareTheme.ink2)
                }.fixedSize(horizontal: false, vertical: true).frame(maxWidth: .infinity, alignment: .leading)
                Image(systemName: "chevron.right").font(.system(size: 20)).foregroundStyle(CareTheme.ink2).accessibilityHidden(true)
            }.padding(18).frame(maxWidth: .infinity, minHeight: 100, alignment: .leading).contentShape(Rectangle())
        }.buttonStyle(CarePressStyle()).foregroundStyle(CareTheme.ink).accessibilityElement(children: .ignore).accessibilityLabel(title)
    }
    private func modeLabel(_ title: String, selected: Bool) -> some View {
        HStack(spacing: 7) {
            Text("Aa").font(CareTheme.font(20, bold: selected)).accessibilityHidden(true)
            Text(title).font(CareTheme.font(21, bold: selected)).fixedSize(horizontal: false, vertical: true)
        }.frame(maxWidth: .infinity, minHeight: 58).padding(.horizontal, 6).padding(.vertical, 6)
            .foregroundStyle(selected ? CareTheme.accent : CareTheme.ink2)
            .background(selected ? CareTheme.surface : .clear, in: RoundedRectangle(cornerRadius: 18))
    }
}

struct CarePersonSelectionView: View {
    @EnvironmentObject private var members: FamilyMemberStore
    @EnvironmentObject private var memories: MemoryListViewModel
    @EnvironmentObject private var navigation: JournalNavigation
    @Environment(\.dynamicTypeSize) private var typeSize
    let onSelect: (FamilyMember) -> Void
    let onAdd: () -> Void
    var body: some View {
        VStack(spacing: 0) {
            CareToolbar(title: "选择家人", backTitle: "首页", onBack: { navigation.tab = .home })
            ScrollView {
                VStack(alignment: .leading, spacing: 14) {
                    CareHeading(title: "这次讲谁的故事？", subtitle: "点一下家人，就可以开始。").padding(.bottom, 8)
                    ForEach(members.members) { person in
                        Button { onSelect(person) } label: {
                            HStack(spacing: 14) {
                                JournalAvatar(person: person, size: typeSize.isAccessibilitySize ? 56 : 74)
                                VStack(alignment: .leading, spacing: 9) {
                                    ViewThatFits(in: .horizontal) {
                                        HStack(alignment: .firstTextBaseline, spacing: 8) { name(person) }.fixedSize(horizontal: true, vertical: false)
                                        VStack(alignment: .leading, spacing: 4) { name(person) }
                                    }
                                    Text("已讲 \(count(person)) 段").font(CareTheme.font(17, bold: true)).foregroundStyle(CareTheme.accent)
                                        .padding(.horizontal, 12).padding(.vertical, 5).background(CareTheme.soft, in: Capsule())
                                }.frame(maxWidth: .infinity, alignment: .leading)
                                Image(systemName: "arrow.right").font(.system(size: 23)).foregroundStyle(CareTheme.accent)
                                    .frame(width: 48, height: 52).background(CareTheme.faint, in: Circle()).accessibilityHidden(true)
                            }.padding(18).frame(maxWidth: .infinity, minHeight: 116, alignment: .leading).journalCard(radius: 26)
                        }.buttonStyle(CarePressStyle()).foregroundStyle(CareTheme.ink).accessibilityIdentifier("care.person.\(person.id)")
                    }
                    if members.isLoading { ProgressView("正在打开家人…").font(CareTheme.font(20)).frame(maxWidth: .infinity).padding(12) }
                    if let error = members.errorMessage { CareError(message: error) { Task { await members.load() } } }
                    Button(action: onAdd) {
                        Label("添加一位家人", systemImage: "plus").font(CareTheme.font(24, bold: true))
                            .fixedSize(horizontal: false, vertical: true).frame(maxWidth: .infinity, minHeight: 76).padding(.horizontal, 12)
                            .foregroundStyle(CareTheme.accent).contentShape(RoundedRectangle(cornerRadius: 26))
                    }.buttonStyle(CarePressStyle()).overlay { RoundedRectangle(cornerRadius: 26).stroke(CareTheme.border, style: StrokeStyle(lineWidth: 2, dash: [7, 5])) }
                        .accessibilityIdentifier("members.addAnother")
                }.padding(20)
            }.scrollIndicators(.hidden)
        }.carePage()
    }
    @ViewBuilder private func name(_ person: FamilyMember) -> some View {
        Text(person.relationship.isEmpty ? person.name : person.relationship).font(CareTheme.font(28, bold: true))
            .fixedSize(horizontal: false, vertical: true)
        if !person.relationship.isEmpty { Text(person.name).font(CareTheme.font(20)).foregroundStyle(CareTheme.ink2).fixedSize(horizontal: false, vertical: true) }
    }
    private func count(_ person: FamilyMember) -> Int {
        FamilyMemoryCollection(members: members.members, memories: memories.memoryEvents).events
            .filter { $0.primaryPersonID.map { $0 == person.id } ?? $0.personIDs.contains(person.id) }.count
    }
}

struct CareStoryReading: View {
    let memory: MemoryEvent
    let identity: String
    var api: (any MemoryAPI)? = nil
    var onBack: (() -> Void)? = nil
    @EnvironmentObject private var members: FamilyMemberStore
    @Environment(\.dynamicTypeSize) private var typeSize
    @Environment(\.verticalSizeClass) private var verticalSizeClass
    @Environment(\.scenePhase) private var scenePhase
    @AppStorage("journal.care.readingScale") private var readingScale = 1.0
    @StateObject private var speech = CareStorySpeech()
    private var person: FamilyMember? { carePerson(for: memory, members: members.members) }
    private var hasPhoto: Bool { memory.imageData != nil || memory.imageName != nil }
    private var hasRemoteCover: Bool { api != nil && !memory.mediaAssets.isEmpty }
    private var scrollsToolbar: Bool { typeSize.isAccessibilitySize && verticalSizeClass == .compact }
    private var metadata: [(label: String, value: String)] {
        let time = careMeaningful(memory.dateLabel)
        let place = careMeaningful(memory.information.place.value) ?? careMeaningful(memory.location)
        let feeling = careMeaningful(memory.information.feeling.value)
        guard time != nil || place != nil || feeling != nil else { return [] }
        return [("时间", time ?? "待补充"), ("地点", place ?? "待补充"), ("感受", feeling ?? "待补充")]
    }
    var body: some View {
        VStack(spacing: 0) {
            if !scrollsToolbar { readingToolbar }
            ScrollView {
                VStack(spacing: 0) {
                if scrollsToolbar { readingToolbar }
                VStack(alignment: .leading, spacing: 20) {
                    if hasPhoto { JournalPhoto(memory: memory, height: 200, radius: 24) }
                    else if let api, let photo = memory.mediaAssets.first {
                        MemoryPhotoView(attachment: photo, api: api).frame(maxWidth: .infinity).frame(height: 200)
                            .background(CareTheme.paper2, in: RoundedRectangle(cornerRadius: 24))
                            .clipShape(RoundedRectangle(cornerRadius: 24)).accessibilityLabel("回忆照片：\(memory.title)")
                    }
                    HStack(spacing: 10) {
                        if let person { JournalAvatar(person: person, size: 34) }
                        Text(identity).font(CareTheme.font(18)).foregroundStyle(CareTheme.ink2).fixedSize(horizontal: false, vertical: true)
                    }
                    Text(memory.title).font(JournalTheme.story(31)).fixedSize(horizontal: false, vertical: true).accessibilityAddTraits(.isHeader)
                    if !metadata.isEmpty { information }
                    Text(memory.content).font(JournalTheme.story(22 * min(1.6, max(1, readingScale)))).lineSpacing(10).textSelection(.enabled)
                        .fixedSize(horizontal: false, vertical: true).frame(maxWidth: .infinity, alignment: .leading)
                        .accessibilityIdentifier("care.story.body")
                    if let api {
                        ForEach(memory.mediaAssets.dropFirst(hasPhoto || hasRemoteCover ? 1 : 0)) { photo in
                            MemoryPhotoView(attachment: photo, api: api).frame(maxWidth: .infinity, minHeight: 160)
                                .clipShape(RoundedRectangle(cornerRadius: 24))
                        }
                    }
                }.padding(.horizontal, 20).padding(.top, 12).padding(.bottom, 24).frame(maxWidth: 720, alignment: .leading).frame(maxWidth: .infinity)
                }
            }.scrollIndicators(.hidden).accessibilityIdentifier("care.reading.scroll")
        }.carePage().onDisappear { speech.stop() }
            .onChange(of: scenePhase) { _, phase in if phase != .active { speech.stop() } }
            .onChange(of: memory.id) { _, _ in speech.stop() }
            .alert("朗读", isPresented: Binding(get: { speech.errorMessage != nil }, set: { if !$0 { speech.errorMessage = nil } })) {
                Button("确定") { speech.errorMessage = nil }
            } message: { Text(speech.errorMessage ?? "") }
    }
    @ViewBuilder private var readingToolbar: some View {
        Group {
        if typeSize.isAccessibilitySize {
            VStack(alignment: .leading, spacing: 8) { backButton; sizeControls; listenButton }
        } else { ViewThatFits(in: .horizontal) {
            HStack(spacing: 8) { backButton; Spacer(minLength: 0); sizeControls; listenButton }
            VStack(alignment: .leading, spacing: 8) {
                if onBack != nil { backButton }
                HStack(spacing: 10) { sizeControls; listenButton }
            }
        } }
        }.padding(.horizontal, 20).padding(.vertical, 8)
    }
    @ViewBuilder private var backButton: some View {
        if let onBack {
            Button(action: onBack) {
                Label("返回", systemImage: "chevron.left").font(CareTheme.font(20)).fixedSize(horizontal: true, vertical: false)
                    .padding(.horizontal, 14).frame(minHeight: 52).background(CareTheme.surface, in: Capsule())
                    .overlay { Capsule().stroke(CareTheme.border, lineWidth: 1.5) }
            }.buttonStyle(CarePressStyle()).foregroundStyle(CareTheme.accent).accessibilityIdentifier("care.back")
        }
    }
    private var sizeControls: some View {
        HStack(spacing: 0) {
            Button { readingScale = max(1, readingScale - 0.15) } label: { Text("A−").font(CareTheme.font(20, bold: true)).frame(minWidth: 48, minHeight: 52) }
                .disabled(readingScale <= 1).accessibilityLabel("缩小正文").accessibilityIdentifier("care.reading.smaller")
            CareTheme.border.frame(width: 1, height: 30).accessibilityHidden(true)
            Button { readingScale = min(1.6, readingScale + 0.15) } label: { Text("A+").font(CareTheme.font(23, bold: true)).frame(minWidth: 48, minHeight: 52) }
                .disabled(readingScale >= 1.6).accessibilityLabel("放大正文").accessibilityIdentifier("care.reading.larger")
        }.buttonStyle(CarePressStyle()).foregroundStyle(CareTheme.ink).background(CareTheme.surface, in: Capsule())
            .overlay { Capsule().stroke(CareTheme.border, lineWidth: 1.5) }
    }
    private var listenButton: some View {
        Button { speech.toggle(title: memory.title, content: memory.content) } label: {
            Label(speech.isSpeaking ? "停一下" : "听一听", systemImage: speech.isSpeaking ? "stop.fill" : "speaker.wave.2")
                .font(CareTheme.font(19, bold: true)).fixedSize(horizontal: true, vertical: false).padding(.horizontal, 12).frame(minHeight: 52)
                .background(CareTheme.faint, in: Capsule()).overlay { Capsule().stroke(CareTheme.border, lineWidth: 1) }
        }.buttonStyle(CarePressStyle()).foregroundStyle(CareTheme.accent).accessibilityIdentifier("care.reading.speak")
    }
    private var information: some View {
        let layout = typeSize.isAccessibilitySize ? AnyLayout(VStackLayout(alignment: .leading, spacing: 0)) : AnyLayout(HStackLayout(alignment: .top, spacing: 0))
        return layout {
            ForEach(Array(metadata.enumerated()), id: \.offset) { index, item in
                VStack(spacing: 8) {
                    Text(item.label).font(CareTheme.font(17)).foregroundStyle(CareTheme.ink2)
                    Text(item.value).font(CareTheme.font(21, bold: true)).foregroundStyle(item.label == "感受" ? CareTheme.accent : CareTheme.ink)
                        .fixedSize(horizontal: false, vertical: true)
                }.frame(maxWidth: .infinity).padding(.horizontal, 10).padding(.vertical, 16)
                    .overlay(alignment: typeSize.isAccessibilitySize ? .bottom : .trailing) {
                        if index < metadata.count - 1 {
                            if typeSize.isAccessibilitySize { CareTheme.line.frame(height: 1) }
                            else { CareTheme.line.frame(width: 1) }
                        }
                    }
            }
        }.background(CareTheme.surface, in: RoundedRectangle(cornerRadius: 22))
            .overlay { RoundedRectangle(cornerRadius: 22).stroke(CareTheme.border, lineWidth: 1) }
    }
}

@MainActor private final class CareStorySpeech: NSObject, ObservableObject, AVSpeechSynthesizerDelegate {
    @Published private(set) var isSpeaking = false
    @Published var errorMessage: String?
    private let synthesizer = AVSpeechSynthesizer()
    private var currentUtterance: AVSpeechUtterance?
    override init() { super.init(); synthesizer.delegate = self }
    func toggle(title: String, content: String) {
        if isSpeaking { stop(); return }
        do {
            let session = AVAudioSession.sharedInstance()
            try session.setCategory(.playback, mode: .spokenAudio, options: .duckOthers)
            try session.setActive(true)
            let utterance = AVSpeechUtterance(string: title + "。\n" + content)
            utterance.voice = AVSpeechSynthesisVoice(language: "zh-CN")
            utterance.rate = AVSpeechUtteranceDefaultSpeechRate * 0.82
            currentUtterance = utterance; isSpeaking = true; synthesizer.speak(utterance)
        } catch { errorMessage = "暂时无法朗读，请稍后再试。" }
    }
    func stop() {
        currentUtterance = nil; synthesizer.stopSpeaking(at: .immediate); isSpeaking = false
        try? AVAudioSession.sharedInstance().setActive(false, options: .notifyOthersOnDeactivation)
    }
    nonisolated func speechSynthesizer(_ synthesizer: AVSpeechSynthesizer, didFinish utterance: AVSpeechUtterance) {
        Task { @MainActor [weak self] in
            guard let self, self.currentUtterance === utterance else { return }
            self.currentUtterance = nil; self.isSpeaking = false
            try? AVAudioSession.sharedInstance().setActive(false, options: .notifyOthersOnDeactivation)
        }
    }
    nonisolated func speechSynthesizer(_ synthesizer: AVSpeechSynthesizer, didCancel utterance: AVSpeechUtterance) {
        Task { @MainActor [weak self] in
            guard let self, self.currentUtterance === utterance else { return }
            self.currentUtterance = nil; self.isSpeaking = false
        }
    }
}

private func carePerson(for memory: MemoryEvent, members: [FamilyMember]) -> FamilyMember? {
    let id = memory.primaryPersonID ?? memory.personIDs.first
    return members.first { $0.id == id }
}

private func careMeaningful(_ value: String?) -> String? {
    guard let value = value?.trimmingCharacters(in: .whitespacesAndNewlines),
          !value.isEmpty, !["待补充", "时间待补充", "未提及"].contains(value) else { return nil }
    return value
}
