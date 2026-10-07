package com.oppo.smsclassifier

import org.json.JSONObject

/**
 * Unicode NFKC normalization with zero-width removal, whitespace collapse,
 * and optional confusables substitution. Devanagari combining marks are preserved.
 */
class TextNormalizer(
    private val maxLength: Int = 4096,
    private val version: String = "1.0.0",
    confusableReplacements: List<Pair<String, String>> = emptyList(),
) {
    val normalizationVersion: String get() = version

    private val replacements: List<Pair<String, String>> =
        confusableReplacements.sortedByDescending { it.first.length }

    fun normalize(text: String?): String {
        if (text == null) return ""
        var out = java.text.Normalizer.normalize(text, java.text.Normalizer.Form.NFKC)
        out = ZERO_WIDTH_REGEX.replace(out, "")
        out = applyConfusables(out)
        out = WHITESPACE_REGEX.replace(out, " ").trim()
        if (out.length > maxLength) {
            out = out.substring(0, maxLength)
        }
        return out
    }

    private fun applyConfusables(text: String): String {
        if (replacements.isEmpty()) return text
        var out = text
        for ((from, to) in replacements) {
            out = out.replace(from, to)
        }
        return out
    }

    companion object {
        private val ZERO_WIDTH_REGEX = Regex("[\\u200B\\u200C\\u200D\\uFEFF\\u2060\\u180E]")
        private val WHITESPACE_REGEX = Regex("\\s+")

        fun loadConfusablesFromJson(json: String): List<Pair<String, String>> {
            val root = JSONObject(json)
            val mappingsObject = when {
                root.has("mappings") -> root.getJSONObject("mappings")
                else -> root
            }
            val result = mutableListOf<Pair<String, String>>()
            val keys = mappingsObject.keys()
            while (keys.hasNext()) {
                val key = keys.next()
                if (key == "version") continue
                result.add(key to mappingsObject.getString(key))
            }
            return result
        }
    }
}
