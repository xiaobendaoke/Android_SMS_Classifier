package com.oppo.smsclassifier

/**
 * Combines rule signals and optional model probabilities into final category/action.
 *
 * Category (what the message is) is separate from action (how to route it).
 * OTP protect can force INBOX but must not rewrite category to TRANSACTION when fraud conflicts.
 * Without a model, category falls back to rule hints or TRANSACTION with REVIEW when unconfident.
 */
class DecisionRouter(
    private val metadata: ModelMetadata,
) {
    fun route(
        input: SmsInput,
        normalized: String,
        signals: RuleSignals,
        modelProbs: FloatArray?,
        modelAvailable: Boolean,
    ): ClassificationResult {
        val conflict = signals.hasOtpProtect && signals.hasHighFraudRisk
        val hasModelOutput = modelAvailable && modelProbs != null && modelProbs.isNotEmpty()

        val rawModelCategory = if (hasModelOutput) {
            argmaxCategory(modelProbs!!)
        } else {
            signals.categoryHint ?: SmsCategory.TRANSACTION
        }

        val modelConfidence = if (hasModelOutput) {
            modelProbs!!.maxOrNull() ?: 0f
        } else {
            0f
        }

        val category = resolveCategory(
            conflict = conflict,
            hasModelOutput = hasModelOutput,
            modelCategory = if (hasModelOutput) rawModelCategory else null,
            signals = signals,
        )

        val lowConfidence = hasModelOutput &&
            modelConfidence < metadata.thresholdFor(category)

        val noModelLowConfidence = !hasModelOutput &&
            signals.categoryHint == null &&
            !signals.hasOtpProtect &&
            !signals.hasPickupProtect &&
            !signals.hasHighFraudRisk

        val action = resolveAction(
            conflict = conflict,
            signals = signals,
            category = category,
            hasModelOutput = hasModelOutput,
            lowConfidence = lowConfidence,
            modelConfidence = modelConfidence,
        )

        val reasonCode = resolveReasonCode(
            conflict = conflict,
            signals = signals,
            lowConfidence = lowConfidence,
            noModelLowConfidence = noModelLowConfidence,
            hasModelOutput = hasModelOutput,
        )

        val probabilities = if (hasModelOutput) {
            modelProbs!!.copyOf()
        } else {
            uniformProbs()
        }

        val confidence = if (hasModelOutput) {
            modelConfidence
        } else if (signals.categoryHint != null || signals.hasOtpProtect || signals.hasPickupProtect) {
            0.5f
        } else {
            0f
        }

        return ClassificationResult(
            category = category,
            action = action,
            probabilities = probabilities,
            confidence = confidence,
            rawModelCategory = rawModelCategory,
            ruleIds = signals.matchedRuleIds,
            reasonCode = reasonCode,
            languageHint = input.localeHint,
            elapsedMs = 0.0,
            modelVersion = metadata.modelVersion,
            rulesVersion = metadata.rulesVersion,
            normalizationVersion = metadata.normalizationVersion,
        )
    }

    private fun resolveCategory(
        conflict: Boolean,
        hasModelOutput: Boolean,
        modelCategory: SmsCategory?,
        signals: RuleSignals,
    ): SmsCategory {
        if (conflict) {
            // OTP must not blindly force TRANSACTION when fraud is present.
            return when {
                signals.hasHighFraudRisk -> SmsCategory.FRAUD
                modelCategory != null -> modelCategory
                signals.categoryHint != null -> signals.categoryHint
                else -> SmsCategory.TRANSACTION
            }
        }
        if (hasModelOutput && modelCategory != null) {
            return modelCategory
        }
        return signals.categoryHint ?: SmsCategory.TRANSACTION
    }

    private fun resolveAction(
        conflict: Boolean,
        signals: RuleSignals,
        category: SmsCategory,
        hasModelOutput: Boolean,
        lowConfidence: Boolean,
        modelConfidence: Float,
    ): SmsAction {
        if (conflict) return SmsAction.REVIEW
        if (signals.hasOtpProtect) return SmsAction.INBOX

        if (!hasModelOutput) {
            return when {
                signals.hasHighFraudRisk -> SmsAction.SUSPECT
                signals.hasPickupProtect -> SmsAction.INBOX
                category == SmsCategory.TRANSACTION &&
                    (signals.categoryHint == SmsCategory.TRANSACTION) -> SmsAction.INBOX
                category == SmsCategory.FRAUD -> SmsAction.SUSPECT
                category == SmsCategory.AD || category == SmsCategory.HARASS -> SmsAction.SUSPECT
                else -> SmsAction.REVIEW
            }
        }

        if (lowConfidence) return SmsAction.REVIEW

        return when {
            category == SmsCategory.TRANSACTION -> SmsAction.INBOX
            category == SmsCategory.FRAUD &&
                (signals.hasHighFraudRisk || modelConfidence >= metadata.thresholdFor(SmsCategory.FRAUD)) ->
                SmsAction.SUSPECT
            category == SmsCategory.AD || category == SmsCategory.HARASS -> SmsAction.SUSPECT
            else -> SmsAction.REVIEW
        }
    }

    private fun resolveReasonCode(
        conflict: Boolean,
        signals: RuleSignals,
        lowConfidence: Boolean,
        noModelLowConfidence: Boolean,
        hasModelOutput: Boolean,
    ): String = when {
        conflict -> "OTP_FRAUD_CONFLICT"
        noModelLowConfidence -> "NO_MODEL_LOW_CONFIDENCE"
        lowConfidence -> "MODEL_LOW_CONFIDENCE"
        signals.reasonCode != "NO_RULE_MATCH" -> signals.reasonCode
        hasModelOutput -> "MODEL_PREDICTION"
        else -> "NO_MODEL_LOW_CONFIDENCE"
    }

    private fun argmaxCategory(probs: FloatArray): SmsCategory {
        var bestIdx = 0
        var bestVal = probs[0]
        for (i in 1 until probs.size) {
            if (probs[i] > bestVal) {
                bestVal = probs[i]
                bestIdx = i
            }
        }
        val label = metadata.labels.getOrNull(bestIdx) ?: SmsCategory.TRANSACTION.name
        return runCatching { SmsCategory.valueOf(label) }.getOrDefault(SmsCategory.TRANSACTION)
    }

    private fun uniformProbs(): FloatArray = FloatArray(metadata.labels.size) { 1f / metadata.labels.size }
}
