package com.oppo.smsclassifier

import android.content.Context
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Scaffold
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.navigation.NavType
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.currentBackStackEntryAsState
import androidx.navigation.compose.rememberNavController
import androidx.navigation.navArgument
import com.oppo.smsclassifier.notification.NotificationHelper
import com.oppo.smsclassifier.permission.SmsPermissions
import com.oppo.smsclassifier.role.SmsRoleManager
import com.oppo.smsclassifier.ui.about.AboutScreen
import com.oppo.smsclassifier.ui.common.MainBottomBar
import com.oppo.smsclassifier.ui.common.NavRoutes
import com.oppo.smsclassifier.ui.common.SmsClassifierTheme
import com.oppo.smsclassifier.ui.detail.MessageDetailScreen
import com.oppo.smsclassifier.ui.evaluation.EvaluationScreen
import com.oppo.smsclassifier.ui.inbox.InboxScreen
import com.oppo.smsclassifier.ui.onboarding.OnboardingScreen
import com.oppo.smsclassifier.ui.performance.PerformanceScreen
import com.oppo.smsclassifier.ui.review.ReviewScreen
import com.oppo.smsclassifier.ui.suspect.SuspectScreen

class MainActivity : ComponentActivity() {
    private val roleRequest = registerForActivityResult(
        ActivityResultContracts.StartActivityForResult(),
    ) { /* role result handled on next resume */ }

    private val permissionRequest = registerForActivityResult(
        ActivityResultContracts.RequestMultiplePermissions(),
    ) { /* inbox screens re-check permission on next composition */ }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val missing = SmsPermissions.missing(this)
        if (missing.isNotEmpty() && OnboardingPrefs.isComplete(this)) {
            permissionRequest.launch(missing)
        }
        val deepLinkUri = intent?.getStringExtra(NotificationHelper.EXTRA_MESSAGE_URI)

        setContent {
            SmsClassifierTheme {
                SmsClassifierNav(deepLinkUri = deepLinkUri, onRequestRole = { launchRoleRequest() })
            }
        }
    }

    private fun launchRoleRequest() {
        if (SmsRoleManager.isRoleAvailable(this) && !SmsRoleManager.isRoleHeld(this)) {
            val roleManager = getSystemService(android.app.role.RoleManager::class.java) ?: return
            roleRequest.launch(roleManager.createRequestRoleIntent(android.app.role.RoleManager.ROLE_SMS))
        }
    }
}

@Composable
private fun SmsClassifierNav(
    deepLinkUri: String?,
    onRequestRole: () -> Unit,
) {
    val context = androidx.compose.ui.platform.LocalContext.current
    val navController = rememberNavController()
    val backStack by navController.currentBackStackEntryAsState()
    val currentRoute = backStack?.destination?.route?.substringBefore('?')
    val showBottomBar = currentRoute in setOf(
        NavRoutes.INBOX,
        NavRoutes.SUSPECT,
        NavRoutes.REVIEW,
        NavRoutes.EVALUATION,
        NavRoutes.PERFORMANCE,
        NavRoutes.ABOUT,
    )
    val startDestination = if (OnboardingPrefs.isComplete(context)) {
        deepLinkUri?.let { NavRoutes.detail(it) } ?: NavRoutes.INBOX
    } else {
        NavRoutes.ONBOARDING
    }

    Scaffold(
        bottomBar = {
            if (showBottomBar) {
                MainBottomBar(
                    currentRoute = currentRoute,
                    onNavigate = { route ->
                        navController.navigate(route) {
                            popUpTo(NavRoutes.INBOX) { saveState = true }
                            launchSingleTop = true
                            restoreState = true
                        }
                    },
                )
            }
        },
    ) { padding ->
        NavHost(
            navController = navController,
            startDestination = startDestination,
            modifier = Modifier.padding(padding),
        ) {
            composable(NavRoutes.ONBOARDING) {
                OnboardingScreen(
                    onContinue = {
                        OnboardingPrefs.markComplete(context)
                        navController.navigate(NavRoutes.INBOX) {
                            popUpTo(NavRoutes.ONBOARDING) { inclusive = true }
                        }
                    },
                    onRequestRole = onRequestRole,
                )
            }
            composable(NavRoutes.INBOX) {
                InboxScreen(
                    onOpenDetail = { uri ->
                        navController.navigate(NavRoutes.detail(uri))
                    },
                )
            }
            composable(NavRoutes.SUSPECT) {
                SuspectScreen(
                    onOpenDetail = { uri ->
                        navController.navigate(NavRoutes.detail(uri))
                    },
                )
            }
            composable(NavRoutes.REVIEW) {
                ReviewScreen(
                    onOpenDetail = { uri ->
                        navController.navigate(NavRoutes.detail(uri))
                    },
                )
            }
            composable(
                route = NavRoutes.DETAIL,
                arguments = listOf(navArgument("messageUri") { type = NavType.StringType }),
            ) { entry ->
                val encoded = entry.arguments?.getString("messageUri") ?: return@composable
                MessageDetailScreen(messageUri = NavRoutes.decodeMessageUri(encoded))
            }
            composable(NavRoutes.EVALUATION) { EvaluationScreen() }
            composable(NavRoutes.PERFORMANCE) { PerformanceScreen() }
            composable(NavRoutes.ABOUT) { AboutScreen() }
        }
    }
}

private object OnboardingPrefs {
    private const val PREFS = "sms_classifier_prefs"
    private const val KEY_COMPLETE = "onboarding_complete"

    fun isComplete(context: Context): Boolean =
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
            .getBoolean(KEY_COMPLETE, false)

    fun markComplete(context: Context) {
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
            .edit()
            .putBoolean(KEY_COMPLETE, true)
            .apply()
    }
}
