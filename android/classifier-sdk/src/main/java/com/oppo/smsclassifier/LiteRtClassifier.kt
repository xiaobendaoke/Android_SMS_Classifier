package com.oppo.smsclassifier

import java.nio.ByteBuffer
import java.nio.ByteOrder
import kotlin.math.exp

/**
 * LiteRT/TFLite model wrapper. When no model bytes are supplied, inference is unavailable
 * and the DecisionRouter falls back to rules + REVIEW.
 *
 * Interpreter is loaded via reflection so JVM unit tests (no native TFLite) still compile/run
 * when modelBytes is null.
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
    private val modelBuffer: ByteBuffer? = modelBytes
        ?.takeIf { it.isNotEmpty() }
        ?.let { bytes ->
            ByteBuffer.allocateDirect(bytes.size).order(ByteOrder.nativeOrder()).apply {
                put(bytes)
                rewind()
            }
        }

    /** org.tensorflow.lite.Interpreter instance, or null. */
    private var interpreter: Any? = null
    private var runMethod: java.lang.reflect.Method? = null
    private var closeMethod: java.lang.reflect.Method? = null

    override val isAvailable: Boolean get() = interpreter != null

    override val modelVersion: String get() = metadata.modelVersion

    init {
        val buffer = modelBuffer
        if (buffer != null) {
            bindInterpreter(buffer)
        }
    }

    private fun bindInterpreter(buffer: ByteBuffer) {
        try {
            val interpreterClass = Class.forName("org.tensorflow.lite.Interpreter")
            val optionsClass = Class.forName("org.tensorflow.lite.Interpreter\$Options")
            val options = optionsClass.getDeclaredConstructor().newInstance()
            runCatching {
                optionsClass.getMethod("setNumThreads", Int::class.javaPrimitiveType)
                    .invoke(options, 2)
            }
            runCatching {
                optionsClass.getMethod("setUseXNNPACK", Boolean::class.javaPrimitiveType)
                    .invoke(options, true)
            }
            val ctor = interpreterClass.getConstructor(ByteBuffer::class.java, optionsClass)
            val instance = ctor.newInstance(buffer, options)
            interpreter = instance
            runMethod = interpreterClass.getMethod("run", Any::class.java, Any::class.java)
            closeMethod = interpreterClass.getMethod("close")
        } catch (_: Throwable) {
            interpreter = null
            runMethod = null
            closeMethod = null
        }
    }

    override fun predict(tokenIds: IntArray): FloatArray? {
        val interp = interpreter ?: return null
        val run = runMethod ?: return null
        if (tokenIds.size != metadata.inputLength) return null

        return runCatching {
            val input = Array(1) { IntArray(metadata.inputLength) }
            System.arraycopy(tokenIds, 0, input[0], 0, metadata.inputLength)
            val numLabels = metadata.labels.size

            // Prefer float output buffer; if INT8, dequantize via tensor scale/zero-point.
            val floatOut = Array(1) { FloatArray(numLabels) }
            val okFloat = runCatching {
                run.invoke(interp, input, floatOut)
                true
            }.getOrDefault(false)
            if (okFloat) {
                return@runCatching softmax(floatOut[0])
            }

            val intOut = Array(1) { ByteArray(numLabels) }
            run.invoke(interp, input, intOut)
            val dequant = dequantizeInt8(interp, intOut[0])
            softmax(dequant)
        }.getOrNull()
    }

    /**
     * Read output tensor quantization params via reflection when available.
     */
    private fun dequantizeInt8(interp: Any, bytes: ByteArray): FloatArray {
        var scale = 1f
        var zeroPoint = 0
        runCatching {
            val getOutputTensor = interp.javaClass.getMethod("getOutputTensor", Int::class.javaPrimitiveType)
            val tensor = getOutputTensor.invoke(interp, 0)
            val quantization = tensor.javaClass.getMethod("quantizationParams").invoke(tensor)
            scale = quantization.javaClass.getMethod("getScale").invoke(quantization) as Float
            zeroPoint = quantization.javaClass.getMethod("getZeroPoint").invoke(quantization) as Int
        }
        return FloatArray(bytes.size) { i ->
            scale * (bytes[i].toInt() - zeroPoint)
        }
    }

    override fun warmUp() {
        if (!isAvailable) return
        predict(IntArray(metadata.inputLength) { metadata.padId })
    }

    override fun close() {
        runCatching { closeMethod?.invoke(interpreter) }
        interpreter = null
        runMethod = null
        closeMethod = null
    }

    private fun softmax(logits: FloatArray): FloatArray {
        val sum = logits.sum()
        if (sum in 0.95f..1.05f && logits.all { it >= 0f }) {
            return logits.copyOf()
        }
        val max = logits.maxOrNull() ?: 0f
        var total = 0.0
        val exps = DoubleArray(logits.size)
        for (i in logits.indices) {
            exps[i] = exp((logits[i] - max).toDouble())
            total += exps[i]
        }
        if (total <= 0.0) return FloatArray(logits.size) { 1f / logits.size }
        return FloatArray(logits.size) { i -> (exps[i] / total).toFloat() }
    }
}
