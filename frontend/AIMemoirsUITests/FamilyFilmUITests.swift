import XCTest

final class FamilyFilmUITests: XCTestCase {
    @MainActor func testPersonalRollsAndAllFamilyDirectory() {
        continueAfterFailure = false
        let app = XCUIApplication()
        app.launchEnvironment["AI_MEMORIES_DESIGN_SCREEN"] = "film"
        app.launch()
        XCTAssertTrue(app.buttons["film.allFamily"].waitForExistence(timeout: 10))
        XCTAssertFalse(app.staticTexts["未标注人物"].exists)
        XCTAssertEqual(app.staticTexts["film.count.陈建国"].label, "3 段回忆")
        let roll = app.scrollViews["film.roll.陈建国"]
        XCTAssertTrue(roll.exists)
        attach(app, "family-rolls-overview")
        roll.swipeLeft()
        let sharedID = "film.frame.00000000-0000-0000-0000-000000000001."
        let shared = app.buttons.matching(NSPredicate(format: "identifier BEGINSWITH %@ AND label CONTAINS %@", sharedID, "一起回老家过年")).firstMatch
        XCTAssertTrue(shared.waitForExistence(timeout: 5))
        shared.tap()
        XCTAssertTrue(app.staticTexts["一起回老家过年"].waitForExistence(timeout: 5))
        app.buttons["tab.home"].tap()
        app.buttons["tab.family"].tap()
        app.buttons["film.allFamily"].tap()
        let search = app.textFields["搜索家人的姓名或身份"]
        XCTAssertTrue(search.waitForExistence(timeout: 5))
        search.tap()
        search.typeText("奶奶")
        XCTAssertTrue(app.buttons["film.person.林秀兰"].waitForExistence(timeout: 5))
        XCTAssertFalse(app.buttons["film.person.陈建国"].exists)
        XCTAssertEqual(app.staticTexts["film.count.林秀兰"].label, "1 段回忆")
        attach(app, "all-family-search")
        app.buttons["清除搜索"].tap()
        search.typeText("没有这个人")
        XCTAssertTrue(app.staticTexts["没有找到这位家人"].waitForExistence(timeout: 5))
        app.buttons["清除搜索"].tap()
        search.typeText("林秀兰")
        app.buttons["film.person.林秀兰"].tap()
        XCTAssertTrue(app.staticTexts["关于她的回忆"].waitForExistence(timeout: 5))
    }

    @MainActor private func attach(_ app: XCUIApplication, _ name: String) {
        let image = XCTAttachment(screenshot: app.screenshot())
        image.name = name
        image.lifetime = .keepAlways
        add(image)
    }
}
