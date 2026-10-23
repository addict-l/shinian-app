import Foundation
import Testing
@testable import AIMemoirs

struct CareLifeSummaryTests {
    @Test @MainActor func skeletonAnswersAppearInAllThreeGroupsWithoutChangingOriginalWords() {
        let ids = ["SK01", "SK01b", "SK01c", "SK02", "SK03", "SK03b", "SK03c", "SK03d", "SK04", "SK05", "SK06"]
        let fields = ids.map { field($0, quotes: ["原话 \($0)", "补充 \($0)"]) }
        let groups = CareLifeSummaryGroups.make(fields: fields)

        #expect(groups.map(\.title) == ["出生与家乡", "小时候的家", "性格与一生"])
        #expect(groups.map(\.fieldIDs) == [Array(ids[0..<4]), Array(ids[4..<9]), Array(ids[9..<11])])
        #expect(groups.flatMap(\.lines).map(\.text) == ids.map { "原话 \($0)\n补充 \($0)" })
        #expect(groups.flatMap(\.lines).allSatisfy { !$0.subdued })
    }

    @Test @MainActor func legacyAnswersKeepTheirExistingGroups() {
        let ids = ["home", "learning", "early_work", "later_work", "family", "changes", "present"]
        let groups = CareLifeSummaryGroups.make(fields: ids.map { field($0, quotes: ["讲述 \($0)"]) })

        #expect(groups.map(\.title) == ["小时候", "读书工作", "家人近况"])
        #expect(groups.map(\.fieldIDs) == [["home"], ["learning", "early_work", "later_work"], ["family", "changes", "present"]])
        #expect(groups.flatMap(\.lines).count == ids.count)
    }

    @Test @MainActor func mixedAndFutureFieldsRemainVisibleUnderOther() {
        let fields = [field("SK01", quotes: ["一九四八年出生。"]),
                      field("home", quotes: ["老题库里的原话也保留。"]),
                      field("SK99", quotes: ["新增加的问题。"])]
        let groups = CareLifeSummaryGroups.make(fields: fields)

        #expect(groups.last?.title == "其他")
        #expect(groups.last?.fieldIDs == ["home", "SK99"])
        #expect(groups.last?.lines.map(\.text) == ["老题库里的原话也保留。", "新增加的问题。"])
        #expect(Set(groups.flatMap(\.fieldIDs)) == Set(fields.map(\.id)))
    }

    @Test @MainActor func unansweredStatesDoNotHideNeighboringQuotes() {
        let fields = [field("SK01", quotes: ["  我是一九四八年出生的。  "]),
                      field("SK01b", status: "skipped"),
                      field("SK01c", status: "unknown"),
                      field("SK02", status: "declined"),
                      field("SK03", status: "pending", quotes: ["未确认的待填内容"]),
                      field("SK05", status: "unknown", quotes: ["这一部分我还记得。"])]
        let groups = CareLifeSummaryGroups.make(fields: fields)

        #expect(groups[0].lines.map(\.text) == ["  我是一九四八年出生的。  ", "出生地点：暂时跳过", "记忆中的家乡：记不清", "名字与期许：暂时不想讲"])
        #expect(groups[0].lines.map(\.subdued) == [false, true, true, true])
        #expect(groups[1].lines.isEmpty)
        #expect(groups[1].text == "之后可以慢慢补充。")
        #expect(groups[2].lines.first?.text == "这一部分我还记得。")
        #expect(!groups.flatMap(\.lines).contains { $0.text.contains("未确认的待填内容") })
    }

    #if DEBUG
    @Test @MainActor func v2PreviewKeepsElevenFieldsAfterConfirmation() async throws {
        let api = JournalDemoAPI(emptyState: "care-life-review-v2")
        let person = try #require(try await api.members().first)
        let snapshot = try await api.start(person: person, requestID: UUID())
        let overview = try #require(snapshot.lifeOverview)
        #expect(overview.total_questions == 11)
        #expect(overview.fields.count == 11)
        let confirmed = try await api.lifeAction(sessionID: snapshot.sessionID,
            command: LifeCommand(action: "confirm", expected_version: overview.version, client_request_id: UUID()))
        #expect(confirmed.lifeOverview?.status == "confirmed")
        #expect(confirmed.lifeOverview?.total_questions == 11)
    }

    @Test @MainActor func v2QuestionPreviewAdvancesToBirthplaceAndKeepsElevenQuestions() async throws {
        let api = JournalDemoAPI(emptyState: "care-life-question-v2")
        let person = try #require(try await api.members().first)
        let snapshot = try await api.start(person: person, requestID: UUID())
        let overview = try #require(snapshot.lifeOverview)
        #expect(overview.status == "collecting")
        #expect(overview.question_id == "SK01")
        #expect(overview.question_number == 1)
        #expect(overview.total_questions == 11)
        #expect(overview.fields.count == 11)
        #expect(overview.fields.allSatisfy { $0.status == "pending" && $0.evidence.isEmpty })

        let answer = "我是一九四八年出生的。"
        let next = try await api.lifeAction(sessionID: snapshot.sessionID,
            command: LifeCommand(action: "answer", expected_version: overview.version, client_request_id: UUID(), text: answer))
        let advanced = try #require(next.lifeOverview)
        #expect(advanced.question_id == "SK01b")
        #expect(advanced.question == "您出生在哪个地方？")
        #expect(advanced.question_number == 2)
        #expect(advanced.total_questions == 11)
        #expect(advanced.fields.first?.evidence.map(\.quote) == [answer])
        #expect(advanced.fields.dropFirst().allSatisfy { $0.status == "pending" })
    }
    #endif

    private func field(_ id: String, status: String = "known", quotes: [String] = []) -> LifeField {
        LifeField(topic_id: id, status: status, evidence: quotes.map { LifeQuote(message_id: UUID(), quote: $0) })
    }
}
