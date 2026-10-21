package cn.shinian.app.data

import org.junit.Assert.assertEquals
import org.junit.Assert.assertThrows
import org.junit.Test

class TimePreviewTest {
    @Test
    fun appliesSelectedUtf16RangesFromRightToLeftAfterEmoji() {
        val input = TimePreviewInput("旧时光", "🙂1960年第一次出门，1970年回到家。",
            InformationDimension("known", "1960-01-01"), InformationDimension("known", "1961-01-01"))
        val first = TimeSuggestion("a", "summary", 2, 5, "1960年", "1961年春天", "", false, "日期更新")
        val secondStart = input.content.indexOf("1970年")
        val second = TimeSuggestion("b", "summary", secondStart, 5, "1970年", "1971年", "", false, "日期更新")

        val result = TimePreview("snapshot", listOf(first, second), "").applying(setOf("a", "b"), input)

        assertEquals("旧时光", result.first)
        assertEquals("🙂1961年春天第一次出门，1971年回到家。", result.second)
    }

    @Test
    fun changedTextAndOverlappingSuggestionsAreRejected() {
        val input = TimePreviewInput("1960年", "正文", InformationDimension(), InformationDimension())
        val original = TimeSuggestion("a", "title", 0, 5, "1960年", "1961年", "", false, "")
        assertThrows(AuthException::class.java) {
            TimePreview("snapshot", listOf(original), "").applying(setOf("a"), input.copy(title = "1970年"))
        }
        assertThrows(AuthException::class.java) {
            TimePreview("snapshot", listOf(original, original.copy(id = "b")), "").applying(setOf("a", "b"), input)
        }
    }

    @Test
    fun suggestionCannotSplitAnEmojiSurrogatePair() {
        val input = TimePreviewInput("🙂回忆", "正文", InformationDimension(), InformationDimension())
        val invalid = TimeSuggestion("a", "title", 1, 1, input.title.substring(1, 2), "x", "", false, "")

        assertThrows(AuthException::class.java) {
            TimePreview("snapshot", listOf(invalid), "").applying(setOf("a"), input)
        }
    }
}
