package cn.shinian.app.ui.chat

import android.content.Context
import android.content.Intent
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.speech.RecognitionListener
import android.speech.RecognizerIntent
import android.speech.SpeechRecognizer
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue

/** System Mandarin recognition; partial text is editable and is never sent automatically. */
internal class MandarinDictation(private val context: Context, private val onText: (String) -> Unit) {
    enum class Phase { Idle, Preparing, Recording, Finishing }
    var phase by mutableStateOf(Phase.Idle)
        private set
    var error by mutableStateOf<String?>(null)
    val busy get() = phase != Phase.Idle
    val status: String get() = when (phase) {
        Phase.Idle -> "转写可修改，确认后再发送。"
        Phase.Preparing -> "正在准备语音输入…"
        Phase.Recording -> "正在听您讲述，点击停止结束录音。"
        Phase.Finishing -> "正在完成转写…"
    }
    private val handler = Handler(Looper.getMainLooper())
    private var recognizer: SpeechRecognizer? = null
    private var operation = 0

    fun start(existing: String) {
        if (busy) return
        error = null
        if (!SpeechRecognizer.isRecognitionAvailable(context)) {
            error = "这台设备没有可用的普通话语音识别服务，请使用键盘输入。已有文字会保留。"
            return
        }
        val generation = ++operation
        phase = Phase.Preparing
        fun accepted() = operation == generation
        fun receive(bundle: Bundle?) {
            val text = bundle?.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION)?.firstOrNull().orEmpty()
            if (text.isNotBlank()) onText(existing + if (existing.isEmpty() || existing.endsWith('\n')) text else "\n$text")
        }
        try {
            recognizer = SpeechRecognizer.createSpeechRecognizer(context).also { service ->
                service.setRecognitionListener(object : RecognitionListener {
                    override fun onReadyForSpeech(params: Bundle?) { if (accepted()) phase = Phase.Recording }
                    override fun onBeginningOfSpeech() = Unit
                    override fun onRmsChanged(rmsdB: Float) = Unit
                    override fun onBufferReceived(buffer: ByteArray?) = Unit
                    override fun onEndOfSpeech() { if (accepted()) finishWait(generation) }
                    override fun onEvent(eventType: Int, params: Bundle?) = Unit
                    override fun onPartialResults(partialResults: Bundle?) { if (accepted()) receive(partialResults) }
                    override fun onResults(results: Bundle?) {
                        if (!accepted()) return
                        receive(results)
                        val empty = results?.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION)?.firstOrNull().isNullOrBlank()
                        cancel()
                        if (empty) error = "没有识别到清楚的语音，请再次录音或使用键盘输入。"
                    }
                    override fun onError(code: Int) {
                        if (!accepted()) return
                        cancel()
                        error = when (code) {
                            SpeechRecognizer.ERROR_INSUFFICIENT_PERMISSIONS -> "请在系统设置中允许麦克风，或使用键盘输入。"
                            SpeechRecognizer.ERROR_LANGUAGE_NOT_SUPPORTED, SpeechRecognizer.ERROR_LANGUAGE_UNAVAILABLE -> "普通话语音识别暂不可用，请安装系统普通话语音服务或使用键盘输入。"
                            SpeechRecognizer.ERROR_NETWORK, SpeechRecognizer.ERROR_NETWORK_TIMEOUT -> "语音识别网络中断。已识别文字会保留，请检查、修改后发送。"
                            SpeechRecognizer.ERROR_NO_MATCH, SpeechRecognizer.ERROR_SPEECH_TIMEOUT -> "没有识别到清楚的语音，请再次录音或使用键盘输入。"
                            else -> "语音识别中断。已识别文字会保留，请核对后发送，或再次录音。"
                        }
                    }
                })
                service.startListening(Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH).apply {
                    putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL, RecognizerIntent.LANGUAGE_MODEL_FREE_FORM)
                    putExtra(RecognizerIntent.EXTRA_LANGUAGE, "zh-CN")
                    putExtra(RecognizerIntent.EXTRA_PARTIAL_RESULTS, true)
                    putExtra(RecognizerIntent.EXTRA_MAX_RESULTS, 1)
                })
            }
        } catch (_: Exception) {
            cancel()
            error = "无法开始录音，请检查麦克风权限或使用键盘输入。"
        }
    }

    fun stop() {
        if (phase != Phase.Recording) { cancel(); return }
        recognizer?.stopListening()
        finishWait(operation)
    }

    private fun finishWait(generation: Int) {
        if (phase == Phase.Finishing) return
        phase = Phase.Finishing
        handler.postDelayed({
            if (operation == generation && busy) {
                cancel()
                error = "最终转写未及时返回，已保留当前文字。请核对后发送，或再次录音。"
            }
        }, 3_000)
    }

    fun cancel() {
        ++operation
        handler.removeCallbacksAndMessages(null)
        phase = Phase.Idle
        recognizer?.cancel()
        recognizer?.destroy()
        recognizer = null
    }
}
