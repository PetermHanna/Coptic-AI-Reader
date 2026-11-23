package org.copticreader.app

import ai.onnxruntime.OnnxTensor
import ai.onnxruntime.OrtEnvironment
import ai.onnxruntime.OrtSession
import android.annotation.SuppressLint
import android.app.ActivityManager
import android.content.Context
import android.media.AudioFormat
import android.media.AudioRecord
import android.media.MediaRecorder
import android.os.SystemClock
import org.json.JSONArray
import java.io.File
import java.io.RandomAccessFile
import java.nio.FloatBuffer
import java.nio.MappedByteBuffer
import java.nio.channels.FileChannel
import java.util.concurrent.Executors
import java.util.concurrent.ScheduledExecutorService
import java.util.concurrent.TimeUnit
import kotlin.math.sqrt

/**
 * Follows Coptic by sound, fully on the phone (no internet):
 * microphone -> last 4 seconds -> AI model (wav2vec2 phonemes, ONNX Runtime) ->
 * list of sounds -> sent to the page, which finds them in the book's Coptic text.
 *
 * Memory: the model file is memory-mapped and used in place, so its ~320 MB of
 * weights are not copied into the app's memory (app memory ~190 MB instead of
 * ~720 MB). Android can reclaim those pages instead of killing the app.
 */
class CopticListener(
    private val context: Context,
    private val onSounds: (String) -> Unit,
    private val onStatus: (String) -> Unit,
    private val onFailed: (String) -> Unit,
) {
    private val worker: ScheduledExecutorService = Executors.newSingleThreadScheduledExecutor()
    private var record: AudioRecord? = null
    @Volatile private var running = false
    private var session: OrtSession? = null
    private var modelBuffer: MappedByteBuffer? = null // keep mapped while the session lives

    // ring buffer with the last WINDOW_S seconds of audio
    private val ring = FloatArray(SAMPLE_RATE * WINDOW_S)
    private var written = 0L
    private val lock = Any()
    private var steps = 0

    fun start() {
        running = true
        worker.execute {
            try {
                val (s, vocab) = loadModel()
                if (!running) return@execute
                session = s
                Breadcrumbs.mark(context, "starting the microphone for Coptic")
                startMicrophone()
                Breadcrumbs.mark(context, "listening for Coptic")
                onStatus("Listening for Coptic…")
                worker.schedule({ loop(s, vocab) }, STEP_MS, TimeUnit.MILLISECONDS)
            } catch (e: Throwable) {
                running = false
                Breadcrumbs.clear(context)
                onFailed("Coptic AI could not start: ${e.message ?: e.javaClass.simpleName}")
            }
        }
    }

    fun stop() {
        running = false
        worker.shutdownNow()
        record?.let { runCatching { it.stop() }; it.release() }
        record = null
        Breadcrumbs.clear(context)
        // close the model only after a running step has finished (never mid-run)
        val s = session
        session = null
        Thread {
            runCatching { worker.awaitTermination(10, TimeUnit.SECONDS) }
            runCatching { s?.close() }
            modelBuffer = null
        }.start()
    }

    private fun loadModel(): Pair<OrtSession, List<String>> {
        // refuse politely instead of being killed when the phone is short on memory
        val am = context.getSystemService(Context.ACTIVITY_SERVICE) as ActivityManager
        val mi = ActivityManager.MemoryInfo().also { am.getMemoryInfo(it) }
        if (mi.availMem < 350L * 1024 * 1024) {
            throw IllegalStateException("not enough free memory (${mi.availMem / 1_048_576} MB). Close other apps and try again.")
        }

        val file = File(context.filesDir, "w2v_int8.ort")
        val size = context.assets.openFd("model/w2v_int8.ort").use { it.length }
        if (!file.exists() || file.length() != size) {
            Breadcrumbs.mark(context, "preparing the Coptic AI (copying the model)")
            onStatus("Preparing the Coptic AI (first time only, ~20 s)…")
            File(context.filesDir, "w2v_int8.onnx").delete() // older app versions
            context.assets.open("model/w2v_int8.ort").use { input -> file.outputStream().use { input.copyTo(it, 1 shl 20) } }
        }
        val vocab = context.assets.open("model/vocab.json").bufferedReader().use { it.readText() }
            .let { JSONArray(it) }.let { a -> List(a.length()) { a.getString(it) } }

        Breadcrumbs.mark(context, "loading the Coptic AI model")
        onStatus("Loading the Coptic AI…")
        val buffer = RandomAccessFile(file, "r").use { raf ->
            raf.channel.map(FileChannel.MapMode.READ_ONLY, 0, raf.length())
        }
        modelBuffer = buffer
        val opts = OrtSession.SessionOptions().apply {
            setIntraOpNumThreads(2)               // gentle on battery and heat
            setCPUArenaAllocator(false)
            setMemoryPatternOptimization(false)
            addConfigEntry("session.use_ort_model_bytes_directly", "1")
            addConfigEntry("session.use_ort_model_bytes_for_initializers", "1")
            addConfigEntry("session.disable_prepacking", "1")
        }
        return OrtEnvironment.getEnvironment().createSession(buffer, opts) to vocab
    }

    @SuppressLint("MissingPermission") // checked by MainActivity before starting
    private fun startMicrophone() {
        val min = AudioRecord.getMinBufferSize(SAMPLE_RATE, AudioFormat.CHANNEL_IN_MONO, AudioFormat.ENCODING_PCM_16BIT)
        val rec = AudioRecord(
            MediaRecorder.AudioSource.VOICE_RECOGNITION, SAMPLE_RATE,
            AudioFormat.CHANNEL_IN_MONO, AudioFormat.ENCODING_PCM_16BIT, maxOf(min, SAMPLE_RATE),
        )
        if (rec.state != AudioRecord.STATE_INITIALIZED) {
            rec.release()
            throw IllegalStateException("the microphone is not available (used by another app?)")
        }
        record = rec
        rec.startRecording()
        Thread {
            val buf = ShortArray(1600)
            while (running) {
                val n = try { rec.read(buf, 0, buf.size) } catch (e: Throwable) { -1 }
                if (n <= 0) { if (!running) break; SystemClock.sleep(20); continue }
                synchronized(lock) {
                    for (i in 0 until n) ring[((written + i) % ring.size).toInt()] = buf[i] / 32768f
                    written += n
                }
            }
        }.apply { isDaemon = true; name = "coptic-mic"; start() }
    }

    /**
     * Run a step, then rest at least as long as the step took (and at least
     * 1.5 s), so a slow phone always keeps half its processor for the screen.
     */
    private fun loop(session: OrtSession, vocab: List<String>) {
        if (!running) return
        val t0 = SystemClock.elapsedRealtime()
        step(session, vocab)
        val took = SystemClock.elapsedRealtime() - t0
        if (running) runCatching {
            worker.schedule({ loop(session, vocab) }, maxOf(STEP_MS, took), TimeUnit.MILLISECONDS)
        }
    }

    /** Recognize the sounds of the last 4 seconds and send them. */
    private fun step(session: OrtSession, vocab: List<String>) {
        if (!running) return
        try {
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

            val t0 = SystemClock.elapsedRealtime()
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
            if (++steps == 2) {
                val ms = SystemClock.elapsedRealtime() - t0
                onStatus("Coptic AI running (${ms} ms per step)")
            }
        } catch (e: Throwable) {
            running = false
            onFailed("Coptic AI stopped: ${e.message ?: e.javaClass.simpleName}")
        }
    }

    companion object {
        const val SAMPLE_RATE = 16000
        const val WINDOW_S = 4
        const val STEP_MS = 1500L
    }
}
