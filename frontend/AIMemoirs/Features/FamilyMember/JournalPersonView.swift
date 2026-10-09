import SwiftUI

/// 人物详情：展示资料与相关回忆，可从这里进入新的对话。
struct JournalPersonView: View {
    let person: FamilyMember
    @EnvironmentObject private var memories: MemoryListViewModel
    @EnvironmentObject private var navigation: JournalNavigation
    @State private var showingInfo = false
    private var events: [MemoryEvent] { memories.getMemoryEvents(for: person.id) }
    var body: some View {
        ScrollView {
            VStack(spacing: 0) {
                JournalAvatar(person: person, size: 82).padding(.top, 24)
                Text(person.name).font(JournalTheme.font(27, medium: true)).padding(.top, 20)
                Text(person.journalIdentity).font(JournalTheme.font(13)).foregroundStyle(JournalTheme.muted).padding(.top, 12)
                JournalButton(title: "＋  记录与\(person.relationship.isEmpty ? person.name : person.relationship)的故事") { navigation.compose(with: person) }
                    .padding(.top, 33)
                HStack {
                    Text("关于\(person.gender == .female ? "她" : "他")的回忆").font(JournalTheme.font(18, medium: true)); Spacer()
                    Text("\(events.count) 段").font(JournalTheme.font(12)).foregroundStyle(JournalTheme.muted)
                }.padding(.top, 38).padding(.bottom, 20)
                LazyVStack(spacing: 16) {
                    ForEach(events) { event in
                        JournalMemoryCard(memory: event, subtitle: event.dateLabel) { navigation.path.append(.memory(event.id)) }
                    }
                }
                if events.isEmpty { JournalEmptyState(title: "故事，从这里开始", message: "记录一段你们共同的回忆。") }
                Text("还有很多故事，等你慢慢说。").font(JournalTheme.font(12)).foregroundStyle(JournalTheme.muted)
                    .frame(maxWidth: .infinity, alignment: .leading).padding(.top, 36).padding(.bottom, 28)
            }.padding(.horizontal, 24)
        }.scrollIndicators(.hidden).journalPage().navigationBarTitleDisplayMode(.inline)
            .toolbar(.visible, for: .navigationBar)
            .toolbar { ToolbarItem(placement: .topBarTrailing) { Button("人物资料") { showingInfo = true }.font(JournalTheme.font(13)) } }
            .sheet(isPresented: $showingInfo) {
                NavigationStack {
                    Form {
                        LabeledContent("真实姓名", value: person.name)
                        LabeledContent("家庭身份", value: person.relationship)
                        LabeledContent("生日", value: person.birthDate.map(JournalFormat.birthday) ?? "待补充")
                        Text("人物编辑接口尚未接入，当前资料来自服务器。").foregroundStyle(.secondary)
                    }.navigationTitle("人物资料").toolbar { ToolbarItem(placement: .confirmationAction) { Button("完成") { showingInfo = false } } }
                }.presentationDetents([.medium])
            }
    }
}
