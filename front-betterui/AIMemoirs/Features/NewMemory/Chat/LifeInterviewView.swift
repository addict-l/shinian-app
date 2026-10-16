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
    @StateObject private var dictation = JournalDictation()
    @Environment(\.dynamicTypeSize) private var typeSize
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
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
            if showingOverview, let overview {
                LifeOverviewContent(overview: overview, selected: $selected, busy: busy, hasPendingAction: pending != nil,
                    onDetails: { editing = nil; detailsPresented = true },
                    onConfirm: { Task { await perform("confirm") } },
                    onEnter: { Task { await choose() } },
                    feedback: { feedback })
            } else {
            ScrollViewReader { reader in
                ScrollView {
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
                            }
                        }
                        feedback
                        Color.clear.frame(height: 1).id("life.bottom")
                    }.padding(22)
                }.scrollDismissesKeyboard(.interactively)
                    .onChange(of: overview?.turns.count) { _, _ in
                        if reduceMotion { reader.scrollTo("life.bottom", anchor: .bottom) }
                        else { withAnimation { reader.scrollTo("life.bottom", anchor: .bottom) } }
                    }
            }
            if collecting { composer }
            }
        }
        .background((showingOverview ? LifeOverviewStyle.canvas : JournalTheme.paper).ignoresSafeArea()).foregroundStyle(JournalTheme.ink)
        .interactiveDismissDisabled()
        .task {
            input = UserDefaults.standard.string(forKey: cacheKey) ?? ""
            if let data = UserDefaults.standard.data(forKey: commandKey) { pending = try? JSONDecoder().decode(LifeCommand.self, from: data) }
            await refresh()
            if let pending { await perform(pending.action, command: pending) }
        }
        .onChange(of: input) { _, value in UserDefaults.standard.set(value, forKey: cacheKey) }
        .onChange(of: dictation.transcript) { _, value in input = value }
        .onDisappear { dictation.cancel() }
        .alert("语音输入", isPresented: Binding(get: { dictation.errorMessage != nil }, set: { if !$0 { dictation.errorMessage = nil } })) { Button("确定") { dictation.errorMessage = nil } } message: { Text(dictation.errorMessage ?? "") }
        .sheet(isPresented: $detailsPresented) {
            NavigationStack {
                ScrollView {
                    VStack(alignment: .leading, spacing: 18) {
                        if let field = editing {
                            Text("请写下这一项应保留的说法。原始讲述会保留，更正后需要重新核对概览。")
                            TextEditor(text: $editText).frame(minHeight: 160).accessibilityIdentifier("life.correctionText")
                            JournalButton(title: "记录更正") { Task { await perform("correct", text: editText, topic: field.topic_id); if error == nil { editing = nil } } }.disabled(busy || editText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty).accessibilityIdentifier("life.saveCorrection")
                        } else {
                            ForEach(overview?.fields ?? []) { field in
                                VStack(alignment: .leading, spacing: 6) {
                                    HStack {
                                        Text(field.title).font(.headline)
                                        Spacer()
                                        Button("更正") { editing = field; editText = "" }.frame(minWidth: 44, minHeight: 44).accessibilityLabel("更正\(field.title)").accessibilityIdentifier("life.correct.\(field.id)")
                                    }
                                    Text(field.content).font(.body).fixedSize(horizontal: false, vertical: true)
                                }
                            }
                        }
                        if let error { Text(error).foregroundStyle(JournalTheme.danger) }
                    }.padding()
                }.navigationTitle(editing?.title ?? "核对人生脉络")
                    .toolbar { ToolbarItem(placement: .cancellationAction) { Button("返回") { if editing != nil { editing = nil } else { detailsPresented = false } } } }
            }.interactiveDismissDisabled(busy)
        }
    }
    @ViewBuilder private var feedback: some View {
        if let error {
            JournalError(message: error, retryTitle: pending == nil ? "重新读取" : "重试这次操作") {
                Task { if let pending { await perform(pending.action, command: pending) } else { await refresh() } }
            }.padding(.top, 14)
        }
        if busy { ProgressView("正在记录与核对…").frame(maxWidth: .infinity).padding(.top, 12) }
    }
    private func close() {
        dictation.cancel(); focused = false
        Task { if pending == nil && collecting { await perform("pause") }; onClose() }
    }
    @ViewBuilder private var header: some View {
        if showingOverview {
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
    private var composer: some View {
        VStack(spacing: 10) {
            HStack {
                Text("人生骨架 \(overview?.question_number ?? 1) / 7 · 一次聊一个问题").font(JournalTheme.font(12)).accessibilityIdentifier("life.progress")
                Spacer()
                Button("跳过") { Task { await perform("answer", text: "跳过") } }.frame(minWidth: 44, minHeight: 44).disabled(busy || pending != nil).accessibilityIdentifier("life.skip")
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
        if let pending, pending.client_request_id != command.client_request_id { error = "上次回答已保留，请先重试这次操作。"; return }
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
