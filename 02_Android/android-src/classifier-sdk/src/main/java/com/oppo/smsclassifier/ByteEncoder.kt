package com.oppo.smsclassifier

/**
 * UTF-8 byte encoder aligned with training/src/byte_encoder.py.
 */
class ByteEncoder(
    private val maxBytes: Int = 512,
    private val headBytes: Int = 384,
    private val tailBytes: Int = 128,
    private val padId: Int = 0,
    private val byteOffset: Int = 1,
) {
    fun encode(text: String): IntArray {
        var raw = text.toByteArray(Charsets.UTF_8)
        if (raw.size > maxBytes) {
            val head = raw.copyOfRange(0, headBytes)
            val tail = raw.copyOfRange(raw.size - tailBytes, raw.size)
            raw = head + tail
        }
        val ids = IntArray(maxBytes) { padId }
        val limit = minOf(raw.size, maxBytes)
        for (i in 0 until limit) {
            ids[i] = (raw[i].toInt() and 0xFF) + byteOffset
        }
        return ids
    }

    companion object {
        const val MAX_BYTES = 512
        const val PAD_ID = 0
        const val BYTE_OFFSET = 1
    }
}
