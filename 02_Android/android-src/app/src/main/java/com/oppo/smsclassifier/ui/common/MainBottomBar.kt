package com.oppo.smsclassifier.ui.common

import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Assessment
import androidx.compose.material.icons.filled.Edit
import androidx.compose.material.icons.filled.Info
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
    BottomNavItem(NavRoutes.EVALUATION, R.string.tab_evaluation) {
        Icon(Icons.Default.Assessment, contentDescription = null)
    },
    BottomNavItem(NavRoutes.JUDGE, R.string.tab_judge) {
        Icon(Icons.Default.Edit, contentDescription = null)
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
