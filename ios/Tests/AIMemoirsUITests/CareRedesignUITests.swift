import XCTest

/// Every launch uses the offline design API; these tests never create or change
/// a person, conversation, or memory on a family server.
final class CareRedesignUITests: XCTestCase {
    @MainActor private func launch(_ screen: String, large: Bool = false) -> XCUIApplication {
        continueAfterFailure = false
        XCUIDevice.shared.orientation = .portrait
        let app = XCUIApplication()
        app.launchArguments = ["--design-screen", screen, "-journal.careMode.enabled", "YES"]
        if large {
            app.launchArguments += ["-UIPreferredContentSizeCategoryName", "UICTContentSizeCategoryAccessibilityXXXL"]
        }
        app.launch()
        return app
    }

    @MainActor private func wait(_ timeout: Double = 15, _ condition: @escaping () -> Bool) {
        let item = XCTNSPredicateExpectation(predicate: NSPredicate { _, _ in condition() }, object: nil)
        XCTAssertEqual(XCTWaiter.wait(for: [item], timeout: timeout), .completed)
    }

    @MainActor private func scrollContainer(_ app: XCUIApplication) -> XCUIElement {
        // Full-screen sheets retain the underlying chat in the accessibility
        // tree. Scroll the foreground care page instead of that hidden history.
        for id in ["care.reading.scroll", "care.saved.scroll", "care.draft.scroll"] {
            let scroll = app.scrollViews[id]
            if scroll.exists && scroll.isHittable { return scroll }
        }
        return app.scrollViews.allElementsBoundByIndex
            .filter { $0.isHittable && $0.frame.width > app.frame.width * 0.6 && $0.frame.height > 80 }
            .max { $0.frame.width * $0.frame.height < $1.frame.width * $1.frame.height }
            ?? app
    }

    @MainActor private func reveal(_ element: XCUIElement, app: XCUIApplication, timeout: Double = 15) {
        XCTAssertTrue(element.waitForExistence(timeout: timeout), element.debugDescription)
        for _ in 0..<20 {
            let scroll = scrollContainer(app)
            if !["care.reading.scroll", "care.saved.scroll", "care.draft.scroll"].contains(scroll.identifier) {
                if element.isHittable { return }
                // Native scroll gestures choose a point inside the scrollable
                // content, clear of the fixed action dock in overview pages.
                if element.frame.maxY > 0 && element.frame.midY < scroll.frame.minY + 8 {
                    scroll.swipeDown()
                } else {
                    scroll.swipeUp()
                }
                continue
            }
            let descendants = scroll.descendants(matching: element.elementType)
            let belongsToScroll = element.identifier.isEmpty
                ? descendants.matching(NSPredicate(format: "label == %@", element.label)).firstMatch.exists
                : descendants.matching(identifier: element.identifier).firstMatch.exists
            // Bottom tabs and fixed toolbars cannot move with this scroll view.
            if element.isHittable && !belongsToScroll { return }
            let frame = element.frame
            let viewport = scroll.frame.intersection(app.frame).insetBy(dx: 0, dy: 12)
            if element.isHittable && (frame.height > viewport.height || viewport.contains(frame)) { return }
            let delta: CGFloat
            if frame.maxY > viewport.maxY { delta = frame.maxY - viewport.maxY }
            else { delta = frame.minY - viewport.minY }
            let distance = min(max(abs(delta), 24), viewport.height * 0.5)
            // Keep the gesture away from the system home indicator and edges.
            let startY = viewport.minY + viewport.height * (delta > 0 ? 0.75 : 0.25)
            let endY = startY + (delta > 0 ? -distance : distance)
            let origin = app.coordinate(withNormalizedOffset: .zero)
            let start = origin.withOffset(CGVector(dx: viewport.midX, dy: startY))
            let end = origin.withOffset(CGVector(dx: viewport.midX, dy: endY))
            start.press(forDuration: 0.1, thenDragTo: end, withVelocity: XCUIGestureVelocity(rawValue: 200), thenHoldForDuration: 0.25)
            if element.isHittable && element.frame.height <= viewport.height && viewport.contains(element.frame) {
                return
            }
        }
        XCTFail("Could not reveal element within the visible scroll viewport: \(element.debugDescription)")
    }

    @MainActor private func tap(_ element: XCUIElement, app: XCUIApplication) {
        reveal(element, app: app)
        XCTAssertTrue(element.isEnabled, element.debugDescription)
        element.tap()
    }

    @MainActor private func shot(_ name: String, _ app: XCUIApplication) {
        let item = XCTAttachment(screenshot: app.screenshot())
        item.name = "care-redesign-" + name
        item.lifetime = .keepAlways
        add(item)
    }

    @MainActor func testInteractivePreviewCanSwitchBackAndRelaunchInStandardMode() {
        continueAfterFailure = false
        XCUIDevice.shared.orientation = .portrait
        let app = XCUIApplication()
        // Interactive review must use writable preferences. A -key YES launch
        // override locks AppStorage reads for the lifetime of that process.
        app.launchArguments = ["--design-screen", "settings"]
        app.launch()
        defer { app.terminate() }
        let mode = app.switches["settings.careMode"]
        XCTAssertTrue(mode.waitForExistence(timeout: 15))
        if mode.value as? String == "0" {
            mode.tap()
            tap(app.buttons["care.tab.profile"], app: app)
        } else {
            app.terminate()
            app.launchArguments = ["--design-screen", "profile"]
            app.launch()
        }
        tap(app.buttons["care.switchStandard"], app: app)
        tap(app.alerts.buttons["继续使用关怀模式"], app: app)
        XCTAssertTrue(app.buttons["care.tab.home"].exists)
        tap(app.buttons["care.switchStandard"], app: app)
        tap(app.alerts.buttons["切换普通模式"], app: app)
        XCTAssertTrue(app.buttons["tab.compose"].waitForExistence(timeout: 8),
                      "Confirming standard mode must immediately update the active UI.")
        XCTAssertFalse(app.buttons["care.tab.home"].exists)
        shot("mode-switch-standard", app)
        app.terminate()
        app.launchArguments = ["--design-screen", "home"]
        app.launch()
        XCTAssertTrue(app.buttons["tab.compose"].waitForExistence(timeout: 10),
                      "The selected standard mode must survive a normal relaunch.")
    }

    @MainActor func testBrowsingFiltersReadingControlsAndAddPersonForm() {
        let app = launch("home")
        defer { app.terminate() }
        tap(app.buttons["care.tab.family"], app: app)
        let search = app.textFields["care.memories.search"]
        XCTAssertTrue(search.waitForExistence(timeout: 20), "Search must be present before any search action.")
        let grandpa = app.buttons["care.memories.filter.00000000-0000-0000-0000-000000000001"]
        tap(grandpa, app: app)
        XCTAssertTrue(grandpa.isSelected)
        tap(search, app: app)
        search.typeText("蒲扇\n")
        XCTAssertTrue(app.staticTexts["没有找到，换一句话或另一位家人试试。"].waitForExistence(timeout: 10),
                      "Searching another person's story must still respect the selected family member.")
        tap(app.buttons["care.memories.filter.all"], app: app)
        XCTAssertTrue(app.buttons["care.memories.filter.all"].isSelected)
        let matchingMemory = app.buttons.matching(NSPredicate(format: "identifier BEGINSWITH %@", "care.memory.")).firstMatch
        XCTAssertTrue(app.staticTexts["葡萄架下的那把蒲扇"].waitForExistence(timeout: 10))
        shot("memory-filter-and-search", app)
        tap(matchingMemory, app: app)
        let story = app.staticTexts["care.story.body"]
        XCTAssertTrue(story.waitForExistence(timeout: 15))
        XCTAssertTrue(story.label.contains("葡萄架"))
        let smaller = app.buttons["care.reading.smaller"]
        XCTAssertTrue(smaller.exists)
        for _ in 0..<6 where smaller.isEnabled { tap(smaller, app: app) }
        XCTAssertFalse(smaller.isEnabled, "Reading controls must reach the minimum through their real storage updates.")
        tap(app.buttons["care.reading.larger"], app: app)
        XCTAssertTrue(smaller.isEnabled)
        reveal(app.buttons["care.reading.speak"], app: app)
        XCTAssertTrue(app.buttons["care.reading.speak"].isEnabled)
        XCTAssertTrue(app.buttons["memory.actions"].exists)
        shot("reading-size-and-speech-controls", app)
        tap(app.buttons["care.back"], app: app)
        tap(app.buttons["care.tab.profile"], app: app)
        XCTAssertTrue(app.staticTexts["我们家的回忆"].waitForExistence(timeout: 10))
        shot("more", app)
        tap(app.buttons["care.tab.home"], app: app)
        tap(app.buttons["home.newMemory"], app: app)
        XCTAssertTrue(app.buttons["care.person.00000000-0000-0000-0000-000000000001"].waitForExistence(timeout: 15))
        tap(app.buttons["members.addAnother"], app: app)
        tap(app.buttons["member.relationship.option.外婆"], app: app)
        XCTAssertEqual(app.textFields["member.relationship"].value as? String, "外婆")
        XCTAssertTrue(app.textFields["member.realName"].exists)
        XCTAssertTrue(app.buttons["member.birthday"].exists)
        XCTAssertFalse(app.buttons["member.add"].isEnabled, "Birthday and name are required before adding a family member.")
        shot("add-person-form", app)
    }

    @MainActor func testSkeletonV2QuotesAndGroupsLeadToAllSixTopics() {
        let app = launch("care-life-review-v2")
        defer { app.terminate() }
        XCTAssertTrue(app.buttons["life.confirm"].waitForExistence(timeout: 25))
        if app.buttons["展开出生与家乡"].exists { tap(app.buttons["展开出生与家乡"], app: app) }
        for text in ["我是一九四八年出生的，属鼠。", "湖南湘潭乡下，一个叫石塘的村子。", "记忆中的家乡：暂时跳过"] {
            let quote = app.staticTexts.matching(NSPredicate(format: "label CONTAINS %@", text)).firstMatch
            XCTAssertTrue(quote.waitForExistence(timeout: 10), text)
        }
        shot("v2-birth-quotes", app)
        for title in ["出生与家乡", "小时候的家", "性格与一生"] {
            reveal(app.staticTexts[title], app: app)
        }
        let characterQuote = app.staticTexts.matching(NSPredicate(format: "label CONTAINS %@", "我这人慢热，认准的事会慢慢做到底。")).firstMatch
        XCTAssertTrue(characterQuote.exists)
        shot("v2-three-groups", app)
        tap(app.buttons["life.confirm"], app: app)
        for module in ["childhood", "growth", "work", "family", "later_life", "reflection"] {
            reveal(app.buttons["life.module." + module], app: app)
        }
        XCTAssertTrue(app.buttons["care.life.randomTopic"].exists)
        shot("v2-six-topics", app)
        tap(app.buttons["life.module.work"], app: app)
        XCTAssertTrue(app.buttons["chat.input.keyboard"].waitForExistence(timeout: 15))
    }

    @MainActor func testClearingSkeletonInputAllowsTypingAndSendingAgain() {
        let app = launch("care-life-question")
        defer { app.terminate() }
        // Preview input is intentionally persistent; clear any prior local input
        // before checking the explicit clear-and-retype transition.
        if app.buttons["life.input.clear"].waitForExistence(timeout: 2) {
            tap(app.buttons["life.input.clear"], app: app)
        }
        tap(app.buttons["life.input.keyboard"], app: app)
        let input = app.textFields["life.input"]
        tap(input, app: app)
        input.typeText("这一段准备清空。")
        tap(app.buttons["life.input.dismissKeyboard"], app: app)
        tap(app.buttons["life.input.clear"], app: app)
        XCTAssertTrue(app.buttons["life.input.keyboard"].waitForExistence(timeout: 10))
        XCTAssertFalse(app.textFields["life.input"].exists)
        shot("skeleton-input-cleared", app)
        tap(app.buttons["life.input.keyboard"], app: app)
        tap(input, app: app)
        XCTAssertFalse((input.value as? String ?? "").contains("准备清空"))
        input.typeText("小时候我和父母住在乡下。")
        tap(app.buttons["life.input.dismissKeyboard"], app: app)
        tap(app.buttons["life.send"], app: app)
        let progress = app.descendants(matching: .any).matching(identifier: "life.progress").firstMatch
        wait { progress.exists && progress.label.contains("第 2 个问题") }
        XCTAssertTrue(app.buttons["life.input.keyboard"].exists)
        shot("skeleton-retyped-answer-sent", app)
    }

    @MainActor func testLargestTextDraftAndSavedReadingRemainReachableInPortrait() {
        let app = launch("review", large: true)
        defer { app.terminate() }
        reveal(app.buttons["care.draft.edit"], app: app, timeout: 25)
        reveal(app.buttons["重新整理"], app: app)
        shot("largest-draft-portrait-actions", app)
        tap(app.buttons["memory.save"], app: app)
        XCTAssertTrue(app.staticTexts["care.saved.title"].waitForExistence(timeout: 20))
        shot("largest-portrait-saved", app)
        tap(app.buttons["care.saved.read"], app: app)
        let readingBody = app.staticTexts["care.story.body"]
        XCTAssertTrue(readingBody.waitForExistence(timeout: 15))
        XCTAssertGreaterThan(readingBody.label.count, 20)
        reveal(app.buttons["care.reading.speak"], app: app)
        shot("largest-portrait-saved-reading", app)
    }
}
