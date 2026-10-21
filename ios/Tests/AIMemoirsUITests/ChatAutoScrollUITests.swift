import XCTest

/// Explicit offline previews in a separate verification bundle; no family account is used.
final class StandardChatAutoScrollUITests: XCTestCase {
    @MainActor private func launch(life: Bool) -> XCUIApplication {
        continueAfterFailure = false
        XCUIDevice.shared.orientation = .portrait
        let app = XCUIApplication()
        app.launchArguments = ["--design-screen", life ? "care-life-scroll" : "chat-scroll", "-journal.careMode.enabled", "NO"]
        app.launch()
        let tag = life ? "life" : "chat"
        XCTAssertTrue(input(app, tag).waitForExistence(timeout: 20))
        wait { app.scrollViews[tag + ".history"].value as? String == "最新消息" }
        return app
    }

    @MainActor private func input(_ app: XCUIApplication, _ tag: String) -> XCUIElement {
        app.descendants(matching: .any).matching(identifier: tag + ".input").firstMatch
    }

    @MainActor private func wait(_ timeout: Double = 12, condition: @escaping () -> Bool) {
        let expectation = XCTNSPredicateExpectation(predicate: NSPredicate { _, _ in condition() }, object: nil)
        XCTAssertEqual(XCTWaiter.wait(for: [expectation], timeout: timeout), .completed)
    }

    @MainActor private func shot(_ name: String, _ app: XCUIApplication) {
        let item = XCTAttachment(screenshot: XCUIScreen.main.screenshot())
        item.name = name; item.lifetime = .keepAlways; add(item)
        let keyboard = app.keyboards.firstMatch
        let tag = name.hasPrefix("life") ? "life" : "chat"
        let history = app.scrollViews[tag + ".history"]
        let frames = "app=\(app.frame), keyboardExists=\(keyboard.exists), keyboard=\(keyboard.exists ? keyboard.frame : .zero), historyValue=\(String(describing: history.value)), latestButton=\(app.buttons[tag + ".history.latest"].exists)"
        let geometry = XCTAttachment(string: frames)
        geometry.name = name + "-geometry"; geometry.lifetime = .keepAlways; add(geometry)
    }

    /// The existing assistant bubble exposes both a combined label and its Text child.
    /// Check the visible matching element rather than relying on the first AX match.
    @MainActor private func visibleText(_ text: String, _ app: XCUIApplication) -> Bool {
        app.staticTexts.matching(NSPredicate(format: "label == %@", text))
            .allElementsBoundByIndex.contains { $0.isHittable }
    }

    @MainActor private func assertSoftwareKeyboard(_ app: XCUIApplication) {
        let keyboard = app.keyboards.firstMatch
        XCTAssertTrue(keyboard.waitForExistence(timeout: 8))
        wait { keyboard.frame.height > 100 && keyboard.frame.minY < app.frame.maxY - 100 }
    }

    @MainActor private func send(_ text: String, _ app: XCUIApplication, _ tag: String) {
        let field = input(app, tag)
        field.tap(); field.typeText(text)
        app.buttons[tag + ".send"].tap()
    }

    @MainActor private func exerciseFollow(life: Bool) {
        let app = launch(life: life)
        let tag = life ? "life" : "chat"
        let history = app.scrollViews[tag + ".history"]
        let latest = "本地旧记录 13：那年家门口有一棵树。我们在树下说话，记住了生活里的小事。"
        XCTAssertTrue(visibleText(latest, app))
        input(app, tag).tap()
        assertSoftwareKeyboard(app)
        wait { history.value as? String == "最新消息" }
        XCTAssertLessThanOrEqual(input(app, tag).frame.maxY, app.keyboards.firstMatch.frame.minY + 3)
        XCTAssertTrue(visibleText(latest, app))
        shot(tag + "-keyboard-latest", app)
        input(app, tag).typeText("local answer")
        app.buttons[tag + ".send"].tap()
        let reply = app.staticTexts["本地回复：local answer"]
        XCTAssertTrue(reply.waitForExistence(timeout: 10))
        wait { self.visibleText("本地回复：local answer", app) && history.value as? String == "最新消息" }
        shot(tag + "-send-and-reply", app)
        send("长回复", app, tag)
        let longReply = app.staticTexts.matching(NSPredicate(format: "label BEGINSWITH '长回复第 1 行' ")).firstMatch
        XCTAssertTrue(longReply.waitForExistence(timeout: 10))
        wait { history.value as? String == "最新消息" }
        XCTAssertLessThanOrEqual(longReply.frame.maxY, history.frame.maxY + 3)
        shot(tag + "-long-reply-bottom", app)
        app.terminate()
    }

    @MainActor func testStoryChatFollowsRepliesLongContentAndKeyboard() { exerciseFollow(life: false) }
    @MainActor func testLifeChatFollowsRepliesLongContentAndKeyboard() { exerciseFollow(life: true) }

    @MainActor func testIncomingRepliesPreserveHistoryAndExplicitActionsResume() {
        for life in [false, true] {
            let app = launch(life: life)
            let tag = life ? "life" : "chat"
            let history = app.scrollViews[tag + ".history"]
            send("history reply", app, tag)
            history.swipeDown(velocity: .fast)
            history.swipeDown(velocity: .fast)
            wait { app.buttons[tag + ".history.latest"].isHittable }
            let anchor = app.staticTexts.allElementsBoundByIndex.first { item in
                item.label.hasPrefix("本地旧记录") && item.frame.minY > history.frame.minY + 8 && item.frame.maxY < history.frame.maxY - 8
            }
            XCTAssertNotNil(anchor)
            let before = anchor!.frame.minY
            XCTAssertTrue(app.staticTexts["本地回复：history reply"].waitForExistence(timeout: 10))
            XCTAssertEqual(history.value as? String, "历史消息")
            XCTAssertEqual(anchor!.frame.minY, before, accuracy: 4)
            shot(tag + "-history-preserved", app)
            app.buttons[tag + ".history.latest"].tap()
            wait { history.value as? String == "最新消息" }
            XCTAssertTrue(visibleText("本地回复：history reply", app))
            history.swipeDown(velocity: .fast)
            wait { app.buttons[tag + ".history.latest"].isHittable }
            send("own send resumes", app, tag)
            let reply = app.staticTexts["本地回复：own send resumes"]
            XCTAssertTrue(reply.waitForExistence(timeout: 10))
            wait { history.value as? String == "最新消息" && self.visibleText("本地回复：own send resumes", app) }
            shot(tag + "-own-send-resumes", app)
            app.terminate()
        }
    }

    @MainActor func testStoryLandscapeKeepsLatestAboveKeyboard() {
        let app = launch(life: false)
        XCUIDevice.shared.orientation = .landscapeLeft
        defer { XCUIDevice.shared.orientation = .portrait; app.terminate() }
        wait { app.frame.width > app.frame.height }
        let field = input(app, "chat")
        field.tap()
        assertSoftwareKeyboard(app)
        wait { app.scrollViews["chat.history"].value as? String == "最新消息" }
        XCTAssertLessThanOrEqual(field.frame.maxY, app.keyboards.firstMatch.frame.minY + 3)
        XCTAssertTrue(visibleText("本地旧记录 13：那年家门口有一棵树。我们在树下说话，记住了生活里的小事。", app))
        shot("chat-landscape-keyboard", app)
    }
}
