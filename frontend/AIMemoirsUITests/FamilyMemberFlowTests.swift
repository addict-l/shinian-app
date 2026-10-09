import XCTest

final class FamilyMemberFlowTests: XCTestCase {
    @MainActor
    func testAddTwoMembersAndEnterChatWithoutDateStep() throws {
        continueAfterFailure = false
        let app = XCUIApplication()
        app.launch()
        app.tabBars.buttons["新的回忆"].tap()
        XCTAssertTrue(app.textFields["member.realName"].waitForExistence(timeout: 10))
        XCTAssertFalse(app.buttons["member.add"].isEnabled)
        XCTAssertFalse(app.staticTexts["选择时间"].exists)
        attach(app, name: "01-add-family-member")

        addMember(in: app, name: "张建国", relationship: "爷爷")
        XCTAssertTrue(app.buttons["members.card.张建国"].waitForExistence(timeout: 5))
        app.buttons["members.addAnother"].tap()
        addMember(in: app, name: "王秀兰", relationship: "奶奶")
        XCTAssertTrue(app.buttons["members.card.王秀兰"].waitForExistence(timeout: 5))
        XCTAssertTrue(app.buttons["members.card.张建国"].exists)
        attach(app, name: "02-created-family-members")

        app.tabBars.buttons["首页"].tap()
        app.tabBars.buttons["新的回忆"].tap()
        XCTAssertTrue(app.buttons["members.card.张建国"].exists)
        app.buttons["members.card.张建国"].tap()
        if app.alerts["请求失败"].waitForExistence(timeout: 5) {
            app.alerts["请求失败"].buttons["确定"].tap()
        }
        XCTAssertTrue(app.staticTexts["与 张建国的回忆"].waitForExistence(timeout: 5))
        XCTAssertTrue(app.staticTexts["爷爷"].exists)
        XCTAssertFalse(app.staticTexts["选择时间"].exists)
        attach(app, name: "03-chat-with-selected-member")

        app.buttons["newMemory.step.1"].tap()
        XCTAssertTrue(app.buttons["members.card.张建国"].waitForExistence(timeout: 5))
        XCTAssertTrue(app.buttons["members.card.王秀兰"].exists)
    }

    @MainActor
    private func addMember(in app: XCUIApplication, name: String, relationship: String) {
        let nameField = app.textFields["member.realName"]
        XCTAssertTrue(nameField.waitForExistence(timeout: 5))
        nameField.tap()
        nameField.typeText(name)
        let relationshipField = app.textFields["member.relationship"]
        relationshipField.tap()
        relationshipField.typeText(relationship)
        app.buttons["member.birthday"].tap()
        let birthdayConfirmation = app.buttons["member.confirmBirthday"]
        for _ in 0..<3 where !birthdayConfirmation.isHittable { app.swipeUp() }
        birthdayConfirmation.tap()
        let add = app.buttons["member.add"]
        for _ in 0..<3 where !add.isHittable { app.swipeUp() }
        XCTAssertTrue(add.isEnabled)
        add.tap()
    }

    @MainActor
    private func attach(_ app: XCUIApplication, name: String) {
        let attachment = XCTAttachment(screenshot: app.screenshot())
        attachment.name = name
        attachment.lifetime = .keepAlways
        add(attachment)
    }
}
