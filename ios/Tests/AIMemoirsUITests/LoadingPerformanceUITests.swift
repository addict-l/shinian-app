import XCTest

final class LoadingPerformanceUITests: XCTestCase {
    @MainActor func testDisposableCandidateHomeShowsLazyPhotoAndBrowsing() throws {
        guard ProcessInfo.processInfo.environment["SHINIAN_LOADING_LIVE_UI"] == "1" else { throw XCTSkip("Explicit disposable candidate only") }
        continueAfterFailure = false
        let app = XCUIApplication(bundleIdentifier: "com.shinian.validation.performance")
        app.launchEnvironment["AI_MEMORIES_API_URL"] = "http://127.0.0.1:17655"
        app.launch()
        XCTAssertTrue(app.buttons["home.featured"].waitForExistence(timeout: 60))
        let photo = app.descendants(matching: .any).matching(NSPredicate(format: "identifier BEGINSWITH 'memory.photo.'")).firstMatch
        XCTAssertTrue(photo.waitForExistence(timeout: 30))
        let loaded = XCTNSPredicateExpectation(predicate: NSPredicate(format: "value == '照片已加载'"), object: photo)
        XCTAssertEqual(XCTWaiter.wait(for: [loaded], timeout: 45), .completed)
        let home = XCTAttachment(screenshot: app.screenshot()); home.name = "01-candidate-home-lazy-photo"; home.lifetime = .keepAlways; add(home)
        app.buttons["home.allMemories"].tap()
        XCTAssertTrue(app.buttons.matching(NSPredicate(format: "identifier BEGINSWITH 'memory.card.'")).firstMatch.waitForExistence(timeout: 30))
        let stories = XCTAttachment(screenshot: app.screenshot()); stories.name = "02-candidate-photo-story-list"; stories.lifetime = .keepAlways; add(stories)
        app.buttons["tab.family"].tap()
        XCTAssertTrue(app.descendants(matching: .any).matching(identifier: "film.overview").firstMatch.waitForExistence(timeout: 30))
        let film = XCTAttachment(screenshot: app.screenshot()); film.name = "03-candidate-family-films"; film.lifetime = .keepAlways; add(film)
    }
}
