import SwiftUI

/// 添加人物表单：绑定草稿，展示校验和请求状态，通过回调提交。
struct JournalAddPersonView: View {
    @Binding var draft: FamilyMemberDraft
    let loading: Bool
    let error: String?
    let onAdd: () -> Void
    let onSelect: () -> Void
    @State private var showingBirthday = false
    @State private var showingRelationships = false
    @State private var relationshipOptionsHeight: CGFloat = 0
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var pickedBirthday = APIDate.parseDay("1950-01-01")!
    @FocusState private var focused: Field?
    private enum Field { case name, relationship }
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 0) {
                JournalHeader(kicker: "新的回忆     /     01 添加人物", title: "先认识一位家人", subtitle: "把重要的人，放进你的回忆里。")
                    .padding(.bottom, 27)
                HStack(spacing: 13) {
                    Image(systemName: "person").font(.system(size: 22)).foregroundStyle(JournalTheme.accent)
                        .frame(width: 44, height: 44).background(JournalTheme.surface, in: Circle())
                    Text("每一段回忆，\n都从一个人开始。").font(JournalTheme.font(14)).lineSpacing(5).foregroundStyle(JournalTheme.accent)
                    Spacer()
                }.padding(.horizontal, 15).frame(minHeight: 76)
                    .background(JournalTheme.soft, in: RoundedRectangle(cornerRadius: 18)).padding(.bottom, 30)
                field("真实姓名") {
                    TextField("填写家人的真实姓名", text: $draft.realName).focused($focused, equals: .name)
                        .textContentType(.name).submitLabel(.next).onSubmit { focused = .relationship }
                        .accessibilityIdentifier("member.realName")
                }.padding(.bottom, 28)
                field("家庭身份") {
                    TextField("例如爷爷、奶奶", text: $draft.relationship).focused($focused, equals: .relationship)
                        .submitLabel(.done).onSubmit { focused = nil }.accessibilityIdentifier("member.relationship")
                    Button {
                        focused = nil
                        showingRelationships.toggle()
                    } label: {
                        Image(systemName: "chevron.down").font(.system(size: 13))
                            .rotationEffect(.degrees(showingRelationships ? 180 : 0))
                            .foregroundStyle(JournalTheme.accent).frame(width: 44, height: 44)
                            .contentShape(Rectangle())
                    }.buttonStyle(.plain)
                        .accessibilityLabel("选择常用家庭身份")
                        .accessibilityValue(showingRelationships ? "已展开" : "已收起")
                        .accessibilityIdentifier("member.relationshipOptions")
                }
                // 保留面板实例并测量自然高度，动画只改变可见高度。
                // 避免条件插入与位移过渡叠加，造成选项跳入、下方表单突然换位。
                JournalRelationshipOptions(selection: draft.relationship) { role in
                    draft.relationship = role
                    showingRelationships = false
                }
                .padding(.top, 10)
                .fixedSize(horizontal: false, vertical: true)
                .onGeometryChange(for: CGFloat.self) { $0.size.height } action: { height in
                    relationshipOptionsHeight = height
                }
                .opacity(showingRelationships ? 1 : 0)
                .animation(reduceMotion ? nil : .easeOut(duration: 0.18), value: showingRelationships)
                .frame(height: showingRelationships ? relationshipOptionsHeight : 0, alignment: .top)
                .clipped()
                .allowsHitTesting(showingRelationships)
                .accessibilityHidden(!showingRelationships)
                VStack(alignment: .leading, spacing: 13) {
                    Text("生日").font(JournalTheme.font(12)).foregroundStyle(JournalTheme.muted)
                    Button {
                        focused = nil; pickedBirthday = draft.birthDate ?? APIDate.parseDay("1950-01-01")!; showingBirthday = true
                    } label: {
                        HStack {
                            Text(draft.birthDate.map(JournalFormat.birthday) ?? "选择家人的生日")
                                .foregroundStyle(draft.birthDate == nil ? JournalTheme.muted : JournalTheme.ink)
                            Spacer(); Image(systemName: "calendar").foregroundStyle(JournalTheme.muted)
                        }.font(JournalTheme.font(16)).padding(.horizontal, 16).frame(height: 54)
                            .background(JournalTheme.surface, in: RoundedRectangle(cornerRadius: 14))
                    }.buttonStyle(.plain).accessibilityIdentifier("member.birthday")
                }.padding(.top, 28)
                Text("家庭身份支持自定义，例如姑姑、舅舅。").font(JournalTheme.font(12)).foregroundStyle(JournalTheme.muted).padding(.top, 26)
                if let error { Text(error).font(JournalTheme.font(12)).foregroundStyle(.red).padding(.top, 14) }
                JournalButton(title: "添加并继续", loading: loading, disabled: !draft.isValid()) { focused = nil; onAdd() }
                    .padding(.top, 44).accessibilityIdentifier("member.add")
                Button("已添加过家人？选择已有的人物", action: onSelect)
                    .font(JournalTheme.font(13)).foregroundStyle(JournalTheme.lavender)
                    .frame(maxWidth: .infinity).frame(minHeight: 44).padding(.top, 6)
                    .buttonStyle(.plain)
                    .accessibilityIdentifier("newMemory.step.1")
            }.padding(.horizontal, 24).padding(.bottom, 28)
                // 与箭头、生日和按钮共用可中断的平滑曲线；滚动容器不参与隐式动画。
                .animation(reduceMotion ? nil : .smooth(duration: 0.36, extraBounce: 0), value: showingRelationships)
        }.scrollIndicators(.hidden).scrollDismissesKeyboard(.interactively)
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
    private func field<Content: View>(_ title: String, @ViewBuilder content: () -> Content) -> some View {
        VStack(alignment: .leading, spacing: 13) {
            Text(title).font(JournalTheme.font(12)).foregroundStyle(JournalTheme.muted)
            HStack { content() }.font(JournalTheme.font(16)).padding(.horizontal, 16).frame(height: 54)
                .background(JournalTheme.surface, in: RoundedRectangle(cornerRadius: 14))
        }
    }
}
