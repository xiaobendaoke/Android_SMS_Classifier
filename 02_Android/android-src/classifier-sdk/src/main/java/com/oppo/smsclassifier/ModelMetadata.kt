package com.oppo.smsclassifier

import org.json.JSONObject

/**
 * Model metadata loaded from assets/model/model_metadata.json.
 */
data class ModelMetadata(
    val modelVersion: String,
    val architecture: String,
    val inputLength: Int,
    val padId: Int,
    val byteOffset: Int,
    val labels: List<String>,
    val normalizationVersion: String,
    val rulesVersion: String,
    val quantization: String,
    val thresholds: Map<String, Map<SmsCategory, Float>>,
    val modelOutputSize: Int,
    val transactionProtectionIndex: Int?,
    val transactionProtectionThreshold: Float,
) {
    fun thresholdFor(category: SmsCategory): Float {
        val default = thresholds["default"] ?: emptyMap()
        return default[category] ?: DEFAULT_THRESHOLDS[category] ?: 0.5f
    }

    fun labelIndex(category: SmsCategory): Int = labels.indexOf(category.name)

    companion object {
        private val DEFAULT_THRESHOLDS = mapOf(
            SmsCategory.TRANSACTION to 0.55f,
            SmsCategory.AD to 0.70f,
            SmsCategory.HARASS to 0.70f,
            SmsCategory.FRAUD to 0.75f,
        )

        fun loadFromJson(json: String): ModelMetadata {
            val root = JSONObject(json)
            val labels = buildList {
                val array = root.getJSONArray("labels")
                for (i in 0 until array.length()) {
                    add(array.getString(i))
                }
            }
            val thresholds = parseThresholds(root.optJSONObject("thresholds"))
            return ModelMetadata(
                modelVersion = root.getString("modelVersion"),
                architecture = root.getString("architecture"),
                inputLength = root.getInt("inputLength"),
                padId = root.getInt("padId"),
                byteOffset = root.getInt("byteOffset"),
                labels = labels,
                normalizationVersion = root.getString("normalizationVersion"),
                rulesVersion = root.getString("rulesVersion"),
                quantization = root.getString("quantization"),
                thresholds = thresholds,
                modelOutputSize = root.optInt("modelOutputSize", labels.size),
                transactionProtectionIndex = root
                    .optInt("transactionProtectionIndex", -1)
                    .takeIf { it >= 0 },
                transactionProtectionThreshold = root
                    .optDouble("transactionProtectionThreshold", 0.5)
                    .toFloat(),
            )
        }

        fun loadDefault(): ModelMetadata = loadFromJson(
            """
            {
              "modelVersion": "1.0.0",
              "architecture": "byte_textcnn",
              "inputLength": 512,
              "padId": 0,
              "byteOffset": 1,
              "labels": ["TRANSACTION", "AD", "HARASS", "FRAUD"],
              "normalizationVersion": "1.0.0",
              "rulesVersion": "1.0.0",
              "quantization": "INT8",
              "modelOutputSize": 4,
              "transactionProtectionIndex": -1,
              "transactionProtectionThreshold": 0.5,
              "thresholds": {
                "default": {
                  "TRANSACTION": 0.55,
                  "AD": 0.70,
                  "HARASS": 0.70,
                  "FRAUD": 0.75
                }
              }
            }
            """.trimIndent(),
        )

        private fun parseThresholds(obj: JSONObject?): Map<String, Map<SmsCategory, Float>> {
            if (obj == null) return emptyMap()
            val result = linkedMapOf<String, Map<SmsCategory, Float>>()
            val groups = obj.keys()
            while (groups.hasNext()) {
                val groupName = groups.next()
                val groupObj = obj.getJSONObject(groupName)
                val categoryMap = linkedMapOf<SmsCategory, Float>()
                val categories = groupObj.keys()
                while (categories.hasNext()) {
                    val categoryName = categories.next()
                    runCatching {
                        categoryMap[SmsCategory.valueOf(categoryName)] = groupObj.getDouble(categoryName).toFloat()
                    }
                }
                result[groupName] = categoryMap
            }
            return result
        }
    }
}
