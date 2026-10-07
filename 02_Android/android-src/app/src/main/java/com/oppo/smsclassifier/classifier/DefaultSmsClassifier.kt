package com.oppo.smsclassifier.classifier

import android.content.Context
import com.oppo.smsclassifier.ClassificationResult
import com.oppo.smsclassifier.SmsClassifier
import com.oppo.smsclassifier.SmsInput
import com.oppo.smsclassifier.DefaultSmsClassifier as SdkDefaultSmsClassifier

/**
 * Process-wide offline classifier bound to merged app/SDK assets.
 * Missing TFLite falls back to rules + REVIEW (never drops messages).
 */
object DefaultSmsClassifier {
    @Volatile
    private var delegate: SmsClassifier? = null
    @Volatile
    private var appContext: Context? = null

    fun init(context: Context) {
        if (delegate != null) return
        synchronized(this) {
            if (delegate != null) return
            val app = context.applicationContext
            appContext = app
            val assets = app.assets
            val modelBytes = runCatching {
                assets.open("model/sms_bytecnn_int8.tflite").use { it.readBytes() }
            }.getOrNull()
            val readAsset: (String) -> String = { path ->
                assets.open(path).bufferedReader().use { it.readText() }
            }
            delegate = SdkDefaultSmsClassifier(
                readAsset = readAsset,
                modelBytes = modelBytes,
            )
        }
    }

    fun warmUp(context: Context? = appContext) {
        val ctx = context ?: error("DefaultSmsClassifier.init(context) required before warmUp()")
        init(ctx)
        delegate?.warmUp()
    }

    suspend fun classify(input: SmsInput): ClassificationResult {
        val d = delegate
            ?: error("DefaultSmsClassifier.init(context) must be called first")
        return d.classify(input)
    }

    suspend fun classify(context: Context, input: SmsInput): ClassificationResult {
        init(context)
        return requireNotNull(delegate).classify(input)
    }
}
