package com.oppo.smsclassifier

/**
 * LiteRT/TFLite model wrapper. When no model bytes are supplied, inference is unavailable.
 */
interface LiteRtPredictor : AutoCloseable {
    val isAvailable: Boolean
    val modelVersion: String
    fun predict(tokenIds: IntArray): FloatArray?
    fun warmUp()
}

class LiteRtClassifier(
    private val metadata: ModelMetadata,
    modelBytes: ByteArray? = null,
) : LiteRtPredictor {
    @Suppress("unused")
    private val modelBuffer: ByteArray? = modelBytes?.takeIf { it.isNotEmpty() }

    override val isAvailable: Boolean = modelBuffer != null

    override val modelVersion: String get() = metadata.modelVersion

    override fun predict(tokenIds: IntArray): FloatArray? {
        if (!isAvailable) return null
        // Phase 1: model bytes present but interpreter wiring deferred to later phase.
        return null
    }

    override fun warmUp() {
        if (!isAvailable) return
        predict(IntArray(metadata.inputLength) { metadata.padId })
    }

    override fun close() {
        // Release MappedByteBuffer / interpreter in later phases.
    }
}
