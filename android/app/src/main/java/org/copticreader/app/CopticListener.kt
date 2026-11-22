package org.copticreader.app

import ai.onnxruntime.OnnxTensor
import ai.onnxruntime.OrtEnvironment
import ai.onnxruntime.OrtSession
import android.annotation.SuppressLint
import android.content.Context
import android.media.AudioFormat
import android.media.AudioRecord
import android.media.MediaRecorder
import org.json.JSONArray
import java.io.File
import java.nio.FloatBuffer
import java.util.concurrent.Executors
import java.util.concurrent.ScheduledExecutorService
import java.util.concurrent.TimeUnit
import kotlin.math.sqrt

/**
 * Follows Coptic by sound, fully on the phone (no internet):
 * microphone -> last 5 seconds -> AI model (wav2vec2 phonemes, ONNX) -> list of
 * sounds -> sent to the page, which finds them in the book's Coptic text.
 */
class CopticListener(
    private val context: Context,
    private val onSounds: (String) -> Unit,
    private val onStatus: (String) -> Unit,
    private val onFailed: (String) -> Unit,
) {
    private val worker: ScheduledExecutorService = Executors.newSingleThreadScheduledExecutor()
    private var record: AudioRecord? = null
    private var reader: Thread? = null
    @Volatile private var running = false

    // ring buffer with the last WINDOW_S seconds of audio
    private val ring = FloatArray(SAMPLE_RATE * WINDOW_S)
    private var written = 0L
    private val lock = Any()

    fun start() {
        running = true
        worker.execute {
            try {
                val (session, vocab) = loadModel()
                startMicrophone()
                onStatus("Listening for Coptic…")
                worker.scheduleWithFixedDelay({ step(session, vocab) }, 1000, STEP_MS, TimeUnit.MILLISECONDS)
            } catch (e: Throwable) {
                running = false
                onFailed("Coptic AI could not start: ${e.message}")
            }
        }
    }

    fun stop() {
        running = false
        worker.shutdownNow()
        record?.let { runCatching { it.stop() }; it.release() }
        record = null
    }

    /** The model ships inside the app; it is copied out once so it can be memory-mapped. */
    private fun loadModel(): Pair<OrtSession, List<String>> {
        val file = File(context.filesDir, "w2v_int8.onnx")
        val size = context.assets.openFd("model/w2v_int8.onnx").use { it.length }
        if (!file.exists() || file.length() != size) {
            onStatus("Preparing the Coptic AI (first time only)…")
            context.assets.open("model/w2v_int8.onnx").use { input -> file.outputStream().use { input.copyTo(it, 1 shl 20) } }
        }
        val vocabJson = context.assets.open("model/vocab.json").bufferedReader().use { it.readText() }
        val vocab = JSONArray(vocabJson).let { a -> List(a.length()) { a.getString(it) } }
        onStatus("Loading the Coptic AI…")
        val opts = OrtSession.SessionOptions().apply {
            setIntraOpNumThreads(Runtime.getRuntime().availableProcessors().coerceIn(2, 4))
            setOptimizationLevel(OrtSession.SessionOptions.OptLevel.ALL_OPT)
        }
        return OrtEnvironment.getEnvironment().createSession(file.absolutePath, opts) to vocab
    }

    @SuppressLint("MissingPermission") // checked by MainActivity before starting
    private fun startMicrophone() {
        val min = AudioRecord.getMinBufferSize(SAMPLE_RATE, AudioFormat.CHANNEL_IN_MONO, AudioFormat.ENCODING_PCM_16BIT)
        val rec = AudioRecord(
            MediaRecorder.AudioSource.VOICE_RECOGNITION, SAMPLE_RATE,
            AudioFormat.CHANNEL_IN_MONO, AudioFormat.ENCODING_PCM_16BIT, maxOf(min, SAMPLE_RATE),
        )
        check(rec.state == AudioRecord.STATE_INITIALIZED) { "microphone unavailable" }
        record = rec
        rec.startRecording()
        reader = Thread {
            val buf = ShortArray(1600)
            while (running) {
                val n = rec.read(buf, 0, buf.size)
                if (n <= 0) continue
                synchronized(lock) {
                    for (i in 0 until n) {
                        ring[((written + i) % ring.size).toInt()] = buf[i] / 32768f
                    }
                    written += n
                }
            }
        }.apply { isDaemon = true; start() }
    }

    /** Every second: recognize the sounds of the last 5 seconds and send them. */
    private fun step(session: OrtSession, vocab: List<String>) {
        if (!running) return
        val audio: FloatArray
        synchronized(lock) {
            val n = minOf(written, ring.size.toLong()).toInt()
            if (n < SAMPLE_RATE) return
            audio = FloatArray(n) { i -> ring[((written - n + i) % ring.size).toInt()] }
        }
        // the model expects zero-mean, unit-variance audio
        val mean = audio.average().toFloat()
        var sq = 0.0
        for (v in audio) sq += (v - mean) * (v - mean)
        val std = sqrt(sq / audio.size).toFloat() + 1e-7f
        if (std < 0.003f) { onSounds("[]"); return } // silence
        for (i in audio.indices) audio[i] = (audio[i] - mean) / std

        val env = OrtEnvironment.getEnvironment()
        OnnxTensor.createTensor(env, FloatBuffer.wrap(audio), longArrayOf(1, audio.size.toLong())).use { input ->
            session.run(mapOf("audio" to input)).use { out ->
                @Suppress("UNCHECKED_CAST")
                val logits = (out[0].value as Array<Array<FloatArray>>)[0]
                val phones = JSONArray()
                var last = -1
                for (frame in logits) { // greedy CTC: best token per frame, merge repeats, drop blanks
                    var best = 0
                    for (k in frame.indices) if (frame[k] > frame[best]) best = k
                    if (best != last) {
                        val p = vocab[best]
                        if (p != "<pad>" && p != "<s>" && p != "</s>" && p != "<unk>" && p != "|") phones.put(p)
                    }
                    last = best
                }
                onSounds(phones.toString())
            }
        }
    }

    companion object {
        const val SAMPLE_RATE = 16000
        const val WINDOW_S = 5
        const val STEP_MS = 1000L
    }
}
