import SwiftUI

struct CareAddPersonView: View {
    @Binding var draft: FamilyMemberDraft
    let loading: Bool
    let error: String?
    let onAdd: () -> Void
    let onClose: () -> Void
    private enum Field { case relationship, name }
    @FocusState private var field: Field?
    @Environment(\.dynamicTypeSize) private var typeSize
    @Environment(\.scenePhase) private var scenePhase
    @StateObject private var dictation = JournalDictation()
    @State private var showingBirthday = false
    @State private var birthday = APIDate.parseDay("1950-01-01")!
    private let relationships = ["爷爷", "奶奶", "外公", "外婆", "爸爸", "妈妈"]
    var body: some View {
        VStack(spacing: 0) {
            CareToolbar(title: "添加家人", onBack: onClose).disabled(loading)
            ScrollView {
                VStack(alignment: .leading, spacing: 20) {
                    CareHeading(title: "先记下家人的名字", subtitle: "这些资料，之后也可以修改。").padding(.bottom, 4)
                    VStack(alignment: .leading, spacing: 12) {
                        fieldLabel("怎么称呼这位家人", symbol: "person.2")
                        LazyVGrid(columns: typeSize.isAccessibilitySize ? [GridItem(.flexible())] : [GridItem(.adaptive(minimum: 72), spacing: 10)], spacing: 10) {
                            ForEach(relationships, id: \.self) { relationship in
                                Button { draft.relationship = relationship; field = nil } label: {
                                    Text(relationship).font(CareTheme.font(24, bold: draft.relationship == relationship))
                                        .fixedSize(horizontal: false, vertical: true).frame(maxWidth: .infinity, minHeight: 56).padding(.horizontal, 8).padding(.vertical, 4)
                                        .foregroundStyle(draft.relationship == relationship ? .white : CareTheme.ink)
                                        .background(draft.relationship == relationship ? CareTheme.accent : CareTheme.surface, in: RoundedRectangle(cornerRadius: 18))
                                        .overlay { RoundedRectangle(cornerRadius: 18).stroke(draft.relationship == relationship ? CareTheme.accent : CareTheme.border, lineWidth: 1.5) }
                                }.buttonStyle(CarePressStyle()).accessibilityAddTraits(draft.relationship == relationship ? .isSelected : [])
                                    .accessibilityIdentifier("member.relationship.option." + relationship)
                            }
                        }
                        TextField("也可以自己写，例如姑姑、舅舅", text: $draft.relationship, axis: .vertical)
                            .font(CareTheme.font(22)).lineLimit(1...2).padding(.horizontal, 18).padding(.vertical, 16).frame(minHeight: 64)
                            .background(CareTheme.surface, in: RoundedRectangle(cornerRadius: 22))
                            .overlay { RoundedRectangle(cornerRadius: 22).stroke(field == .relationship ? CareTheme.accent : CareTheme.border, lineWidth: field == .relationship ? 2 : 1.5) }
                            .focused($field, equals: .relationship).submitLabel(.next).onSubmit { field = .name }
                            .accessibilityLabel("怎么称呼这位家人").accessibilityIdentifier("member.relationship")
                    }
                    VStack(alignment: .leading, spacing: 12) {
                        fieldLabel("真实姓名", symbol: "person")
                        HStack(spacing: 8) {
                            TextField("填写家人的姓名", text: $draft.realName).textContentType(.name).font(CareTheme.font(24))
                                .focused($field, equals: .name).submitLabel(.done).onSubmit { field = nil }
                                .disabled(dictation.isBusy).accessibilityLabel("真实姓名").accessibilityIdentifier("member.realName")
                            Button {
                                field = nil
                                if dictation.phase == .preparing { dictation.cancel() }
                                else if dictation.isRecording { dictation.stop() }
                                else { Task { await dictation.start(existingText: "") } }
                            } label: {
                                Image(systemName: dictation.isBusy ? "stop.circle" : "mic").font(.system(size: 25)).frame(width: 48, height: 48)
                            }.buttonStyle(CarePressStyle()).foregroundStyle(CareTheme.accent).disabled(dictation.phase == .finishing)
                                .accessibilityLabel(dictation.isBusy ? "停止姓名语音输入" : "语音填写姓名").accessibilityIdentifier("member.nameDictation")
                        }.padding(.leading, 18).padding(.trailing, 8).padding(.vertical, 10).frame(minHeight: 68)
                            .background(CareTheme.surface, in: RoundedRectangle(cornerRadius: 22))
                            .overlay { RoundedRectangle(cornerRadius: 22).stroke(field == .name || dictation.isBusy ? CareTheme.accent : CareTheme.border, lineWidth: field == .name || dictation.isBusy ? 2 : 1.5) }
                        if dictation.isBusy { Text(dictation.statusText).font(CareTheme.font(18)).foregroundStyle(CareTheme.accent).fixedSize(horizontal: false, vertical: true) }
                    }
                    VStack(alignment: .leading, spacing: 12) {
                        fieldLabel("生日", symbol: "calendar")
                        Button {
                            field = nil; birthday = draft.birthDate ?? APIDate.parseDay("1950-01-01")!; showingBirthday = true
                        } label: {
                            HStack(spacing: 12) {
                                Text(draft.birthDate.map(JournalSpacedDate.string) ?? "选择家人的生日").font(CareTheme.font(22))
                                    .foregroundStyle(draft.birthDate == nil ? CareTheme.ink2 : CareTheme.ink).fixedSize(horizontal: false, vertical: true)
                                Spacer(minLength: 0)
                                Image(systemName: "calendar").font(.system(size: 25)).foregroundStyle(CareTheme.accent).accessibilityHidden(true)
                            }.padding(18).frame(maxWidth: .infinity, minHeight: 68, alignment: .leading)
                                .background(CareTheme.surface, in: RoundedRectangle(cornerRadius: 22))
                                .overlay { RoundedRectangle(cornerRadius: 22).stroke(CareTheme.border, lineWidth: 1.5) }
                        }.buttonStyle(CarePressStyle()).accessibilityIdentifier("member.birthday")
                    }
                    if let error { CareError(message: error) }
                }.padding(20)
            }.scrollIndicators(.hidden).scrollDismissesKeyboard(.interactively).disabled(loading)
                .toolbar {
                    ToolbarItemGroup(placement: .keyboard) {
                        Spacer()
                        Button("收起键盘") { field = nil }.accessibilityIdentifier("member.dismissKeyboard")
                    }
                }
        }.safeAreaInset(edge: .bottom, spacing: 0) {
            CareButton(title: "添加并开始讲述", symbol: "checkmark", loading: loading, disabled: !draft.isValid() || dictation.isBusy) {
                field = nil; dictation.cancel(); onAdd()
            }.accessibilityIdentifier("member.add").careDock()
        }.carePage().overlay { if loading { CareBusyOverlay(text: "正在添加…") } }
            .onChange(of: dictation.transcript) { _, text in
                if !text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty { draft.realName = text }
            }
            .onChange(of: scenePhase) { _, phase in if phase == .background { dictation.cancel() } }
            .onDisappear { dictation.cancel() }
            .sheet(isPresented: $showingBirthday) {
                NavigationStack {
                    DatePicker("家人的生日", selection: $birthday, in: ...Date(), displayedComponents: .date)
                        .datePickerStyle(.wheel).padding()
                        .navigationTitle("家人的生日").navigationBarTitleDisplayMode(.inline)
                        .toolbar {
                            ToolbarItem(placement: .cancellationAction) { Button("取消") { showingBirthday = false } }
                            ToolbarItem(placement: .confirmationAction) {
                                Button("确定") { draft.birthDate = birthday; showingBirthday = false }.accessibilityIdentifier("member.confirmBirthday")
                            }
                        }
                }.presentationDetents([.medium, .large]).environment(\.locale, Locale(identifier: "zh_CN"))
            }
            .alert("语音输入", isPresented: Binding(get: { dictation.errorMessage != nil }, set: { if !$0 { dictation.errorMessage = nil } })) {
                Button("确定") { dictation.errorMessage = nil }
            } message: { Text(dictation.errorMessage ?? "") }
    }
    private func fieldLabel(_ title: String, symbol: String) -> some View {
        HStack(spacing: 9) {
            Image(systemName: symbol).font(.system(size: 24)).foregroundStyle(CareTheme.accent).accessibilityHidden(true)
            Text(title).font(CareTheme.font(21, bold: true)).fixedSize(horizontal: false, vertical: true)
        }.accessibilityAddTraits(.isHeader)
    }
}
