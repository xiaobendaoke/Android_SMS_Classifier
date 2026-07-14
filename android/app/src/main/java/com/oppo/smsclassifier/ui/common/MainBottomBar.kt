package com.oppo.smsclassifier.ui.common

import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Assessment
import androidx.compose.material.icons.filled.Home
import androidx.compose.material.icons.filled.Info
import androidx.compose.material.icons.filled.Report
import androidx.compose.material.icons.filled.Science
import androidx.compose.material.icons.filled.Speed
import androidx.compose.material.icons.filled.Visibility
import androidx.compose.material3.Icon
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.res.stringResource
import com.oppo.smsclassifier.R

data class BottomNavItem(
    val route: String,
    val labelRes: Int,
    val icon: @Composable () -> Unit,
)

val mainBottomNavItems = listOf(
    BottomNavItem(NavRoutes.INBOX, R.string.tab_inbox) {
        Icon(Icons.Default.Home, contentDescription = null)
    },
    BottomNavItem(NavRoutes.SUSPECT, R.string.tab_suspect) {
        Icon(Icons.Default.Report, contentDescription = null)
    },
    BottomNavItem(NavRoutes.REVIEW, R.string.tab_review) {
        Icon(Icons.Default.Visibility, contentDescription = null)
    },
    BottomNavItem(NavRoutes.EVALUATION, R.string.tab_evaluation) {
        Icon(Icons.Default.Science, contentDescription = null)
    },
    BottomNavItem(NavRoutes.PERFORMANCE, R.string.tab_performance) {
        Icon(Icons.Default.Speed, contentDescription = null)
    },
    BottomNavItem(NavRoutes.ABOUT, R.string.tab_about) {
        Icon(Icons.Default.Info, contentDescription = null)
    },
)

@Composable
fun MainBottomBar(
    currentRoute: String?,
    onNavigate: (String) -> Unit,
) {
    NavigationBar {
        mainBottomNavItems.forEach { item ->
            NavigationBarItem(
                selected = currentRoute == item.route,
                onClick = { onNavigate(item.route) },
                icon = item.icon,
                label = { Text(stringResource(item.labelRes)) },
            )
        }
    }
}
