package com.oppo.smsclassifier.service

import android.app.Service
import android.content.Intent
import android.os.IBinder
import android.telephony.SmsManager
import android.util.Log

/**
 * Minimal RESPOND_VIA_MESSAGE service for default SMS role qualification.
 */
class RespondViaMessageService : Service() {
    override fun onBind(intent: Intent?): IBinder? = null

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        val data = intent?.data
        val address = data?.schemeSpecificPart
        val message = intent?.getStringExtra(Intent.EXTRA_TEXT)
        if (!address.isNullOrBlank() && !message.isNullOrBlank()) {
            try {
                SmsManager.getDefault().sendTextMessage(address, null, message, null, null)
            } catch (e: Exception) {
                Log.w(TAG, "respond-via-message failed", e)
            }
        }
        stopSelf(startId)
        return START_NOT_STICKY
    }

    companion object {
        private const val TAG = "RespondViaMessage"
    }
}
