import XCTest

final class JournalUIFlowTests: XCTestCase {
    @MainActor func testInlineRelationshipOptions() {
        let app = XCUIApplication()
        app.launchEnvironment["AI_MEMORIES_DESIGN_SCREEN"] = "add"
        app.launch()
        let toggle = app.buttons["member.relationshipOptions"]
        XCTAssertTrue(toggle.waitForExistence(timeout: 10))
        toggle.tap()
        XCTAssertTrue(app.buttons["member.role.奶奶"].waitForExistence(timeout: 5))
        attach(app, "inline-relationship-options")
        app.buttons["member.role.奶奶"].tap()
        XCTAssertEqual(app.textFields["member.relationship"].value as? String, "奶奶")
        XCTAssertFalse(app.buttons["member.role.奶奶"].exists)
        app.textFields["member.relationship"].tap()
        app.textFields["member.relationship"].typeText("自定义")
        XCTAssertEqual(app.textFields["member.relationship"].value as? String, "奶奶自定义")
    }

    @MainActor func testChatComposerStaysAboveNavigationAndKeyboard() throws {
        continueAfterFailure = false
        let app = XCUIApplication()
        app.launchEnvironment["AI_MEMORIES_DESIGN_SCREEN"] = "chat"
        app.launch()
        let input = app.textFields["chat.input"]
        let tab = app.buttons["tab.compose"]
        XCTAssertTrue(input.waitForExistence(timeout: 15))
        XCTAssertTrue(input.isHittable)
        XCTAssertLessThanOrEqual(input.frame.maxY, tab.frame.minY)
        XCTAssertTrue(app.buttons["添加照片"].isHittable)
        XCTAssertTrue(app.buttons["语音输入"].isHittable)
        attach(app, "chat-input-visible")

        input.tap()
        input.typeText("那天他笑着鼓励我继续骑。")
        let send = app.buttons["chat.send"]
        XCTAssertTrue(send.isHittable)
        XCTAssertLessThanOrEqual(input.frame.maxY, tab.frame.minY)
        if app.keyboards.firstMatch.exists {
            XCTAssertLessThanOrEqual(send.frame.maxY, app.keyboards.firstMatch.frame.minY)
        }
        attach(app, "chat-keyboard-visible")
        send.tap()
        XCTAssertTrue(app.staticTexts["那天他笑着鼓励我继续骑。"].waitForExistence(timeout: 10))
        XCTAssertTrue(input.isHittable)
        XCTAssertLessThanOrEqual(input.frame.maxY, tab.frame.minY)
    }

    @MainActor func testDesignScreens() throws {
        continueAfterFailure = false
        for (screen, ready) in [("home", "把平凡，留成永远。"), ("add", "先认识一位家人"), ("select", "今天，想起了谁？"), ("chat", "关于爷爷"), ("review", "回忆预览"), ("film", "家庭胶片"), ("memories", "所有回忆"), ("person", "陈建国"), ("profile", "回忆的收藏者")] {
            let app = XCUIApplication()
            app.launchEnvironment["AI_MEMORIES_DESIGN_SCREEN"] = screen
            app.launch()
            XCTAssertTrue(app.staticTexts[ready].firstMatch.waitForExistence(timeout: 15), screen)
            if screen == "review" { XCTAssertTrue(app.buttons["memory.save"].waitForExistence(timeout: 10)) }
            attach(app, screen)
            app.terminate()
        }
    }

    @MainActor func testCreatePersonChatPreviewConfirmAndNavigate() throws {
        continueAfterFailure = false
        let app = XCUIApplication(); app.launchEnvironment["AI_MEMORIES_DESIGN_SCREEN"] = "home"; app.launch()
        XCTAssertTrue(app.buttons["tab.compose"].waitForExistence(timeout: 10)); app.buttons["tab.compose"].tap()
        let add = app.buttons["member.add"]
        XCTAssertTrue(add.waitForExistence(timeout: 10)); XCTAssertFalse(add.isEnabled)
        XCTAssertFalse(app.staticTexts["选择时间"].exists)
        app.textFields["member.realName"].tap(); app.textFields["member.realName"].typeText("UI测试人物")
        app.textFields["member.relationship"].tap(); app.textFields["member.relationship"].typeText("外公")
        app.buttons["member.birthday"].tap()
        XCTAssertTrue(app.buttons["member.confirmBirthday"].waitForExistence(timeout: 5)); app.buttons["member.confirmBirthday"].tap()
        reveal(add, app); XCTAssertTrue(add.isEnabled); add.tap()
        let person = app.buttons["members.card.UI测试人物"]
        XCTAssertTrue(person.waitForExistence(timeout: 10))
        // 新增人物即有胶卷，不能等到保存第一段回忆才出现。
        app.buttons["tab.family"].tap()
        app.buttons["film.allFamily"].tap()
        let familySearch = app.textFields["搜索家人的姓名或身份"]
        XCTAssertTrue(familySearch.waitForExistence(timeout: 5))
        familySearch.tap(); familySearch.typeText("UI测试人物")
        XCTAssertEqual(app.staticTexts["film.count.UI测试人物"].label, "0 段回忆")
        XCTAssertTrue(app.buttons["film.empty.UI测试人物"].exists)
        app.buttons["tab.compose"].tap()
        reveal(person, app); person.tap()
        let input = app.textFields["chat.input"]
        XCTAssertTrue(input.waitForExistence(timeout: 10)); input.tap(); input.typeText("他在院子里教我骑车。")
        app.buttons["chat.send"].tap()
        let generate = app.buttons["chat.generate"]; reveal(generate, app); generate.tap()
        let save = app.buttons["memory.save"]; XCTAssertTrue(save.waitForExistence(timeout: 10)); save.tap()
        XCTAssertTrue(app.staticTexts["关于他的回忆"].waitForExistence(timeout: 10))
        app.buttons["tab.family"].tap()
        XCTAssertTrue(app.staticTexts["家庭胶片"].waitForExistence(timeout: 5))
        app.buttons["film.allFamily"].tap()
        XCTAssertTrue(familySearch.waitForExistence(timeout: 5))
        familySearch.tap(); familySearch.typeText("UI测试人物")
        XCTAssertEqual(app.staticTexts["film.count.UI测试人物"].label, "1 段回忆")
        XCTAssertFalse(app.buttons["film.empty.UI测试人物"].exists)
        app.buttons["tab.home"].tap(); app.buttons["tab.family"].tap()
        app.buttons["film.person.陈建国"].tap()
        XCTAssertTrue(app.staticTexts["关于他的回忆"].waitForExistence(timeout: 5))
        app.buttons["tab.profile"].tap()
        XCTAssertTrue(app.staticTexts["回忆的收藏者"].waitForExistence(timeout: 5))
        app.buttons["我的全部回忆"].tap()
        XCTAssertTrue(app.staticTexts["所有回忆"].waitForExistence(timeout: 5))
        let search = app.textFields["搜索回忆、人物或一句话"]; search.tap(); search.typeText("不存在的标题xyz")
        XCTAssertTrue(app.staticTexts["没有找到相关回忆"].waitForExistence(timeout: 5))
    }
    @MainActor private func reveal(_ element: XCUIElement, _ app: XCUIApplication) {
        for _ in 0..<7 where !element.isHittable { app.swipeUp() }
        if !element.isHittable {
            attach(app, "unreachable-element")
            print(app.debugDescription)
        }
        XCTAssertTrue(element.isHittable)
    }
    @MainActor private func attach(_ app: XCUIApplication, _ name: String) {
        let image = XCTAttachment(screenshot: app.screenshot()); image.name = "journal-v1-" + name
        image.lifetime = .keepAlways; add(image)
    }
}
