plugins { id("com.android.application"); id("org.jetbrains.kotlin.android") }
val appVersion = rootProject.file("../VERSION").readText().trim()
require(Regex("[0-9]+\\.[0-9]+\\.[0-9]+").matches(appVersion)) { "Invalid root VERSION" }

android {
    namespace = "de.kassensturz.app"
    compileSdk = 35
    defaultConfig {
        applicationId = "de.kassensturz.app"
        minSdk = 28
        targetSdk = 35
        versionCode = 3
        versionName = appVersion
        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"
    }
    compileOptions { sourceCompatibility = JavaVersion.VERSION_17; targetCompatibility = JavaVersion.VERSION_17 }
    kotlinOptions { jvmTarget = "17" }
    buildTypes { release { isMinifyEnabled = false } }
    testOptions { unitTests.isReturnDefaultValues = true }
}
dependencies {
    implementation("androidx.core:core:1.15.0")
    implementation("com.google.mlkit:text-recognition:16.0.1")
    androidTestImplementation("androidx.test:runner:1.6.2")
    androidTestImplementation("androidx.test.ext:junit:1.2.1")
    testImplementation("junit:junit:4.13.2")
}
