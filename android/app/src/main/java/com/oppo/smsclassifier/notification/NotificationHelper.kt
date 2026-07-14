package com.oppo.smsclassifier.notification

import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.os.Build
import androidx.core.app.NotificationCompat
import com.oppo.smsclassifier.MainActivity
import com.oppo.smsclassifier.R
import com.oppo.smsclassifier.SmsAction

object NotificationHelper {
    private const val CHANNEL_INBOX = "sms_inbox"
    private const val CHANNEL_SUSPECT = "sms_suspect"
    private const val CHANNEL_MMS = "sms_mms"

    fun showMessageNotification(
        context: Context,
        action: SmsAction,
        address: String,
        preview: String,
        messageUri: String,
    ) {
        ensureChannels(context)
        val channelId = when (action) {
            SmsAction.SUSPECT -> CHANNEL_SUSPECT
            SmsAction.REVIEW -> CHANNEL_INBOX
            SmsAction.INBOX -> CHANNEL_INBOX
        }
        val title = when (action) {
            SmsAction.SUSPECT -> context.getString(R.string.notification_suspect_title)
            SmsAction.REVIEW -> context.getString(R.string.notification_review_title)
            SmsAction.INBOX -> context.getString(R.string.notification_inbox_title)
        }
        val notificationId = messageUri.hashCode()
        val pendingIntent = PendingIntent.getActivity(
            context,
            notificationId,
            Intent(context, MainActivity::class.java).apply {
                flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP
                putExtra(EXTRA_MESSAGE_URI, messageUri)
            },
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
        )
        val notification = NotificationCompat.Builder(context, channelId)
            .setSmallIcon(android.R.drawable.ic_dialog_email)
            .setContentTitle("$title — $address")
            .setContentText(preview.take(80))
            .setContentIntent(pendingIntent)
            .setAutoCancel(true)
            .build()
        val manager = context.getSystemService(NotificationManager::class.java)
        manager.notify(notificationId, notification)
    }

    fun showMmsPlaceholderNotification(context: Context) {
        ensureChannels(context)
        val notification = NotificationCompat.Builder(context, CHANNEL_MMS)
            .setSmallIcon(android.R.drawable.ic_dialog_email)
            .setContentTitle(context.getString(R.string.notification_mms_title))
            .setContentText(context.getString(R.string.notification_mms_body))
            .setAutoCancel(true)
            .build()
        context.getSystemService(NotificationManager::class.java)
            .notify(CHANNEL_MMS.hashCode(), notification)
    }

    private fun ensureChannels(context: Context) {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) return
        val manager = context.getSystemService(NotificationManager::class.java)
        listOf(
            CHANNEL_INBOX to context.getString(R.string.channel_inbox),
            CHANNEL_SUSPECT to context.getString(R.string.channel_suspect),
            CHANNEL_MMS to context.getString(R.string.channel_mms),
        ).forEach { (id, name) ->
            manager.createNotificationChannel(
                NotificationChannel(id, name, NotificationManager.IMPORTANCE_DEFAULT),
            )
        }
    }

    const val EXTRA_MESSAGE_URI = "message_uri"
}
