package org.copticreader.app

import android.Manifest
import android.annotation.SuppressLint
import android.app.Activity
import android.content.pm.PackageManager
import android.graphics.Color
import android.os.Build
import android.os.Bundle
import android.view.WindowInsets
import android.view.WindowManager
import android.webkit.JavascriptInterface
import android.webkit.WebResourceRequest
import android.webkit.WebResourceResponse
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.FrameLayout
import androidx.webkit.WebViewAssetLoader
import org.json.JSONObject

/**
 * The app: shows the prayer book screen (bundled with the app, works offline)
 * and gives it two listeners: Android's speech recognizer for Arabic, German and
 * English words, and the on-phone AI sound model for Coptic.
 */
class MainActivity : Activity() {
    private lateinit var web: WebView
    private var words: WordListener? = null
    private var coptic: CopticListener? = null
    private var pendingMode: String? = null
    private var lastStop: String? = null

    @SuppressLint("SetJavaScriptEnabled")
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        Breadcrumbs.installCrashHandler(applicationContext)
        lastStop = Breadcrumbs.takeLast(this)

        // serve the bundled files from an https address so the page can load its books
        val assets = WebViewAssetLoader.Builder()
            .addPathHandler("/assets/", WebViewAssetLoader.AssetsPathHandler(this))
            .build()
        web = WebView(this).apply {
            setBackgroundColor(BG)
            settings.javaScriptEnabled = true
            settings.domStorageEnabled = true
            settings.mediaPlaybackRequiresUserGesture = false
            webViewClient = object : WebViewClient() {
                override fun shouldInterceptRequest(view: WebView, request: WebResourceRequest): WebResourceResponse? =
                    assets.shouldInterceptRequest(request.url)

                override fun onPageFinished(view: WebView, url: String) {
                    // tell the user if the app stopped unexpectedly last time, and where
                    lastStop?.let { js("nativeStatus(${JSONObject.quote("Last time the app closed while $it")})") }
                    lastStop = null
                }
            }
            addJavascriptInterface(Bridge(), "Native")
            loadUrl("https://appassets.androidplatform.net/assets/www/index.html")
        }

        // Keep the page out from under the status bar and navigation bar
        // (Android 15 draws apps edge to edge, which covered the top buttons).
        val root = FrameLayout(this).apply { setBackgroundColor(BG) }
        root.addView(web, FrameLayout.LayoutParams(FrameLayout.LayoutParams.MATCH_PARENT, FrameLayout.LayoutParams.MATCH_PARENT))
        root.setOnApplyWindowInsetsListener { v, insets ->
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
                val bars = insets.getInsets(WindowInsets.Type.systemBars() or WindowInsets.Type.displayCutout())
                v.setPadding(bars.left, bars.top, bars.right, bars.bottom)
            } else {
                @Suppress("DEPRECATION")
                v.setPadding(insets.systemWindowInsetLeft, insets.systemWindowInsetTop, insets.systemWindowInsetRight, insets.systemWindowInsetBottom)
            }
            insets
        }
        setContentView(root)
    }

    /** Called from the page's JavaScript as window.Native.start(...) / stop(). */
    inner class Bridge {
        @JavascriptInterface
        fun start(mode: String) = runOnUiThread { startListening(mode) }

        @JavascriptInterface
        fun stop() = runOnUiThread { stopListening() }
    }

    private fun startListening(mode: String) {
        if (checkSelfPermission(Manifest.permission.RECORD_AUDIO) != PackageManager.PERMISSION_GRANTED) {
            pendingMode = mode
            requestPermissions(arrayOf(Manifest.permission.RECORD_AUDIO), REQ_MIC)
            return
        }
        stopListening()
        window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
        try {
            if (mode == "cop") {
                coptic = CopticListener(
                    applicationContext,
                    onSounds = { json -> js("nativeSounds(${JSONObject.quote(json)})") },
                    onStatus = { msg -> js("nativeStatus(${JSONObject.quote(msg)})") },
                    onFailed = { msg -> runOnUiThread { stopListening() }; js("nativeStopped(${JSONObject.quote(msg)})") },
                ).also { it.start() }
            } else {
                Breadcrumbs.mark(this, "listening with the speech recognizer ($mode)")
                words = WordListener(
                    this, mode,
                    onText = { text -> js("nativeHeard(${JSONObject.quote(text)})") },
                    onFailed = { msg -> runOnUiThread { stopListening() }; js("nativeStopped(${JSONObject.quote(msg)})") },
                ).also { it.start() }
            }
        } catch (e: Throwable) {
            stopListening()
            js("nativeStopped(${JSONObject.quote("Could not start listening: ${e.message ?: e.javaClass.simpleName}")})")
        }
    }

    private fun stopListening() {
        words?.stop(); words = null
        coptic?.stop(); coptic = null
        Breadcrumbs.clear(this)
        window.clearFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
    }

    private fun js(code: String) = runOnUiThread { web.evaluateJavascript(code, null) }

    override fun onRequestPermissionsResult(requestCode: Int, permissions: Array<out String>, grantResults: IntArray) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults)
        if (requestCode != REQ_MIC) return
        val mode = pendingMode ?: return
        pendingMode = null
        if (grantResults.firstOrNull() == PackageManager.PERMISSION_GRANTED) startListening(mode)
        else js("nativeStopped(${JSONObject.quote("Microphone permission is needed to follow the service.")})")
    }

    override fun onDestroy() {
        stopListening()
        web.destroy()
        super.onDestroy()
    }

    // Back: close the settings panel first; otherwise leave the app as usual.
    @Deprecated("Deprecated in Android")
    override fun onBackPressed() {
        web.evaluateJavascript("window.closeSettings ? window.closeSettings() : false") { closed ->
            if (closed != "true") {
                @Suppress("DEPRECATION")
                super.onBackPressed()
            }
        }
    }

    companion object {
        private const val REQ_MIC = 7
        private val BG = Color.parseColor("#17110d")
    }
}
