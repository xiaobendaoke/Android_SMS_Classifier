package com.oppo.smsclassifier.data

import android.content.ContentValues
import android.content.Context
import android.net.Uri
import android.provider.Telephony

/**
 * Helpers to read/write [Telephony.Sms]. Message body is stored only in the system
 * SMS content provider — this repository never persists body text in app storage.
 */
class SmsProviderRepository(private val context: Context) {

    data class SmsMessageDisplay(
        val id: Long,
        val address: String,
        val body: String,
        val date: Long,
        val threadId: Long,
    )

    /**
     * Inserts an inbound message into the system SMS inbox provider.
     * Body lives only in Telephony.Sms; callers should store classification metadata separately.
     */
    fun insertInboxMessage(
        address: String,
        body: String,
        timestampMillis: Long,
        subscriptionId: Int? = null,
    ): Uri? {
        val values = ContentValues().apply {
            put(Telephony.Sms.ADDRESS, address)
            put(Telephony.Sms.BODY, body)
            put(Telephony.Sms.DATE, timestampMillis)
            put(Telephony.Sms.READ, 0)
            put(Telephony.Sms.SEEN, 0)
            put(Telephony.Sms.TYPE, Telephony.Sms.MESSAGE_TYPE_INBOX)
            subscriptionId?.let { put(Telephony.Sms.SUBSCRIPTION_ID, it) }
        }
        return context.contentResolver.insert(Telephony.Sms.Inbox.CONTENT_URI, values)
    }

    /**
     * Reads recent inbox messages from the system provider for in-memory UI display.
     * Body is returned here only for rendering and is not written to Room.
     */
    fun queryRecentMessages(limit: Int = 100): List<SmsMessageDisplay> {
        val results = mutableListOf<SmsMessageDisplay>()
        val projection = arrayOf(
            Telephony.Sms._ID,
            Telephony.Sms.ADDRESS,
            Telephony.Sms.BODY,
            Telephony.Sms.DATE,
            Telephony.Sms.THREAD_ID,
        )
        return try {
            context.contentResolver.query(
                Telephony.Sms.Inbox.CONTENT_URI,
                projection,
                null,
                null,
                "${Telephony.Sms.DATE} DESC LIMIT $limit",
            )?.use { cursor ->
                val idIdx = cursor.getColumnIndexOrThrow(Telephony.Sms._ID)
                val addressIdx = cursor.getColumnIndexOrThrow(Telephony.Sms.ADDRESS)
                val bodyIdx = cursor.getColumnIndexOrThrow(Telephony.Sms.BODY)
                val dateIdx = cursor.getColumnIndexOrThrow(Telephony.Sms.DATE)
                val threadIdx = cursor.getColumnIndexOrThrow(Telephony.Sms.THREAD_ID)
                while (cursor.moveToNext()) {
                    results += SmsMessageDisplay(
                        id = cursor.getLong(idIdx),
                        address = cursor.getString(addressIdx) ?: "",
                        body = cursor.getString(bodyIdx) ?: "",
                        date = cursor.getLong(dateIdx),
                        threadId = cursor.getLong(threadIdx),
                    )
                }
            }
            results
        } catch (_: SecurityException) {
            // READ_SMS not granted yet — callers should request runtime permission.
            emptyList()
        }
    }

    fun messageUriForId(messageId: Long): String =
        "${Telephony.Sms.CONTENT_URI}/$messageId"
}
