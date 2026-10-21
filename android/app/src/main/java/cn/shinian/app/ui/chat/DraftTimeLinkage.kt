package cn.shinian.app.ui.chat

import kotlinx.serialization.json.JsonObject

/** Server ranges are UTF-16 offsets, just like Kotlin String indices and Swift NSString ranges. */
internal fun applyDraftTime(captured: DraftEdits, preview: JsonObject, selected: Set<String>): DraftEdits {
    fun apply(field: String, source: String): String {
        var result = source
        var boundary = source.length
        val suggestions = preview.objects("suggestions")
            .filter { it.text("field") == field && it.text("id") in selected }
            .sortedByDescending { it.number("start") }
        for (item in suggestions) {
            val start = item.number("start", -1)
            val length = item.number("length")
            val after = item.text("after") ?: throw IllegalArgumentException("文字已变化，请重新核对时间。")
            require(start >= 0 && length > 0 && start <= boundary && length <= boundary - start) { "文字已变化，请重新核对时间。" }
            val end = start + length
            require(source.substring(start, end) == item.text("before")) { "文字已变化，请重新核对时间。" }
            require(!(start > 0 && start < source.length && source[start].isLowSurrogate() && source[start - 1].isHighSurrogate())) { "文字已变化，请重新核对时间。" }
            require(!(end > 0 && end < source.length && source[end].isLowSurrogate() && source[end - 1].isHighSurrogate())) { "文字已变化，请重新核对时间。" }
            result = result.replaceRange(start, end, after)
            boundary = start
        }
        return result
    }
    val title = apply("title", captured.title)
    val content = apply("summary", captured.content)
    require(title.length <= 200 && content.length <= 100_000) { "修改后文字过长，请减少内容再应用。" }
    return captured.copy(title = title, content = content, anchor = captured.time)
}
