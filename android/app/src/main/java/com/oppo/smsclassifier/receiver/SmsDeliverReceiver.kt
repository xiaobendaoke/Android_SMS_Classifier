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
import java.util.concurrent.TimeUnit

class SmsDeliverReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        val pending = goAsync()
        val app = context.applicationContext as SmsClassifierApplication
        val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)

        scope.launch {
            try {
                val messages = Telephony.Sms.Intents.getMessagesFromIntent(intent)
                if (messages.isEmpty()) return@launch

                val address = messages.first().displayOriginatingAddress ?: ""
                val body = messages.joinToString(separator = "") { it.messageBody ?: "" }
                val timestamp = messages.first().timestampMillis
                val subscriptionId = intent.getIntExtra("subscription", -1).takeIf { it >= 0 }

                val smsRepo = SmsProviderRepository(context)
                val insertedUri = smsRepo.insertInboxMessage(
                    address = address,
                    body = body,
                    timestampMillis = timestamp,
                    subscriptionId = subscriptionId,
                )
                val messageId = insertedUri?.lastPathSegment?.toLongOrNull()
                val messageUri = insertedUri?.toString()
                    ?: messageId?.let { smsRepo.messageUriForId(it) }
                    ?: return@launch

                // Classification budget: 500ms — fall back to REVIEW on timeout/error.
                val result = withTimeoutOrNull(TimeUnit.MILLISECONDS.toMillis(500)) {
                    DefaultSmsClassifier.classify(
                        SmsInput(
                            sender = address,
                            body = body,
                            timestampMillis = timestamp,
                            subscriptionId = subscriptionId,
                        ),
                    )
                }

                val category = result?.category?.name ?: "TRANSACTION"
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
                )
                app.database.classificationDao().insert(meta)

                withContext(Dispatchers.Main) {
                    val smsAction = result?.action ?: SmsAction.REVIEW
                    NotificationHelper.showMessageNotification(
                        context = context,
                        action = smsAction,
                        address = address,
                        preview = body,
                        messageUri = messageUri,
                    )
                }
            } catch (_: Exception) {
                // Receiver must not crash; metadata write failures are non-fatal.
            } finally {
                pending.finish()
            }
        }
    }
}
