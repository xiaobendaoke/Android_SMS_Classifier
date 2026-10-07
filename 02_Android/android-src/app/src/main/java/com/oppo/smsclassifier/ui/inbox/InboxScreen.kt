package com.oppo.smsclassifier.ui.inbox

import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalLifecycleOwner
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
import com.oppo.smsclassifier.R
import com.oppo.smsclassifier.SmsAction
import com.oppo.smsclassifier.SmsClassifierApplication
import com.oppo.smsclassifier.data.SmsProviderRepository
import com.oppo.smsclassifier.permission.SmsPermissions
import com.oppo.smsclassifier.ui.common.MessageListItem
import com.oppo.smsclassifier.ui.common.MessageListRow
import com.oppo.smsclassifier.ui.common.toListItem
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun InboxScreen(onOpenDetail: (String) -> Unit) {
    val context = LocalContext.current
    var items by remember { mutableStateOf<List<MessageListItem>>(emptyList()) }
    var loading by remember { mutableStateOf(true) }
    var hasReadSms by remember { mutableStateOf(SmsPermissions.hasReadSms(context)) }
    var refreshKey by remember { mutableIntStateOf(0) }
    val lifecycleOwner = LocalLifecycleOwner.current
    val permissionLauncher = rememberLauncherForActivityResult(
        ActivityResultContracts.RequestMultiplePermissions(),
    ) {
        hasReadSms = SmsPermissions.hasReadSms(context)
        refreshKey++
    }

    DisposableEffect(lifecycleOwner) {
        val observer = LifecycleEventObserver { _, event ->
            if (event == Lifecycle.Event.ON_RESUME) {
                val granted = SmsPermissions.hasReadSms(context)
                if (granted != hasReadSms) {
                    hasReadSms = granted
                    refreshKey++
                }
            }
        }
        lifecycleOwner.lifecycle.addObserver(observer)
        onDispose { lifecycleOwner.lifecycle.removeObserver(observer) }
    }

    LaunchedEffect(refreshKey, hasReadSms) {
        if (!hasReadSms) {
            loading = false
            items = emptyList()
            return@LaunchedEffect
        }
        loading = true
        items = withContext(Dispatchers.IO) {
            val app = context.applicationContext as SmsClassifierApplication
            val smsRepo = SmsProviderRepository(context)
            val dao = app.database.classificationDao()
            smsRepo.queryRecentMessages().mapNotNull { msg ->
                val uri = smsRepo.messageUriForId(msg.id)
                val meta = dao.getByUri(uri)
                // Isolate SUSPECT/REVIEW from the main inbox view.
                when (meta?.action) {
                    SmsAction.SUSPECT.name, SmsAction.REVIEW.name -> null
                    else -> msg.toListItem(meta)
                }
            }
        }
        loading = false
    }

    Scaffold(
        topBar = {
            TopAppBar(title = { Text(stringResource(R.string.tab_inbox)) })
        },
    ) { padding ->
        when {
            !hasReadSms -> Box(
                modifier = Modifier.fillMaxSize().padding(padding),
                contentAlignment = Alignment.Center,
            ) {
                Column(
                    horizontalAlignment = Alignment.CenterHorizontally,
                    verticalArrangement = Arrangement.spacedBy(12.dp),
                    modifier = Modifier.padding(24.dp),
                ) {
                    Text(stringResource(R.string.sms_permission_needed))
                    Button(
                        onClick = {
                            val missing = SmsPermissions.missing(context)
                            if (missing.isNotEmpty()) {
                                permissionLauncher.launch(missing)
                            } else {
                                hasReadSms = true
                                refreshKey++
                            }
                        },
                    ) {
                        Text(stringResource(R.string.sms_permission_grant))
                    }
                }
            }
            loading -> Box(
                modifier = Modifier.fillMaxSize().padding(padding),
                contentAlignment = Alignment.Center,
            ) { CircularProgressIndicator() }
            items.isEmpty() -> Box(
                modifier = Modifier.fillMaxSize().padding(padding),
                contentAlignment = Alignment.Center,
            ) { Text(stringResource(R.string.inbox_empty)) }
            else -> LazyColumn(modifier = Modifier.fillMaxSize().padding(padding)) {
                items(items, key = { it.messageUri }) { item ->
                    MessageListRow(item = item, onClick = { onOpenDetail(item.messageUri) })
                }
            }
        }
    }
}
