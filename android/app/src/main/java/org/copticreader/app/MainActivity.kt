package org.copticreader.app

import android.Manifest
import android.annotation.SuppressLint
import android.app.Activity
import android.content.pm.PackageManager
import android.graphics.Color
import android.os.Bundle
import android.view.WindowManager
import android.webkit.JavascriptInterface
import android.webkit.WebResourceRequest
import android.webkit.WebResourceResponse
import android.webkit.WebView
import android.webkit.WebViewClient
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

    @SuppressLint("SetJavaScriptEnabled")
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        window.statusBarColor = Color.parseColor("#100b08")
        window.navigationBarColor = Color.parseColor("#100b08")

        // serve the bundled files from an https address so the page can load its books
        val assets = WebViewAssetLoader.Builder()
            .addPathHandler("/assets/", WebViewAssetLoader.AssetsPathHandler(this))
            .build()
        web = WebView(this).apply {
            setBackgroundColor(Color.parseColor("#17110d"))
            settings.javaScriptEnabled = true
            settings.domStorageEnabled = true
            settings.mediaPlaybackRequiresUserGesture = false
            webViewClient = object : WebViewClient() {
                override fun shouldInterceptRequest(view: WebView, request: WebResourceRequest): WebResourceResponse? =
                    assets.shouldInterceptRequest(request.url)
            }
            addJavascriptInterface(Bridge(), "Native")
            loadUrl("https://appassets.androidplatform.net/assets/www/index.html")
        }
        setContentView(web)
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
        if (mode == "cop") {
            coptic = CopticListener(
                this,
                onSounds = { json -> js("nativeSounds(${JSONObject.quote(json)})") },
                onStatus = { msg -> js("nativeStatus(${JSONObject.quote(msg)})") },
                onFailed = { msg -> js("nativeStopped(${JSONObject.quote(msg)})") },
            ).also { it.start() }
        } else {
            words = WordListener(
                this, mode,
                onText = { text -> js("nativeHeard(${JSONObject.quote(text)})") },
                onFailed = { msg -> js("nativeStopped(${JSONObject.quote(msg)})") },
            ).also { it.start() }
        }
    }

    private fun stopListening() {
        words?.stop(); words = null
        coptic?.stop(); coptic = null
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

    @Deprecated("Back goes back inside the page first")
    override fun onBackPressed() {
        if (web.canGoBack()) web.goBack() else @Suppress("DEPRECATION") super.onBackPressed()
    }

    companion object { private const val REQ_MIC = 7 }
}
