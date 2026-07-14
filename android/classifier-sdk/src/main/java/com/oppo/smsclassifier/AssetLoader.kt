package com.oppo.smsclassifier

import java.io.InputStream

/**
 * Loads text assets from the classpath for JVM unit tests.
 * Android runtime should pass an [android.content.res.AssetManager] reader lambda to [DefaultSmsClassifier].
 */
object AssetLoader {
    fun readText(path: String): String {
        val normalizedPath = path.trimStart('/')
        val classLoader = AssetLoader::class.java.classLoader
            ?: throw IllegalStateException(
                "Cannot load resource '$normalizedPath': no ClassLoader available",
            )
        val stream = classLoader.getResourceAsStream(normalizedPath)
            ?: throw IllegalStateException(
                "Resource not found on classpath: '$normalizedPath'. " +
                    "For JVM tests, place the file under src/test/resources/$normalizedPath " +
                    "mirroring src/main/assets/.",
            )
        return stream.bufferedReader(Charsets.UTF_8).use { it.readText() }
    }
}
