plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

android {
    namespace = "org.copticreader.app"
    compileSdk = 35

    defaultConfig {
        applicationId = "org.copticreader.app"
        minSdk = 26
        targetSdk = 35
        versionCode = (System.getenv("GITHUB_RUN_NUMBER") ?: "1").toInt()
        versionName = "0.1." + (System.getenv("GITHUB_RUN_NUMBER") ?: "0")
        // real phones only: keeps the app smaller
        ndk { abiFilters += listOf("arm64-v8a", "armeabi-v7a") }
    }

    buildTypes {
        release {
            isMinifyEnabled = false
            // signed with the debug key so it installs directly (no Play Store)
            signingConfig = signingConfigs.getByName("debug")
        }
    }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions { jvmTarget = "17" }

    // the AI model must not be compressed inside the app, so it can be copied out fast
    androidResources { noCompress += listOf("ort") }

    sourceSets["main"].assets.srcDirs(layout.buildDirectory.dir("generated/www-assets"))
}

// Bundle the app screen (the same files as the web version), the books and the model.
val copyWebAssets by tasks.registering(Sync::class) {
    val root = rootProject.projectDir.parentFile
    from(root) {
        include("index.html", "src/**", "fonts/**", "books/**", "icons/**")
        into("www")
    }
    from(rootProject.file("model")) {
        include("w2v_int8.ort", "vocab.json")
        into("model")
    }
    into(layout.buildDirectory.dir("generated/www-assets"))
}
tasks.named("preBuild") { dependsOn(copyWebAssets) }

dependencies {
    implementation("com.microsoft.onnxruntime:onnxruntime-android:1.32.0")
    implementation("androidx.webkit:webkit:1.12.1")
}
