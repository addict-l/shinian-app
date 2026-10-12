import SwiftUI

struct JournalPersonView: View {
    let person: FamilyMember
    @EnvironmentObject private var memories: MemoryListViewModel
    @EnvironmentObject private var navigation: JournalNavigation
    private var events: [MemoryEvent] { memories.getMemoryEvents(for: person.id).sorted { $0.createdAt > $1.createdAt } }
    private var role: String { person.relationship.isEmpty ? person.name : person.relationship }
    private var hasOwnStories: Bool { events.contains { $0.primaryPersonID == person.id } }

    var body: some View {
        VStack(spacing: 0) {
            JournalBackBar(title: "人物资料")
            ScrollView {
                VStack(alignment: .leading, spacing: 0) {
                    identityCard
                    Button { navigation.path.append(.memoir(person.id)) } label: {
                        HStack(spacing: 12) {
                            JournalIconTile(icon: "book", fill: JournalTheme.butterSoft, ink: JournalTheme.butterInk, size: 44, radius: 14)
                            VStack(alignment: .leading, spacing: 3) {
                                Text("制作／继续制作回忆录").font(JournalTheme.font(15.5, medium: true)).foregroundStyle(JournalTheme.ink)
                                Text("封面、目录、故事和照片排成一本 PDF").font(JournalTheme.font(12)).foregroundStyle(JournalTheme.muted)
                            }
                            Spacer(minLength: 0)
                            DesignIcon("chev").foregroundStyle(JournalTheme.muted)
                        }.padding(16).journalCard()
                    }.buttonStyle(JournalActionButtonStyle()).padding(.top, 14).accessibilityIdentifier("person-memoir")
                        .disabled(!hasOwnStories)
                    if !hasOwnStories {
                        Text("先保存一段以这位家人为主人物的回忆，再制作回忆录。")
                            .font(JournalTheme.font(12)).foregroundStyle(JournalTheme.muted).padding(.top, 8)
                    }
                    JournalSectionHeader(title: JournalDemo.isPreview ? "关于\(person.gender == .female ? "她" : "他")" : "关于\(role)") {
                        Text("\(events.count) 段").font(JournalTheme.font(12)).foregroundStyle(JournalTheme.muted)
                    }
                    VStack(spacing: 12) {
                        ForEach(Array(events.enumerated()), id: \.element.id) { index, event in
                            HStack(spacing: 12) {
                                Circle().fill(JournalTheme.rotating(index).dot).frame(width: 8, height: 8)
                                    .overlay { Circle().stroke(JournalTheme.rotating(index).ring, lineWidth: 3) }
                                Button { navigation.path.append(.memory(event.id)) } label: {
                                    HStack(spacing: 12) {
                                        JournalPhoto(memory: event, height: 58, radius: 12).frame(width: 58)
                                        VStack(alignment: .leading, spacing: 4) {
                                            Text(event.title).font(JournalTheme.story(15.5)).foregroundStyle(JournalTheme.ink).lineLimit(1)
                                            Text(memoryWhenWhere(event)).font(JournalTheme.font(12)).foregroundStyle(JournalTheme.muted).lineLimit(1)
                                        }
                                        Spacer(minLength: 0)
                                    }.padding(10).journalCard()
                                }.buttonStyle(.plain)
                            }
                        }
                    }.background(alignment: .leading) { JournalTheme.line.frame(width: 1).padding(.leading, 3.5).padding(.vertical, 36) }
                }.padding(.horizontal, JournalTheme.gutter).padding(.top, 6).padding(.bottom, 16)
            }.scrollIndicators(.hidden)
            JournalButton(title: "记录与\(role)的故事", icon: "plus") { navigation.compose(with: person) }
                .padding(.horizontal, JournalTheme.gutter).padding(.top, 8).padding(.bottom, 16)
        }.journalPage()
    }
    private var identityCard: some View {
        VStack(alignment: .leading, spacing: 16) {
            HStack(spacing: 16) {
                JournalAvatar(person: person, size: 88)
                VStack(alignment: .leading, spacing: 4) {
                    Text(role).font(JournalTheme.font(12)).foregroundStyle(JournalTheme.accentDeep)
                        .padding(.horizontal, 10).frame(height: 24).background(.white, in: Capsule())
                    Text(person.name).font(JournalTheme.story(25))
                    Text("生日 · " + (person.birthDate.map(JournalSpacedDate.string) ?? "待补充"))
                        .font(JournalTheme.font(12)).foregroundStyle(JournalTheme.muted)
                }
            }
            Text("还有很多故事，等你慢慢说。").font(JournalTheme.story(14)).foregroundStyle(Color(hex: 0x9A7B62))
        }.frame(maxWidth: .infinity, alignment: .leading).padding(20)
            .background(alignment: .bottomTrailing) { Circle().fill(.white.opacity(0.35)).frame(width: 160, height: 160).offset(x: 20, y: 40) }
            .background(LinearGradient(colors: [Color(hex: 0xFCEBDD), Color(hex: 0xF7E1CF)], startPoint: .topLeading, endPoint: .bottomTrailing)).clipShape(RoundedRectangle(cornerRadius: 28))
    }
}
