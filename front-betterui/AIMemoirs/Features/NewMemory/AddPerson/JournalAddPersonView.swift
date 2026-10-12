import SwiftUI

/// 添加人物表单：绑定草稿，展示校验和请求状态，通过回调提交。
struct JournalAddPersonView: View {
    @Binding var draft: FamilyMemberDraft
    let loading: Bool
    let error: String?
    let onAdd: () -> Void
    let onSelect: () -> Void
    var onClose: () -> Void = {}
    @State private var showingBirthday = false
    @State private var pickedBirthday = APIDate.parseDay("1950-01-01")!
    @FocusState private var focused: Field?
    private enum Field { case name, relationship }
    var body: some View {
        VStack(spacing: 0) {
            JournalNavBar {
                JournalRoundButton(icon: "x", label: "关闭", action: onClose).accessibilityIdentifier("member.close")
            } trailing: { Color.clear.frame(width: 44, height: 44) }
            .overlay {
                HStack(spacing: 6) {
                    Capsule().fill(JournalTheme.accent).frame(width: 22, height: 6)
                    Circle().fill(JournalTheme.line).frame(width: 6, height: 6)
                    Circle().fill(JournalTheme.line).frame(width: 6, height: 6)
                }.accessibilityHidden(true)
            }
            ScrollView {
                VStack(alignment: .leading, spacing: 0) {
                    JournalEyebrow(lead: "新的回忆", trail: "01 添加人物")
                    JournalTitle("每一段回忆，\n都从一个人开始。", size: 27).padding(.top, 10)
                    JournalSubtitle("把重要的人，放进你的回忆里。").padding(.top, 4)

                    HStack(spacing: 0) {
                        Text("家庭身份").font(JournalTheme.font(14, medium: true)).foregroundStyle(JournalTheme.ink)
                        Text(" · 选一个熟悉的称呼").font(JournalTheme.font(12)).foregroundStyle(JournalTheme.muted)
                    }.padding(.top, 18)
                    JournalRelationshipOptions(selection: draft.relationship) { role in
                        draft.relationship = role; focused = nil
                    }.padding(.top, 10)

                    JournalFieldBox(label: "家庭身份") {
                        TextField("", text: $draft.relationship, prompt: Text("例如爷爷、奶奶").foregroundStyle(JournalTheme.placeholder))
                            .focused($focused, equals: .relationship)
                            .submitLabel(.next).onSubmit { focused = .name }.accessibilityIdentifier("member.relationship")
                    }.padding(.top, 12)
                    Text("家庭身份支持自定义，例如姑姑、舅舅。").font(JournalTheme.font(12)).foregroundStyle(JournalTheme.muted)
                        .padding(.horizontal, 4).padding(.top, 6)

                    JournalFieldBox(label: "真实姓名") {
                        TextField("", text: $draft.realName, prompt: Text("填写家人的真实姓名").foregroundStyle(JournalTheme.placeholder))
                            .focused($focused, equals: .name)
                            .textContentType(.name).submitLabel(.done).onSubmit { focused = nil }
                            .accessibilityIdentifier("member.realName")
                    }.padding(.top, 12)

                    Button {
                        focused = nil; pickedBirthday = draft.birthDate ?? APIDate.parseDay("1950-01-01")!; showingBirthday = true
                    } label: {
                        JournalFieldBox(label: "生日") {
                            Text(draft.birthDate.map(JournalSpacedDate.string) ?? "选择家人的生日")
                                .foregroundStyle(draft.birthDate == nil ? JournalTheme.placeholder : JournalTheme.ink)
                        } accessory: {
                            DesignIcon("cal").foregroundStyle(JournalTheme.accent)
                        }.contentShape(Rectangle())
                    }.buttonStyle(.plain).padding(.top, 12).accessibilityIdentifier("member.birthday")

                    if let error { Text(error).font(JournalTheme.font(12)).foregroundStyle(JournalTheme.danger).padding(.top, 14) }
                    JournalButton(title: "添加并继续", loading: loading, disabled: !draft.isValid()) { focused = nil; onAdd() }
                        .padding(.top, 22).accessibilityIdentifier("member.add")
                    if loading {
                        Text("正在为\(draft.relationship)准备开场白…").font(JournalTheme.font(12))
                            .foregroundStyle(JournalTheme.muted).frame(maxWidth: .infinity).padding(.top, 12)
                    }
                    Button(action: onSelect) {
                        Text("已添加过家人？选择已有的人物 ›").font(JournalTheme.font(13.5)).foregroundStyle(JournalTheme.accentDeep)
                            .frame(maxWidth: .infinity).frame(minHeight: 44)
                    }
                    .buttonStyle(.plain).padding(.top, 4)
                    .accessibilityIdentifier("newMemory.step.1")
                }.padding(.horizontal, JournalTheme.gutter).padding(.top, 4).padding(.bottom, 28)
            }.disabled(loading).scrollIndicators(.hidden).scrollDismissesKeyboard(.interactively)
        }
        .sheet(isPresented: $showingBirthday) {
            NavigationStack {
                DatePicker("生日", selection: $pickedBirthday, in: ...Date(), displayedComponents: .date)
                    .datePickerStyle(.wheel).labelsHidden().padding()
                    .navigationTitle("家人的生日").navigationBarTitleDisplayMode(.inline)
                    .toolbar {
                        ToolbarItem(placement: .cancellationAction) { Button("取消") { showingBirthday = false } }
                        ToolbarItem(placement: .confirmationAction) {
                            Button("确定") { draft.birthDate = pickedBirthday; showingBirthday = false }.accessibilityIdentifier("member.confirmBirthday")
                        }
                    }
            }.presentationDetents([.height(340)]).environment(\.locale, Locale(identifier: "zh_CN"))
        }
    }
}
