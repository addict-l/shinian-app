import XCTest

final class BetterUIFlowTests: XCTestCase {
    @MainActor private func launch(_ screen: String? = nil, isolated: Bool = false) -> XCUIApplication {
        continueAfterFailure = false
        XCUIDevice.shared.orientation = .portrait
        let app = XCUIApplication()
        if let screen { app.launchArguments = ["--design-screen", screen] }
        if isolated {
            app.launchEnvironment["AI_MEMORIES_API_URL"] = "http://localhost:17655"
        } else {
            app.launchEnvironment["AI_MEMORIES_API_URL"] = "https://aimemory.47-82-83-74.nip.io"
        }
        app.launchArguments += ["-journal.careMode.enabled", "NO"]
        app.launch()
        return app
    }
    @MainActor private func tap(_ element: XCUIElement, timeout: TimeInterval = 15) {
        XCTAssertTrue(element.waitForExistence(timeout: timeout))
        element.tap()
    }
    @MainActor private func scrollTo(_ element: XCUIElement, app: XCUIApplication) {
        for _ in 0..<5 {
            if element.exists && element.isHittable { return }
            app.swipeUp()
        }
        XCTAssertTrue(element.exists && element.isHittable)
    }
    @MainActor private func replace(_ field: XCUIElement, with value: String) {
        field.tap()
        field.press(forDuration: 1.2)
        let app = XCUIApplication()
        if app.menuItems["全选"].exists { app.menuItems["全选"].tap(); field.typeText(value) }
        else {
            let count = (field.value as? String)?.count ?? 0
            field.typeText(String(repeating: XCUIKeyboardKey.delete.rawValue, count: count) + value)
        }
    }
    @MainActor private func screenshot(_ name: String, app: XCUIApplication) {
        let item = XCTAttachment(screenshot: app.screenshot()); item.name = name; item.lifetime = .keepAlways; add(item)
    }
    @MainActor func testCloudFamilyLoadsWithNormalLaunchAndAllTabsReachable() throws {
        let app = launch()
        tap(app.buttons["tab.profile"], timeout: 30)
        let stat = app.descendants(matching: .any).matching(identifier: "profile.stat.家庭人物").firstMatch
        XCTAssertTrue(stat.waitForExistence(timeout: 30))
        let loaded = NSPredicate(format: "label MATCHES '.*[0-9]+.*'")
        expectation(for: loaded, evaluatedWith: stat)
        waitForExpectations(timeout: 30)
        screenshot("cloud-profile", app: app)
        tap(app.buttons["tab.family"])
        let person = app.buttons.matching(NSPredicate(format: "identifier BEGINSWITH 'film.person.'")).firstMatch
        tap(person, timeout: 30)
        XCTAssertTrue(app.staticTexts["人物资料"].waitForExistence(timeout: 10))
        screenshot("cloud-person", app: app)
        if app.buttons["person-memoir"].isEnabled {
            tap(app.buttons["person-memoir"])
            XCTAssertTrue(app.staticTexts["memoir-sync-status"].waitForExistence(timeout: 20))
            screenshot("cloud-memoir-settings", app: app)
            tap(app.buttons["关闭回忆录"])
        }
        tap(app.buttons["tab.profile"])
        tap(app.buttons["设置"])
        XCTAssertTrue(app.buttons["退出家庭登录"].waitForExistence(timeout: 10))
        tap(app.buttons["返回"])
        tap(app.buttons["隐私与数据"])
        XCTAssertTrue(app.staticTexts["隐私与数据"].waitForExistence(timeout: 10))
        tap(app.buttons["返回"])
        tap(app.buttons["我的全部回忆"])
        XCTAssertTrue(app.staticTexts["所有回忆"].waitForExistence(timeout: 15))
        screenshot("cloud-all-memories", app: app)
    }
    @MainActor func testPreviewStoryEditingAndDeletionRefreshSharedCollection() {
        let app = launch("story")
        tap(app.buttons["memory.actions"])
        tap(app.buttons["编辑回忆"])
        let title = app.textFields["memory.editTitle"]
        XCTAssertTrue(title.waitForExistence(timeout: 15))
        replace(title, with: "温馨版编辑验证")
        tap(app.buttons["memory.saveEdits"])
        XCTAssertTrue(app.staticTexts["温馨版编辑验证"].waitForExistence(timeout: 15))
        tap(app.buttons["memory.actions"])
        tap(app.buttons["删除整段回忆"])
        tap(app.alerts.buttons["确认删除整段"])
        tap(app.buttons["tab.profile"])
        let count = app.descendants(matching: .any).matching(identifier: "profile.stat.珍藏回忆").firstMatch
        XCTAssertTrue(count.label.contains("17"))
        screenshot("preview-shared-count-after-deletion", app: app)
    }
    @MainActor func testCoverCropAndCollageCanBeAdjustedWithoutBlockingPageScroll() {
        let app = launch("memoir")
        tap(app.buttons["memoir-edit-style"]); tap(app.buttons["memoir.template.photo"]); tap(app.buttons["完成"])
        tap(app.buttons["memoir-cover-photos"])
        let photos = app.buttons.matching(NSPredicate(format: "identifier BEGINSWITH 'memoir.coverPhoto.'"))
        scrollTo(photos.firstMatch, app: app); tap(photos.firstMatch)
        screenshot("preview-memoir-cover-grouped", app: app)
        tap(app.buttons["memoir-cover-photos"])
        let crop = app.buttons["memoir-cover-crop"]
        scrollTo(crop, app: app); tap(crop)
        XCTAssertTrue(app.descendants(matching: .any)["memoir-crop-preview"].waitForExistence(timeout: 10))
        let zoom = app.sliders["缩放"]
        XCTAssertTrue(zoom.exists); zoom.adjust(toNormalizedSliderPosition: 0.45)
        tap(app.buttons["memoir-crop-done"])
        tap(app.buttons["完成"])
        tap(app.buttons["memoir-edit-style"])
        let collage = app.buttons["memoir.template.collage"]
        scrollTo(collage, app: app); tap(collage)
        tap(app.buttons["完成"])
        let picker = app.buttons["memoir-cover-photos"]
        scrollTo(picker, app: app); tap(picker)
        scrollTo(photos.firstMatch, app: app)
        photos.firstMatch.tap()
        tap(app.buttons["完成"])
        let next = app.buttons["memoir-next"]
        scrollTo(next, app: app); tap(next)
        tap(app.buttons["memoir-generate"])
        XCTAssertTrue(app.buttons["memoir-share"].waitForExistence(timeout: 30))
        screenshot("preview-memoir-pdf", app: app)
        tap(app.buttons["memoir-share"])
        XCTAssertTrue(app.buttons["关闭"].waitForExistence(timeout: 15) || app.buttons["Close"].exists)
    }
    @MainActor func testRealBackendAddChatSaveMemoirAndDeleteOnIsolatedDatabase() throws {
        guard ProcessInfo.processInfo.environment["BETTERUI_ISOLATED_TEST"] == "1" else { throw XCTSkip("Disposable API only") }
        let app = launch(isolated: true)
        let name = "联调人物" + String(UUID().uuidString.prefix(6))
        tap(app.buttons["tab.compose"], timeout: 30)
        tap(app.buttons["members.addAnother"])
        tap(app.buttons["爷爷"])
        tap(app.textFields["member.realName"])
        app.textFields["member.realName"].typeText(name)
        tap(app.buttons["member.birthday"])
        tap(app.buttons["member.confirmBirthday"])
        tap(app.buttons["member.add"])
        let member = app.descendants(matching: .any).matching(identifier: "members.card." + name).firstMatch
        tap(member, timeout: 120)
        let input = app.descendants(matching: .any).matching(identifier: "chat.input").firstMatch
        XCTAssertTrue(input.waitForExistence(timeout: 30))
        tap(app.buttons["chat.addPhotos"])
        if app.images["PickerOnboardingHeaderViewIcon"].waitForExistence(timeout: 2) {
            let close = app.buttons["关闭"].firstMatch
            if close.exists && close.isHittable { close.tap() }
        }
        let cells = app.images.matching(identifier: "PXGGridLayout-Info")
        XCTAssertTrue(cells.firstMatch.waitForExistence(timeout: 30))
        cells.firstMatch.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.5)).tap()
        let confirm = app.navigationBars.buttons.matching(NSPredicate(format: "label BEGINSWITH '添加' OR label == '完成' OR label == 'Done' OR label BEGINSWITH 'Add'")).firstMatch
        tap(confirm)
        input.tap()
        input.typeText("2010年5月1日，我在家门口的小广场教孙子骑自行车。我扶着车后座，告诉他看前方。他终于学会了，我觉得很开心。这是虚构联调故事，已经讲完，请整理成回忆草稿。")
        tap(app.buttons["chat.send"])
        let generate = app.buttons["chat.generate"]
        tap(generate, timeout: 120)
        tap(app.buttons["保存这段回忆"], timeout: 120)
        XCTAssertTrue(input.waitForExistence(timeout: 120))
        screenshot("isolated-real-chat-saved", app: app)
        tap(app.buttons["newMemory.step.1"])
        tap(app.buttons["tab.family"])
        let person = app.buttons["film.person." + name]
        scrollTo(person, app: app); tap(person)
        tap(app.buttons["person-memoir"])
        let next = app.buttons["memoir-next"]
        scrollTo(next, app: app); tap(next)
        tap(app.buttons["生成整本预览"])
        XCTAssertTrue(app.buttons["memoir-share"].waitForExistence(timeout: 60))
        screenshot("isolated-real-memoir-pdf", app: app)
        tap(app.buttons["关闭回忆录"])
        tap(app.buttons["tab.profile"])
        tap(app.buttons["我的全部回忆"])
        let card = app.buttons.matching(NSPredicate(format: "identifier BEGINSWITH 'memory.card.'")).firstMatch
        tap(card)
        tap(app.buttons["memory.actions"])
        tap(app.buttons["编辑回忆"])
        let title = app.textFields["memory.editTitle"]
        XCTAssertTrue(title.waitForExistence(timeout: 15))
        replace(title, with: "真实服务界面保存验证")
        tap(app.buttons["memory.saveEdits"])
        XCTAssertTrue(app.staticTexts["真实服务界面保存验证"].waitForExistence(timeout: 30))
        screenshot("isolated-real-story-edited", app: app)
        tap(app.buttons["memory.actions"])
        tap(app.buttons["删除整段回忆"])
        tap(app.alerts.buttons["确认删除整段"])
        XCTAssertTrue(app.staticTexts["还没有回忆"].waitForExistence(timeout: 30))
        screenshot("isolated-real-story-deleted", app: app)
    }
}
