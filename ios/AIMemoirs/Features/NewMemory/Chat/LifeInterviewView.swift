import SwiftUI

/// The person outline is independent of deletable story segments and local story input.
struct LifeInterviewView: View {
    let person: FamilyMember
    let api: any ChatAPI
    let onUpdated: (ChatSnapshot) -> Void
    let onClose: () -> Void
    let onEnter: (ChatSnapshot) -> Void
    @State private var snapshot: ChatSnapshot
    @State private var input = ""
    @State private var selected = "childhood"
    @State private var detailsPresented = false
    @State private var editing: LifeField?
    @State private var editText = ""
    @State private var busy = false
    @State private var error: String?
    @State private var pending: LifeCommand?
    @State private var historyPresented = false
    @State private var careFollowUp = false
    @State private var careLastQuestionID: String?
    @State private var autoFollow = JournalChatAutoFollow()
    @StateObject private var dictation = JournalDictation()
    @Environment(\.dynamicTypeSize) private var typeSize
    @Environment(\.verticalSizeClass) private var verticalSizeClass
    @Environment(\.journalCareMode) private var care
    @Environment(\.scenePhase) private var scenePhase
    @FocusState private var focused: Bool
    private var overview: LifeOverview? { snapshot.lifeOverview }
    private var collecting: Bool { overview?.status == "collecting" }
    private var showingOverview: Bool { overview?.status == "review" || overview?.status == "confirmed" }
    private let cacheScope = FamilySessionRegistry.scopeKey
    private var cacheKey: String { cacheScope + ".life-outline-input-\(person.id)" }
    private var commandKey: String { cacheScope + ".life-outline-request-\(person.id)" }
    init(person: FamilyMember, api: any ChatAPI, snapshot: ChatSnapshot, onUpdated: @escaping (ChatSnapshot) -> Void, onClose: @escaping () -> Void, onEnter: @escaping (ChatSnapshot) -> Void) {
        self.person = person; self.api = api; self.onUpdated = onUpdated; self.onClose = onClose; self.onEnter = onEnter
        _snapshot = State(initialValue: snapshot)
    }
    var body: some View {
        VStack(spacing: 0) {
            header
            if care {
                careContent
                feedback.padding(.horizontal, 20)
            } else if showingOverview, let overview {
                LifeOverviewContent(overview: overview, selected: $selected, busy: busy, hasPendingAction: pending != nil,
                    onDetails: { editing = nil; detailsPresented = true },
                    onConfirm: { Task { await perform("confirm") } },
                    onEnter: { Task { await choose() } },
                    feedback: { feedback })
            } else {
            JournalChatHistory(follow: autoFollow, identifier: "life.history") {
                    VStack(alignment: .leading, spacing: 18) {
                        Text(collecting ? "01 / 了解人生骨架" : "02 / 核对脉络，选择板块")
                            .font(JournalTheme.font(12, medium: true)).foregroundStyle(JournalTheme.userMessageInk)
                        if overview == nil || overview?.status == "not_started" {
                            Text("先了解您大致经历过哪些日子").font(JournalTheme.story(24))
                            Text("一次聊一个问题，记不清或暂时不想讲的可以跳过。已有聊天与草稿会保留。")
                            JournalButton(title: "开始了解人生骨架") { Task { await perform("begin") } }
                                .accessibilityIdentifier("life.begin")
                        } else if collecting {
                            ForEach(overview?.turns ?? []) { turn in
                                VStack(alignment: .leading, spacing: 8) {
                                    if turn.role == "assistant" { Text("AI 回忆助手").font(JournalTheme.font(12)).foregroundStyle(JournalTheme.ink2) }
                                    Text(turn.content).font(JournalTheme.story(17)).lineSpacing(7)
                                        .padding(turn.role == "user" ? 16 : 0)
                                        .background(turn.role == "user" ? JournalTheme.soft : .clear, in: RoundedRectangle(cornerRadius: 22))
                                        .frame(maxWidth: .infinity, alignment: turn.role == "user" ? .trailing : .leading)
                                }.padding(.leading, turn.role == "user" ? 35 : 0)
                                    .accessibilityIdentifier("life.message.\(turn.id)")
                            }
                        }
                        feedback
                        Color.clear.frame(height: 1).id("life.bottom")
                    }.padding(22)
            }
            if collecting { composer }
            }
        }
        .background {
            if care { JournalBackdrop().ignoresSafeArea() }
            else { (showingOverview ? LifeOverviewStyle.canvas : JournalTheme.paper).ignoresSafeArea() }
        }.foregroundStyle(JournalTheme.ink)
        .overlay { if care && busy { CareBusyOverlay(text: "正在记录与核对…") } }
        .interactiveDismissDisabled()
        .task {
            input = UserDefaults.standard.string(forKey: cacheKey) ?? ""
            if let data = UserDefaults.standard.data(forKey: commandKey) { pending = try? JSONDecoder().decode(LifeCommand.self, from: data) }
            await refresh()
            if let pending { await perform(pending.action, command: pending) }
        }
        .onChange(of: input) { _, value in UserDefaults.standard.set(value, forKey: cacheKey) }
        .onChange(of: dictation.transcript) { _, value in input = value }
        .onAppear { if care { careLastQuestionID = overview?.question_id } }
        .onChange(of: overview?.question) { previous, current in
            if care {
                careFollowUp = previous != nil && previous != current && careLastQuestionID == overview?.question_id
                careLastQuestionID = overview?.question_id
            }
        }
        .onDisappear { dictation.cancel() }
        .onChange(of: scenePhase) { _, phase in
            if phase == .background || (phase == .inactive && dictation.phase != .preparing) { dictation.cancel() }
        }
        .alert("语音输入", isPresented: Binding(get: { dictation.errorMessage != nil }, set: { if !$0 { dictation.errorMessage = nil } })) { Button("确定") { dictation.errorMessage = nil } } message: { Text(dictation.errorMessage ?? "") }
        .sheet(isPresented: $historyPresented) { CareDialogueHistory(entries: CareDialogueEntry.from(overview?.turns ?? []), person: person) { historyPresented = false } }
        .sheet(isPresented: $detailsPresented) {
            if care {
                careCorrectionSheet
            } else {
            NavigationStack {
                ScrollView {
                    VStack(alignment: .leading, spacing: 18) {
                        if let field = editing {
                            Text("请写下这一项应保留的说法。原始讲述会保留，更正后需要重新核对概览。")
                            TextEditor(text: $editText).frame(minHeight: 160).accessibilityIdentifier("life.correctionText")
                            Group {
                                if care {
                                    CareButton(title: "记录更正", loading: busy, disabled: editText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty) {
                                        Task { await perform("correct", text: editText, topic: field.topic_id); if error == nil { editing = nil } }
                                    }
                                } else {
                                    JournalButton(title: "记录更正") { Task { await perform("correct", text: editText, topic: field.topic_id); if error == nil { editing = nil } } }
                                        .disabled(busy || editText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                                }
                            }.accessibilityIdentifier("life.saveCorrection")
                        } else {
                            ForEach(overview?.fields ?? []) { field in
                                VStack(alignment: .leading, spacing: 6) {
                                    HStack {
                                        Text(field.title).font(care ? CareTheme.font(22, bold: true) : .headline)
                                        Spacer()
                                        Button("更正") { editing = field; editText = "" }.frame(minWidth: 44, minHeight: 44).accessibilityLabel("更正\(field.title)").accessibilityIdentifier("life.correct.\(field.id)")
                                    }
                                    Text(field.content).font(care ? CareTheme.font() : .body).fixedSize(horizontal: false, vertical: true)
                                }
                            }
                        }
                        if let error { Text(error).foregroundStyle(JournalTheme.danger) }
                    }.padding()
                }.navigationTitle(editing?.title ?? "核对人生脉络")
                    .toolbar { ToolbarItem(placement: .cancellationAction) { Button("返回") { if editing != nil { editing = nil } else { detailsPresented = false } } } }
            }.font(care ? CareTheme.font() : .body).interactiveDismissDisabled(busy)
            }
        }
    }
    private var careCorrectionSheet: some View {
        VStack(spacing: 0) {
            CareToolbar(title: editing?.title ?? "修改经历") {
                if editing != nil { editing = nil } else { detailsPresented = false }
            }.disabled(busy)
            ScrollView {
                VStack(alignment: .leading, spacing: 20) {
                    if editing != nil {
                        Text("请写下这一项应保留的说法。更正后需要重新核对。")
                            .font(CareTheme.font(19)).foregroundStyle(CareTheme.ink2).lineSpacing(6)
                        TextField("写下应该保留的说法", text: $editText, axis: .vertical)
                            .font(CareTheme.font(22)).lineSpacing(7).lineLimit(5...12).padding(18)
                            .background(CareTheme.surface, in: RoundedRectangle(cornerRadius: 22))
                            .overlay { RoundedRectangle(cornerRadius: 22).stroke(CareTheme.border, lineWidth: 1.5) }
                            .accessibilityIdentifier("life.correctionText")
                    } else {
                        Text("点“更正”，写下应该保留的说法。原来的讲述会留着。")
                            .font(CareTheme.font(19)).foregroundStyle(CareTheme.ink2).lineSpacing(6)
                        VStack(spacing: 20) {
                            ForEach(overview?.fields ?? []) { field in
                                VStack(alignment: .leading, spacing: 12) {
                                    HStack(alignment: .top, spacing: 12) {
                                        VStack(alignment: .leading, spacing: 8) {
                                            Text(field.title).font(CareTheme.font(20, bold: true)).foregroundStyle(CareTheme.ink)
                                            Text(field.content).font(CareTheme.font(18)).foregroundStyle(CareTheme.ink2).lineSpacing(6)
                                                .fixedSize(horizontal: false, vertical: true)
                                        }.frame(maxWidth: .infinity, alignment: .leading)
                                        CareMiniButton(title: "更正", symbol: "pencil") { editing = field; editText = "" }
                                            .accessibilityLabel("更正" + field.title).accessibilityIdentifier("life.correct.\(field.id)")
                                    }
                                    CareTheme.line.frame(height: 1)
                                }
                            }
                        }
                    }
                    if let error { CareError(message: error) }
                }.padding(20)
            }.scrollDismissesKeyboard(.interactively).disabled(busy)
                .safeAreaInset(edge: .bottom, spacing: 0) {
                    if let field = editing {
                        CareButton(title: "记录更正", symbol: "checkmark", loading: busy,
                                   disabled: editText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty) {
                            Task { await perform("correct", text: editText, topic: field.topic_id); if error == nil { editing = nil } }
                        }.accessibilityIdentifier("life.saveCorrection").careDock()
                    }
                }
        }.carePage().overlay { if busy { CareBusyOverlay(text: "正在记录更正…") } }
            .interactiveDismissDisabled(busy)
    }
    @ViewBuilder private var feedback: some View {
        if let error {
            if care {
                CareError(message: error) {
                    Task { if let pending { await perform(pending.action, command: pending) } else { await refresh() } }
                }.padding(.top, 8)
            } else {
            JournalError(message: error, retryTitle: pending == nil ? "重新读取" : "重试这次操作") {
                Task { if let pending { await perform(pending.action, command: pending) } else { await refresh() } }
            }.padding(.top, 14)
            }
        }
        if busy && !care { ProgressView("正在记录与核对…").frame(maxWidth: .infinity).padding(.top, 12) }
    }
    private func close() {
        dictation.cancel(); focused = false
        Task { if pending == nil && collecting { await perform("pause") }; onClose() }
    }
    @ViewBuilder private var header: some View {
        if care {
            CareToolbar(title: showingOverview ? (overview?.status == "confirmed" ? "选择话题" : "核对经历") : "慢慢讲述",
                        backTitle: collecting ? "暂停" : "返回",
                        step: showingOverview ? (overview?.status == "confirmed" ? "2 / 3" : "1 / 3") : overview.map { "\($0.question_number) / \($0.total_questions)" },
                        backIdentifier: "life.back", onBack: close)
        } else if showingOverview {
            ZStack {
                VStack(spacing: 3) {
                    Text("人生概览").font(JournalTheme.font(19, medium: true)).foregroundStyle(LifeOverviewStyle.ink)
                    Text("AI 回忆助手").font(JournalTheme.font(13)).foregroundStyle(LifeOverviewStyle.secondary)
                }
                HStack {
                    Button(action: close) { DesignIcon("back", size: 25).frame(width: 44, height: 44).contentShape(Rectangle()) }
                        .buttonStyle(.plain).foregroundStyle(LifeOverviewStyle.ink)
                        .accessibilityLabel("暂停并返回").accessibilityIdentifier("life.back").disabled(busy)
                    Spacer()
                    if JournalPortraitCache.image(for: person.id) != nil || !person.profileImages.isEmpty {
                        JournalAvatar(person: person, size: 43)
                    } else {
                        Text(JournalAvatar.initial(for: person)).font(JournalTheme.story(20)).foregroundStyle(.white)
                            .frame(width: 43, height: 43).background(LifeOverviewStyle.green, in: Circle()).accessibilityHidden(true)
                    }
                }
            }.frame(minHeight: 54).padding(.horizontal, 21).padding(.top, 3).padding(.bottom, 6)
        } else {
            HStack(spacing: 10) {
                JournalRoundButton(icon: "back", label: "暂停并返回", action: close)
                    .disabled(busy).accessibilityIdentifier("life.back")
                Spacer(minLength: 0)
                VStack(spacing: 4) {
                    Text("\(collecting ? "开始记录" : "人生概览") · \(person.name)").font(JournalTheme.font(16, medium: true))
                    Text("AI 回忆助手").font(JournalTheme.font(12)).foregroundStyle(JournalTheme.sageInk)
                }
                Spacer(minLength: 0)
                JournalAvatar(person: person, size: 38)
            }.padding(.horizontal, 16).padding(.vertical, 12)
                .overlay(alignment: .bottom) { JournalTheme.line.frame(height: 1) }
        }
    }
    private var careInlineInput: Bool { typeSize.isAccessibilitySize || verticalSizeClass == .compact }
    @ViewBuilder private var careContent: some View {
        if showingOverview, let overview {
            CareLifeOverviewView(overview: overview, busy: busy, hasPendingAction: pending != nil,
                onDetails: { editing = nil; detailsPresented = true },
                onConfirm: { Task { await perform("confirm") } },
                onSelect: { module in selected = module; Task { await choose() } },
                onHistory: { historyPresented = true })
        } else {
            ScrollView {
                VStack(alignment: .leading, spacing: 18) {
                    if collecting, let overview {
                        CareProgressBar(current: overview.question_number, total: overview.total_questions)
                            .accessibilityIdentifier("life.progress")
                            .accessibilityLabel("第 \(overview.question_number) 个问题，共 \(overview.total_questions) 个")
                        CarePersonLine(person: person, text: "人生经历")
                        CareQuestionCard(label: careFollowUp ? "接着问您" : "回忆助手问您",
                                         text: overview.question ?? overview.turns.last(where: { $0.role == "assistant" })?.content ?? "想到什么就说什么。",
                                         compact: dictation.isBusy || !input.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || pending != nil)
                        if !dictation.isBusy && input.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty && pending == nil {
                            if typeSize.isAccessibilitySize {
                                VStack(spacing: 10) { careHistoryButton; careSkipButton }
                            } else {
                                ViewThatFits(in: .horizontal) {
                                    HStack(spacing: 12) { careHistoryButton; careSkipButton }
                                    VStack(spacing: 10) { careHistoryButton; careSkipButton }
                                }
                            }
                        }
                    } else {
                        CareHeading(title: "先聊聊您的人生经历", subtitle: "一次只问一个问题，慢慢想、慢慢说。")
                        Text("记不清的可以跳过，累了可以下次继续。").font(CareTheme.font(20)).foregroundStyle(CareTheme.ink2)
                        CareButton(title: "开始聊聊", loading: busy, disabled: pending != nil) { Task { await perform("begin") } }
                            .accessibilityIdentifier("life.begin")
                    }
                    if collecting && careInlineInput { careComposer.padding(.top, 8).padding(.bottom, 8) }
                }.padding(20)
            }.scrollDismissesKeyboard(.interactively)
                .safeAreaInset(edge: .bottom, spacing: 0) {
                    if collecting && !careInlineInput { careComposer.careDock() }
                }
        }
    }
    private var careComposer: some View {
        VStack(spacing: 8) {
            CareNarrationInput(text: $input, dictation: dictation, disabled: busy, retrying: pending != nil,
                inputIdentifier: "life.input", sendIdentifier: "life.send", voiceIdentifier: "life.dictation", pendingText: pending?.text) {
                Task { if let pending { await perform(pending.action, command: pending) } else { await perform("answer", text: input) } }
            }
        }
    }
    private var careHistoryButton: some View {
        CarePill(title: "前面聊过的", symbol: "bubble.left", disabled: busy) { historyPresented = true }
            .accessibilityIdentifier("care.life.history")
    }
    private var careSkipButton: some View {
        CarePill(title: "跳过这题", symbol: "forward", disabled: busy || pending != nil || dictation.isBusy) {
            dictation.cancel(); Task { await perform("answer", text: "跳过") }
        }.accessibilityIdentifier("life.skip")
    }
    private var composer: some View {
        VStack(spacing: 10) {
            HStack {
                Text("人生骨架 \(overview?.question_number ?? 1) / \(overview?.total_questions ?? 6) · 一次聊一个问题").font(JournalTheme.font(12)).accessibilityIdentifier("life.progress")
                Spacer()
                Button("跳过") { Task { await perform("answer", text: "跳过") } }.frame(minWidth: 44, minHeight: 44).disabled(busy).accessibilityIdentifier("life.skip")
            }.foregroundStyle(JournalTheme.userMessageInk)
            HStack(spacing: 10) {
                TextField("慢慢讲，我在听…", text: $input, axis: .vertical).lineLimit(1...5).focused($focused).accessibilityIdentifier("life.input")
                Button { if dictation.isBusy { dictation.stop() } else { Task { await dictation.start(existingText: input) } } } label: { DesignIcon("mic", size: 24).frame(width: 44, height: 44) }.accessibilityLabel(dictation.isBusy ? "结束语音输入" : "语音输入").disabled(busy || pending != nil)
                Button { Task { if let pending { await perform(pending.action, command: pending) } else { await perform("answer", text: input) } } } label: { Image(systemName: pending == nil ? "arrow.up" : "arrow.clockwise").font(.title2).frame(width: 46, height: 46).background(JournalTheme.accentDeep, in: Circle()).foregroundStyle(.white) }.accessibilityLabel(pending == nil ? "发送回答" : "重试回答").accessibilityIdentifier("life.send")
                    .disabled(busy || dictation.isBusy || (pending == nil && input.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty))
            }.padding(8).padding(.leading, 12).background(JournalTheme.surface, in: RoundedRectangle(cornerRadius: 28))
                .overlay { RoundedRectangle(cornerRadius: 28).stroke(JournalTheme.line) }
            if dictation.isBusy { Text(dictation.statusText).font(.caption) }
        }.padding(.horizontal, 20).padding(.bottom, 12).background(JournalTheme.paper)
    }
    private func update(_ value: ChatSnapshot) { snapshot = value; onUpdated(value) }
    private func refresh() async {
        do {
            let value = try await api.state(sessionID: snapshot.sessionID); update(value)
            if let command = value.lifeOverview?.pending_action { pending = command }
        } catch { self.error = error.localizedDescription }
    }
    private func perform(_ action: String, text: String = "", topic: String? = nil, command: LifeCommand? = nil) async {
        guard !busy else { return }
        let command = command ?? LifeCommand(action: action, expected_version: overview?.version ?? 0, client_request_id: UUID(), text: text, topic_id: topic)
        if let pending, pending.client_request_id != command.client_request_id, command.text != "跳过" { error = "上次回答已保留，请先重试这次操作。"; return }
        if !care && (command.action == "answer" || command.action == "begin") { autoFollow.resume() }
        pending = command
        UserDefaults.standard.set(try? JSONEncoder().encode(command), forKey: commandKey)
        busy = true; error = nil
        defer { busy = false }
        do {
            let value = try await api.lifeAction(sessionID: snapshot.sessionID, command: command)
            update(value); pending = nil; UserDefaults.standard.removeObject(forKey: commandKey)
            if command.action == "answer" { input = "" }
        } catch {
            self.error = error.localizedDescription
            if isVersionConflict(error) { pending = nil; UserDefaults.standard.removeObject(forKey: commandKey) }
            await refresh()
        }
    }
    private func choose() async {
        guard !busy else { return }; busy = true; error = nil
        defer { busy = false }
        do { let value = try await api.selectInterview(sessionID: snapshot.sessionID, module: selected, version: snapshot.version); update(value); onEnter(value) }
        catch {
            self.error = error.localizedDescription
            await refresh()
            if snapshot.information.guided_interview?.module == selected && snapshot.information.guided_interview?.module_selected == true { onEnter(snapshot) }
        }
    }
}
