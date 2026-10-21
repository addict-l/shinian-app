package cn.shinian.app.data

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class MemoirSettingsTest {
    @Test
    fun legacyDateFormatsForReadingAndBecomesKnownWhenEditing() {
        val legacy = story("first", "1952-09-01", "2020-01-01")

        assertEquals("1952年9月1日", legacy.dateLabel)
        assertEquals(InformationDimension("known", "1952-09-01"), MemoryEdit(legacy).time)
        assertEquals("小时候", legacy.copy(time = InformationDimension("approximate", "小时候")).dateLabel)
    }

    @Test
    fun timeOrderingUsesEventTimeAndKeepsUndatedStoriesLast() {
        val newer = story("newer", "2001-01-01", "2020-01-01")
        val earlier = story("earlier", "1950-01-01", "2026-01-01")
        val unknown = story("unknown", null, "1900-01-01", InformationDimension("unknown", "记不清"))
        val approximate = story("approximate", null, "2026-02-01", InformationDimension("approximate", "1960年春天"))

        val ordered = MemoirSettings("回忆录").ordered(listOf(newer, unknown, approximate, earlier))

        assertEquals(listOf("earlier", "approximate", "newer", "unknown"), ordered.map { it.id })
    }

    @Test
    fun equalEventTimesKeepSaveOrderAndLifeStagesAreNotInventedDates() {
        val first = story("first", "1960-01-01", "2020-01-01")
        val second = story("second", "1960-01-01", "2021-01-01")
        val childhood = story("childhood", null, "1900-01-01", InformationDimension("approximate", "小时候"))

        assertEquals(listOf("first", "second", "childhood"),
            MemoirSettings("回忆录").ordered(listOf(second, childhood, first)).map { it.id })
        assertNull(MemoirSettings.timeKey(childhood))
    }

    @Test
    fun manualOrderingDropsRemovedStoriesAndAppendsNewlySavedStories() {
        val first = story("first", null, "2020-01-01")
        val second = story("second", null, "2021-01-01")
        val added = story("added", null, "2022-01-01")

        val settings = MemoirSettings("回忆录", ordering = "manual", storyOrder = listOf("removed", "second", "first"))

        assertEquals(listOf("second", "first", "added"), settings.ordered(listOf(added, first, second)).map { it.id })
    }

    @Test
    fun excludedPhotosStayOutWhileNewPhotosKeepTheirOriginalOrder() {
        val memory = story("first", null, "2020-01-01").copy(media = listOf(
            Media("a", "/api/v1/media/a"), Media("b", "/api/v1/media/b"), Media("c", "/api/v1/media/c")))
        val settings = MemoirSettings("回忆录", photoOrders = mapOf("first" to listOf("b", "a")), excludedPhotoIds = listOf("a"))

        assertEquals(listOf("b", "c"), settings.selectedPhotos(memory).map { it.id })
    }

    private fun story(id: String, date: String?, createdAt: String, time: InformationDimension = InformationDimension()) =
        Memory(id, "回忆", "正文", memoryDate = date, createdAt = createdAt, time = time)
}
