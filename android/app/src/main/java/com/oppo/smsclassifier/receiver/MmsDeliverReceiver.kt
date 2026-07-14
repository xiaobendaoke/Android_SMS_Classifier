package com.oppo.smsclassifier.receiver

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import com.oppo.smsclassifier.SmsAction
import com.oppo.smsclassifier.SmsClassifierApplication
import com.oppo.smsclassifier.data.ClassificationMeta
import com.oppo.smsclassifier.notification.NotificationHelper
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.launch
import org.json.JSONArray

/**
 * WAP_PUSH_DELIVER (MMS) receiver — does not drop MMS; stores placeholder metadata only.
 * MMS body/content is not logged or persisted in app storage.
 */
class MmsDeliverReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        val pending = goAsync()
        val app = context.applicationContext as SmsClassifierApplication
        CoroutineScope(SupervisorJob() + Dispatchers.IO).launch {
            try {
                val placeholderUri = "mms://placeholder/${System.currentTimeMillis()}"
                val meta = ClassificationMeta(
                    messageUri = placeholderUri,
                    messageId = null,
                    threadId = null,
                    category = "TRANSACTION",
                    action = SmsAction.REVIEW.name,
                    confidence = 0f,
                    reasonCode = "MMS_PLACEHOLDER",
                    ruleIdsJson = JSONArray().toString(),
                    modelVersion = "n/a",
                    rulesVersion = "n/a",
                    createdAt = System.currentTimeMillis(),
                )
                app.database.classificationDao().insert(meta)
                NotificationHelper.showMmsPlaceholderNotification(context)
            } catch (_: Exception) {
                // Non-fatal
            } finally {
                pending.finish()
            }
        }
    }
}
