import XCTest

final class CareModeFlowTests: XCTestCase {
    @MainActor private func launch(_ screen: String? = nil, cloud: Bool = false, large: Bool = false) -> XCUIApplication {
        continueAfterFailure = false
        XCUIDevice.shared.orientation = .portrait
        let app = XCUIApplication()
        if let screen { app.launchArguments = ["--design-screen", screen] }
        if large { app.launchArguments += ["-UIPreferredContentSizeCategoryName", "UICTContentSizeCategoryAccessibilityXXXL"] }
        if cloud { app.launchEnvironment["AI_MEMORIES_API_URL"] = "http://localhost:18009" }
        app.launch()
        return app
    }
    @MainActor private func tap(_ element: XCUIElement, app: XCUIApplication, timeout: Double = 20) {
        XCTAssertTrue(element.waitForExistence(timeout: timeout))
        for _ in 0..<8 where !element.isHittable {
            if app.scrollViews.firstMatch.exists { app.scrollViews.firstMatch.swipeUp() }
            else { app.swipeUp() }
        }
        XCTAssertTrue(element.isHittable, element.debugDescription); element.tap()
    }
    @MainActor private func shot(_ name: String, _ app: XCUIApplication) {
        let attachment = XCTAttachment(screenshot: app.screenshot()); attachment.name = name; attachment.lifetime = .keepAlways; add(attachment)
    }
    @MainActor private func enableCare() -> XCUIApplication {
        let app = launch("settings")
        let mode = app.switches["settings.careMode"]
        XCTAssertTrue(mode.waitForExistence(timeout: 20))
        if mode.value as? String == "0" { mode.tap() }
        return app
    }
    @MainActor func testCareModePersistsAndDraftEditsReachSavedReading() {
        let first = enableCare(); first.terminate()
        let app = launch("care-life-review")
        XCTAssertTrue(app.buttons["life.confirm"].waitForExistence(timeout: 25))
        shot("care-life-review", app)
        tap(app.buttons["care.life.history"], app: app)
        XCTAssertTrue(app.buttons["care.history.previous"].exists)
        tap(app.buttons["care.history.next"], app: app)
        shot("care-history-second", app)
        tap(app.buttons["care.back"], app: app)
        tap(app.buttons["life.confirm"], app: app)
        for module in ["childhood", "growth", "work", "family", "later_life", "reflection"] {
            XCTAssertTrue(app.buttons["life.module." + module].isHittable)
        }
        shot("care-topics", app)
        tap(app.buttons["life.module.growth"], app: app)
        shot("care-narration", app)
        tap(app.buttons["chat.input.keyboard"], app: app)
        let input = app.textFields["chat.input"]
        XCTAssertTrue(input.waitForExistence(timeout: 15)); input.tap()
        input.typeText("我小时候在村里读书。老师握着我的手教我写名字，我写好了拿回家给母亲看。那一天特别开心。这段故事讲完了，请整理成草稿。")
        tap(app.buttons["chat.send"], app: app)
        tap(app.buttons["chat.generate"], app: app)
        tap(app.buttons["care.draft.edit"], app: app)
        let title = app.textFields["draft.title"]
        XCTAssertTrue(title.waitForExistence(timeout: 15)); title.coordinate(withNormalizedOffset: CGVector(dx: 0.95, dy: 0.5)).tap()
        let count = (title.value as? String)?.count ?? 0
        title.typeText(String(repeating: XCUIKeyboardKey.delete.rawValue, count: count) + "关怀模式草稿校对")
        tap(app.buttons["draft.keepEdits"], app: app)
        tap(app.buttons["memory.save"], app: app)
        XCTAssertTrue(app.staticTexts["care.saved.title"].waitForExistence(timeout: 20))
        XCTAssertEqual(app.staticTexts["care.saved.title"].label, "关怀模式草稿校对")
        shot("care-saved", app)
        tap(app.buttons["care.saved.read"], app: app)
        XCTAssertTrue(app.staticTexts["care.story.body"].waitForExistence(timeout: 10))
        XCTAssertTrue(app.staticTexts["care.story.body"].label.contains("老师"))
        shot("care-saved-reading", app)
        tap(app.buttons["care.back"], app: app)
        tap(app.buttons["care.saved.home"], app: app)
        tap(app.buttons["care.tab.profile"], app: app)
        tap(app.buttons["care.switchStandard"], app: app)
        tap(app.alerts.buttons["继续使用关怀模式"], app: app)
        XCTAssertTrue(app.buttons["care.tab.home"].exists)
        tap(app.buttons["care.switchStandard"], app: app)
        tap(app.alerts.buttons["切换普通模式"], app: app)
        XCTAssertTrue(app.buttons["tab.compose"].waitForExistence(timeout: 15))
        shot("standard-mode-restored", app)
    }
    @MainActor func testCareOverviewAndHistorySupportLargestTextInPortrait() {
        let first = enableCare(); first.terminate()
        let app = launch("care-life-review", large: true)
        XCTAssertTrue(app.buttons["life.confirm"].waitForExistence(timeout: 25))
        shot("care-largest-text-review", app)
        tap(app.buttons["care.life.more"], app: app)
        tap(app.buttons["查看刚才问答"], app: app)
        tap(app.buttons["care.history.next"], app: app)
        XCTAssertTrue(app.buttons["care.history.next"].isHittable)
        shot("care-largest-text-history-portrait", app)
    }
    @MainActor func testLargestTextNarrationKeepsInputAndSendReachable() {
        let first = enableCare(); first.terminate()
        let app = launch("care-life-question", large: true)
        tap(app.buttons["life.input.keyboard"], app: app)
        let input = app.textFields["life.input"]
        XCTAssertTrue(input.waitForExistence(timeout: 15)); input.tap(); input.typeText("小时候我住在乡下。")
        tap(app.buttons["life.input.dismissKeyboard"], app: app)
        tap(app.buttons["life.send"], app: app)
        XCTAssertTrue(app.buttons["life.input.keyboard"].waitForExistence(timeout: 15))
        shot("care-largest-text-narration", app)
    }
    @MainActor func testDeniedVoicePermissionRetainsKeyboardFallback() throws {
        #if CARE_PERMISSION_VALIDATION
        let first = enableCare(); first.terminate()
        let app = launch("care-life-question")
        tap(app.buttons["life.dictation"], app: app)
        let system = XCUIApplication(bundleIdentifier: "com.apple.springboard")
        if system.alerts.firstMatch.waitForExistence(timeout: 4) {
            let deny = system.alerts.buttons.matching(NSPredicate(format: "label IN %@", ["不允许", "Don't Allow", "不允許"])).firstMatch
            XCTAssertTrue(deny.exists); deny.tap()
        }
        XCTAssertTrue(app.alerts["语音输入"].waitForExistence(timeout: 15))
        shot("care-voice-denied", app)
        tap(app.alerts.buttons["确定"], app: app)
        tap(app.buttons["life.input.keyboard"], app: app)
        let input = app.textFields["life.input"]; input.tap(); input.typeText("语音不可用时，我也可以打字讲述。")
        tap(app.buttons["life.input.dismissKeyboard"], app: app)
        tap(app.buttons["life.send"], app: app)
        XCTAssertTrue(app.buttons["life.input.keyboard"].waitForExistence(timeout: 15))
        shot("care-voice-keyboard-fallback", app)
        #else
        throw XCTSkip("Requires microphone denied for the isolated validation bundle")
        #endif
    }
    @MainActor func testCloudCareInterviewSaveAndReloadInIsolatedFamily() throws {
        #if CARE_CLOUD_VALIDATION
        let cloudEnabled = true
        #else
        let cloudEnabled = false
        #endif
        guard cloudEnabled else { throw XCTSkip("Only the isolated care candidate") }
        let first = enableCare(); first.terminate()
        let app = launch(cloud: true)
        if app.buttons["care.tab.profile"].waitForExistence(timeout: 4) {
            tap(app.buttons["care.tab.profile"], app: app); tap(app.buttons["设置与账号"], app: app)
            tap(app.buttons["settings.logout"], app: app)
        }
        tap(app.buttons["login.register"], app: app)
        let username = "care_ui_" + UUID().uuidString.replacingOccurrences(of: "-", with: "").prefix(12)
        let password = UUID().uuidString
        app.textFields["register.username"].tap(); app.textFields["register.username"].typeText(String(username))
        tap(app.buttons["register.password.visibility"], app: app)
        app.textFields["register.password"].tap(); app.textFields["register.password"].typeText(password)
        tap(app.buttons["register.confirmation.visibility"], app: app)
        app.textFields["register.confirmation"].tap(); app.textFields["register.confirmation"].typeText(password)
        tap(app.buttons["register.password.visibility"], app: app)
        tap(app.buttons["register.confirmation.visibility"], app: app)
        tap(app.buttons["register.submit"], app: app)
        tap(app.buttons["home.newMemory"], app: app, timeout: 45)
        if !app.textFields["member.realName"].waitForExistence(timeout: 3) { tap(app.buttons["members.addAnother"], app: app) }
        app.textFields["member.relationship"].tap(); app.textFields["member.relationship"].typeText("爷爷")
        app.textFields["member.realName"].tap(); app.textFields["member.realName"].typeText("关怀验证林师傅\n")
        tap(app.buttons["member.birthday"], app: app); tap(app.buttons["member.confirmBirthday"], app: app)
        tap(app.buttons["member.add"], app: app)
        if app.buttons["life.begin"].waitForExistence(timeout: 4) { tap(app.buttons["life.begin"], app: app) }
        let overviewAnswer = "我小时候在青溪村长大。我没有上过学，跟舅舅学修木门。年轻时帮邻居修门，后来自己开了个修理铺。姐姐叫阿秀，我们一起生活了好多年。我一直记得的一次变化是修理铺搬到了街口。如今我每天在家种菜，偶尔修修小东西。"
        for index in 0..<8 {
            if app.buttons["life.confirm"].exists { break }
            tap(app.buttons["life.input.keyboard"], app: app, timeout: 120)
            let input = app.textFields["life.input"]; input.tap(); input.typeText(index == 0 ? overviewAnswer : "跳过")
            tap(app.buttons["life.send"], app: app)
            let ready = NSPredicate { _, _ in app.buttons["life.confirm"].exists || (app.buttons["life.input.keyboard"].exists && app.buttons["life.input.keyboard"].isEnabled) }
            XCTAssertEqual(XCTWaiter.wait(for: [XCTNSPredicateExpectation(predicate: ready, object: nil)], timeout: 150), .completed)
        }
        tap(app.buttons["life.confirm"], app: app); tap(app.buttons["life.module.work"], app: app, timeout: 90)
        shot("care-cloud-work-question", app)
        tap(app.buttons["chat.input.keyboard"], app: app, timeout: 90)
        let input = app.textFields["chat.input"]; input.tap()
        input.typeText("我最初跟舅舅做木活。他让我给邻居修门，我拿工具去了邻居家，先卸下门扇，刨掉卡住的一点，再装回去试开关。邻居试了几遍，说终于不挤手了。那是我头一次独自把活干好，心里很踏实。这件事已经讲完了，请整理成回忆草稿。")
        tap(app.buttons["chat.send"], app: app)
        let draftReady = NSPredicate { _, _ in app.buttons["memory.save"].exists || app.buttons["chat.generate"].exists }
        XCTAssertEqual(XCTWaiter.wait(for: [XCTNSPredicateExpectation(predicate: draftReady, object: nil)], timeout: 180), .completed)
        if app.buttons["chat.generate"].exists { tap(app.buttons["chat.generate"], app: app) }
        tap(app.buttons["memory.save"], app: app, timeout: 120)
        XCTAssertTrue(app.staticTexts["care.saved.title"].waitForExistence(timeout: 90))
        let title = app.staticTexts["care.saved.title"].label
        shot("care-cloud-saved", app)
        tap(app.buttons["care.saved.read"], app: app)
        XCTAssertTrue(app.staticTexts["care.story.body"].label.contains("门")); shot("care-cloud-reading", app)
        tap(app.buttons["care.back"], app: app); tap(app.buttons["care.saved.home"], app: app)
        app.terminate(); app.launch()
        XCTAssertTrue(app.buttons["care.tab.home"].waitForExistence(timeout: 45))
        XCTAssertTrue(app.staticTexts[title].waitForExistence(timeout: 45) || app.buttons.matching(NSPredicate(format: "label CONTAINS %@", title)).firstMatch.exists)
        shot("care-cloud-reloaded-home", app)
    }
}
