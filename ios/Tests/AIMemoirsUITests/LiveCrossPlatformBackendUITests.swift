import XCTest

/// Read-only business navigation; the hosted test stages a real device login.
final class LiveCrossPlatformBackendUITests: XCTestCase {
    private let appID = "com.shinian.validation.crossplatform"

    @MainActor private func tap(_ item: XCUIElement, timeout: TimeInterval = 30) {
        XCTAssertTrue(item.waitForExistence(timeout: timeout))
        XCTAssertTrue(item.isHittable)
        item.tap()
    }
    @MainActor private func shot(_ name: String, app: XCUIApplication) {
        let attachment = XCTAttachment(screenshot: app.screenshot())
        attachment.name = name; attachment.lifetime = .keepAlways; add(attachment)
    }
    @MainActor private func scrollTo(_ item: XCUIElement, app: XCUIApplication) {
        for _ in 0..<7 {
            if item.exists && item.isHittable { return }
            if app.scrollViews.firstMatch.exists { app.scrollViews.firstMatch.swipeUp() }
            else { app.swipeUp() }
        }
    }

    @MainActor func testNormalRestorePersonStoriesPhotosAndMemoirFromRealBackend() throws {
        guard ProcessInfo.processInfo.environment["SHINIAN_CROSSPLATFORM_READONLY_UI"] == "1" else {
            throw XCTSkip("Explicit separate live verification project only")
        }
        continueAfterFailure = false
        XCUIDevice.shared.orientation = .portrait
        let app = XCUIApplication(bundleIdentifier: appID)
        app.launchEnvironment["AI_MEMORIES_API_URL"] = "https://aimemory.47-82-83-74.nip.io"
        app.launchEnvironment["AI_MEMORIES_DESIGN_SCREEN"] = nil
        app.launch()
        tap(app.buttons["tab.profile"], timeout: 60)
        let people = app.descendants(matching: .any).matching(identifier: "profile.stat.家庭人物").firstMatch
        let stories = app.descendants(matching: .any).matching(identifier: "profile.stat.珍藏回忆").firstMatch
        XCTAssertTrue(people.waitForExistence(timeout: 30))
        XCTAssertTrue(stories.waitForExistence(timeout: 30))
        let loaded = NSPredicate { _, _ in people.label.contains("1") && stories.label.contains("3") }
        XCTAssertEqual(XCTWaiter.wait(for: [XCTNSPredicateExpectation(predicate: loaded, object: nil)], timeout: 45), .completed)
        shot("01-real-family-profile", app: app)

        tap(app.buttons["我的全部回忆"])
        let cards = app.buttons.matching(NSPredicate(format: "identifier BEGINSWITH 'memory.card.'"))
        XCTAssertTrue(cards.firstMatch.waitForExistence(timeout: 45))
        shot("02-real-three-stories", app: app)
        tap(cards.firstMatch)
        XCTAssertTrue(app.buttons["memory.actions"].waitForExistence(timeout: 30))
        shot("03-real-story-and-photo", app: app)
        tap(app.buttons["返回"])
        tap(app.buttons["返回"])

        tap(app.buttons["tab.family"])
        let person = app.buttons["film.person.林秋禾"]
        scrollTo(person, app: app); tap(person)
        XCTAssertTrue(app.staticTexts["人物资料"].waitForExistence(timeout: 30))
        shot("04-real-person", app: app)
        tap(app.buttons["person-memoir"])
        let status = app.staticTexts["memoir-sync-status"]
        XCTAssertTrue(status.waitForExistence(timeout: 45))
        let synced = NSPredicate { _, _ in status.label.contains("已保存") }
        XCTAssertEqual(XCTWaiter.wait(for: [XCTNSPredicateExpectation(predicate: synced, object: nil)], timeout: 45), .completed)
        XCTAssertFalse(app.staticTexts["memoir-error"].exists)
        shot("05-real-memoir-cover", app: app)
        let next = app.buttons["memoir-next"]
        scrollTo(next, app: app); tap(next)
        let chapters = app.descendants(matching: .any).matching(NSPredicate(format: "identifier BEGINSWITH 'memoir.chapter.'"))
        XCTAssertTrue(chapters.firstMatch.waitForExistence(timeout: 30))
        shot("06-real-memoir-chapters", app: app)
        tap(app.buttons["关闭回忆录"])
        app.terminate(); app.launch()
        tap(app.buttons["tab.profile"], timeout: 60)
        let reloadedPeople = app.descendants(matching: .any).matching(identifier: "profile.stat.家庭人物").firstMatch
        let reloadedStories = app.descendants(matching: .any).matching(identifier: "profile.stat.珍藏回忆").firstMatch
        XCTAssertTrue(reloadedPeople.waitForExistence(timeout: 45))
        XCTAssertTrue(reloadedStories.waitForExistence(timeout: 45))
        let reloaded = NSPredicate { _, _ in reloadedPeople.label.contains("1") && reloadedStories.label.contains("3") }
        XCTAssertEqual(XCTWaiter.wait(for: [XCTNSPredicateExpectation(predicate: reloaded, object: nil)], timeout: 45), .completed)
        shot("07-real-session-restored-again", app: app)
    }
}
