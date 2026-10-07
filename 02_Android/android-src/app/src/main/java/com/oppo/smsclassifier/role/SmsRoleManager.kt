package com.oppo.smsclassifier.role

import android.app.Activity
import android.app.role.RoleManager
import android.content.Context
import android.os.Build

/**
 * Helper for requesting ROLE_SMS (Android 10+).
 */
object SmsRoleManager {
    const val REQUEST_SMS_ROLE = 1001

    fun isRoleAvailable(context: Context): Boolean {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.Q) return false
        val roleManager = context.getSystemService(RoleManager::class.java) ?: return false
        return roleManager.isRoleAvailable(RoleManager.ROLE_SMS)
    }

    fun isRoleHeld(context: Context): Boolean {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.Q) return false
        val roleManager = context.getSystemService(RoleManager::class.java) ?: return false
        return roleManager.isRoleHeld(RoleManager.ROLE_SMS)
    }

    fun requestRole(activity: Activity) {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.Q) return
        val roleManager = activity.getSystemService(RoleManager::class.java) ?: return
        if (roleManager.isRoleAvailable(RoleManager.ROLE_SMS) &&
            !roleManager.isRoleHeld(RoleManager.ROLE_SMS)
        ) {
            activity.startActivityForResult(
                roleManager.createRequestRoleIntent(RoleManager.ROLE_SMS),
                REQUEST_SMS_ROLE,
            )
        }
    }
}
