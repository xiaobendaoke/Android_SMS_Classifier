package com.oppo.smsclassifier.receiver

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.provider.Telephony
import com.oppo.smsclassifier.SmsAction
import com.oppo.smsclassifier.SmsClassifierApplication
import com.oppo.smsclassifier.SmsInput
import com.oppo.smsclassifier.classifier.DefaultSmsClassifier
import com.oppo.smsclassifier.data.ClassificationMeta
import com.oppo.smsclassifier.data.SmsProviderRepository
import com.oppo.smsclassifier.notification.NotificationHelper
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import kotlinx.coroutines.withTimeoutOrNull
import org.json.JSONArray
import java.security.MessageDigest
import java.util.concurrent.TimeUnit

/**
 * Default-SMS deliver path:
 * 1) Persist to system SMS Provider first (never lose the message).
 * 2) Classify offline with a hard 500ms budget.
 * 3) On timeout/error → action=REVIEW (visible), never auto-delete.
 * 4) Do not force category=TRANSACTION on failure (avoids gaming transaction recall).
 * 5) Idempotent on repeated broadcasts via deliverKey.
 */
class SmsDeliverReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        val pending = goAsync()
        val app = context.applicationContext as SmsClassifierApplication
        val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)

        scope.launch {
            var messageUri: String? = null
            var address = ""
            try {
                val messages = Telephony.Sms.Intents.getMessagesFromIntent(intent)
                if (messages.isNullOrEmpty()) return@launch

                // Multipart: concatenate bodies; dual-SIM: subscription extra when present.
                address = messages.first().displayOriginatingAddress ?: ""
                val body = messages.joinToString(separator = "") { it.messageBody ?: "" }
                val timestamp = messages.first().timestampMillis
                val subscriptionId = intent.getIntExtra("subscription", -1).takeIf { it >= 0 }
                val deliverKey = idempotencyKey(address, timestamp, body, subscriptionId)

                val smsRepo = SmsProviderRepository(context)
                val dao = app.database.classificationDao()

                // Duplicate broadcast: keep existing Provider row / metadata.
                val existing = dao.getByDeliverKey(deliverKey)
                if (existing != null) {
                    messageUri = existing.messageUri
                    withContext(Dispatchers.Main) {
                        NotificationHelper.showSafeNotification(
                            context = context,
                            action = runCatching { SmsAction.valueOf(existing.action) }
                                .getOrDefault(SmsAction.REVIEW),
                            address = address,
                            messageUri = existing.messageUri,
                        )
                    }
                    return@launch
                }

                val insertedUri = smsRepo.insertInboxMessage(
                    address = address,
                    body = body,
                    timestampMillis = timestamp,
                    subscriptionId = subscriptionId,
                )
                val messageId = insertedUri?.lastPathSegment?.toLongOrNull()
                messageUri = insertedUri?.toString()
                    ?: messageId?.let { smsRepo.messageUriForId(it) }

                if (messageUri == null) {
                    // Provider write failed — still notify so the user knows something arrived.
                    withContext(Dispatchers.Main) {
                        NotificationHelper.showSafeNotification(
                            context = context,
                            action = SmsAction.REVIEW,
                            address = address,
                            messageUri = "sms://undelivered/$deliverKey",
                        )
                    }
                    return@launch
                }

                DefaultSmsClassifier.init(context)

                val result = withTimeoutOrNull(TimeUnit.MILLISECONDS.toMillis(500)) {
                    DefaultSmsClassifier.classify(
                        context,
                        SmsInput(
                            sender = address,
                            body = body,
                            timestampMillis = timestamp,
                            subscriptionId = subscriptionId,
                        ),
                    )
                }

                // Safe path on timeout/error: REVIEW action; category left unset (not TRANSACTION/AD).
                val category = result?.category?.name ?: "UNKNOWN"
                val action = result?.action?.name ?: SmsAction.REVIEW.name
                val confidence = result?.confidence ?: 0f
                val reasonCode = result?.reasonCode ?: "TIMEOUT_OR_ERROR"
                val ruleIdsJson = JSONArray(result?.ruleIds ?: emptyList<String>()).toString()
                val modelVersion = result?.modelVersion ?: "unknown"
                val rulesVersion = result?.rulesVersion ?: "unknown"

                val meta = ClassificationMeta(
                    messageUri = messageUri,
                    messageId = messageId,
                    threadId = null,
                    category = category,
                    action = action,
                    confidence = confidence,
                    reasonCode = reasonCode,
                    ruleIdsJson = ruleIdsJson,
                    modelVersion = modelVersion,
                    rulesVersion = rulesVersion,
                    createdAt = System.currentTimeMillis(),
                    deliverKey = deliverKey,
                )
                dao.insert(meta)

                withContext(Dispatchers.Main) {
                    val smsAction = result?.action ?: SmsAction.REVIEW
                    NotificationHelper.showSafeNotification(
                        context = context,
                        action = smsAction,
                        address = address,
                        messageUri = messageUri,
                    )
                }
            } catch (_: Exception) {
                // Message already in system Provider when insert succeeded; still notify.
                val uri = messageUri
                if (uri != null) {
                    runCatching {
                        withContext(Dispatchers.Main) {
                            NotificationHelper.showSafeNotification(
                                context = context,
                                action = SmsAction.REVIEW,
                                address = address,
                                messageUri = uri,
                            )
                        }
                    }
                }
            } finally {
                pending.finish()
            }
        }
    }

    companion object {
        fun idempotencyKey(
            address: String,
            timestampMillis: Long,
            body: String,
            subscriptionId: Int?,
        ): String {
            val raw = listOf(
                address,
                timestampMillis.toString(),
                body,
                subscriptionId?.toString().orEmpty(),
            ).joinToString("|")
            val digest = MessageDigest.getInstance("SHA-256")
                .digest(raw.toByteArray(Charsets.UTF_8))
            return digest.joinToString("") { "%02x".format(it) }
        }
    }
}
