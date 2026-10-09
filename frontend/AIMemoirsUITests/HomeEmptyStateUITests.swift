import XCTest

final class HomeEmptyStateUITests: XCTestCase {
    @MainActor func testFirstUseOrphanedMemoriesAndPeopleWithoutStories() {
        continueAfterFailure = false
        for screen in ["home-empty", "home-orphaned", "home-people-only"] {
            let app = XCUIApplication()
            app.launchEnvironment["AI_MEMORIES_DESIGN_SCREEN"] = screen
            app.launch()
            let title = screen == "home-people-only" ? "第一段回忆，慢慢说" : "把想念的人，写进第一页"
            XCTAssertTrue(app.staticTexts[title].waitForExistence(timeout: 10))
            XCTAssertFalse(app.buttons["home.featured"].exists)
            let attachment = XCTAttachment(screenshot: app.screenshot())
            attachment.name = screen; attachment.lifetime = .keepAlways; add(attachment)
            app.buttons["home.newMemory"].tap()
            XCTAssertTrue(app.staticTexts[screen == "home-people-only" ? "今天，想起了谁？" : "先认识一位家人"].waitForExistence(timeout: 5))
            app.buttons["tab.profile"].tap()
            let count = app.otherElements["profile.stat.珍藏回忆"]
            XCTAssertTrue(count.waitForExistence(timeout: 5))
            XCTAssertEqual(count.value as? String, "0")
            if screen != "home-people-only" {
                app.buttons["tab.family"].tap()
                let add = app.buttons["film.addFirstPerson"]
                XCTAssertTrue(add.waitForExistence(timeout: 5))
                XCTAssertLessThan(add.frame.width, app.frame.width * 0.75)
                let filmShot = XCTAttachment(screenshot: app.screenshot())
                filmShot.name = "family-empty-compact"; filmShot.lifetime = .keepAlways; self.add(filmShot)
                add.tap()
                XCTAssertTrue(app.staticTexts["先认识一位家人"].waitForExistence(timeout: 5))
                app.buttons["tab.profile"].tap()
            }
            app.buttons["我的全部回忆"].tap()
            XCTAssertTrue(app.staticTexts["还没有回忆"].waitForExistence(timeout: 5))
            app.terminate()
        }
    }
}
