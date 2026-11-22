package org.copticreader.app

import android.content.Context
import android.content.Intent
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.speech.RecognitionListener
import android.speech.RecognizerIntent
import android.speech.SpeechRecognizer

/**
 * Continuous listening with Android's built-in (free) speech recognizer.
 * Android stops after each phrase, so we restart it until stop() is called.
 * Sends the last ~30 words heard (final + partial) to onText.
 */
class WordListener(
    private val context: Context,
    private val language: String, // e.g. "ar-EG", "de-DE", "en-US"
    private val onText: (String) -> Unit,
    private val onFailed: (String) -> Unit,
) {
    private val main = Handler(Looper.getMainLooper())
    private var recognizer: SpeechRecognizer? = null
    private var running = false
    private var finalText = ""

    fun start() {
        if (!SpeechRecognizer.isRecognitionAvailable(context)) {
            onFailed("This phone has no speech recognizer. Install or enable Google speech services.")
            return
        }
        running = true
        recognizer = SpeechRecognizer.createSpeechRecognizer(context).apply { setRecognitionListener(listener) }
        listen()
    }

    fun stop() {
        running = false
        main.removeCallbacksAndMessages(null)
        recognizer?.destroy()
        recognizer = null
    }

    private fun listen() {
        if (!running) return
        val intent = Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH).apply {
            putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL, RecognizerIntent.LANGUAGE_MODEL_FREE_FORM)
            putExtra(RecognizerIntent.EXTRA_LANGUAGE, language)
            putExtra(RecognizerIntent.EXTRA_PARTIAL_RESULTS, true)
            putExtra(RecognizerIntent.EXTRA_MAX_RESULTS, 1)
            // keep listening through the pauses of the service
            putExtra(RecognizerIntent.EXTRA_SPEECH_INPUT_COMPLETE_SILENCE_LENGTH_MILLIS, 4000L)
            putExtra(RecognizerIntent.EXTRA_SPEECH_INPUT_POSSIBLY_COMPLETE_SILENCE_LENGTH_MILLIS, 4000L)
        }
        recognizer?.startListening(intent)
    }

    private fun restartSoon() { if (running) main.postDelayed({ listen() }, 250) }

    private fun send(extra: String) {
        val all = "$finalText $extra".trim().split(Regex("\\s+"))
        onText(all.takeLast(30).joinToString(" "))
    }

    private val listener = object : RecognitionListener {
        override fun onPartialResults(partial: Bundle) {
            partial.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION)?.firstOrNull()?.let { send(it) }
        }
        override fun onResults(results: Bundle) {
            results.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION)?.firstOrNull()?.let {
                finalText = "$finalText $it".trim().split(Regex("\\s+")).takeLast(30).joinToString(" ")
                send("")
            }
            restartSoon()
        }
        override fun onError(error: Int) {
            if (error == SpeechRecognizer.ERROR_INSUFFICIENT_PERMISSIONS) {
                running = false
                onFailed("Microphone permission is needed.")
            } else restartSoon() // no speech / timeout / busy: just keep listening
        }
        override fun onReadyForSpeech(params: Bundle?) {}
        override fun onBeginningOfSpeech() {}
        override fun onRmsChanged(rmsdB: Float) {}
        override fun onBufferReceived(buffer: ByteArray?) {}
        override fun onEndOfSpeech() {}
        override fun onEvent(eventType: Int, params: Bundle?) {}
    }
}
