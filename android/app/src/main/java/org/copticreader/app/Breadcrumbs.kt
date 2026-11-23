package org.copticreader.app

import android.content.Context
import java.io.File
import java.io.PrintWriter
import java.io.StringWriter

/**
 * Remembers what the app was doing, so that if Android kills it (for example
 * when memory runs out), the next start can tell the user where it stopped.
 * Also records the error of an unexpected crash.
 */
object Breadcrumbs {
    private fun file(c: Context) = File(c.filesDir, "last_step.txt")

    fun mark(c: Context, step: String) = runCatching { file(c).writeText(step) }

    fun clear(c: Context) = runCatching { file(c).delete() }

    /** What the app was doing when it last stopped unexpectedly, if anything. */
    fun takeLast(c: Context): String? = runCatching {
        val f = file(c)
        if (f.exists()) f.readText().also { f.delete() } else null
    }.getOrNull()

    fun installCrashHandler(c: Context) {
        val previous = Thread.getDefaultUncaughtExceptionHandler()
        Thread.setDefaultUncaughtExceptionHandler { thread, e ->
            val sw = StringWriter().also { e.printStackTrace(PrintWriter(it)) }
            val step = runCatching { file(c).readText() }.getOrDefault("running")
            mark(c, "$step — error: ${e.javaClass.simpleName}: ${e.message}\n${sw.toString().take(1500)}")
            previous?.uncaughtException(thread, e)
        }
    }
}
