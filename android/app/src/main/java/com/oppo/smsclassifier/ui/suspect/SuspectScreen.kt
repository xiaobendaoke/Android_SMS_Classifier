package com.oppo.smsclassifier.ui.suspect

import androidx.compose.foundation.layout.Box
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
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import com.oppo.smsclassifier.R
import com.oppo.smsclassifier.SmsAction
import com.oppo.smsclassifier.SmsClassifierApplication
import com.oppo.smsclassifier.data.ClassificationMeta
import com.oppo.smsclassifier.data.SmsProviderRepository
import com.oppo.smsclassifier.ui.common.MessageListItem
import com.oppo.smsclassifier.ui.common.MessageListRow
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun SuspectScreen(onOpenDetail: (String) -> Unit) {
    val context = LocalContext.current
    var items by remember { mutableStateOf<List<MessageListItem>>(emptyList()) }
    var loading by remember { mutableStateOf(true) }
    var refreshKey by remember { mutableStateOf(0) }

    LaunchedEffect(refreshKey) {
        loading = true
        items = withContext(Dispatchers.IO) {
            loadSuspectItems(context)
        }
        loading = false
    }

    Scaffold(
        topBar = {
            TopAppBar(title = { Text(stringResource(R.string.tab_suspect)) })
        },
    ) { padding ->
        when {
            loading -> Box(
                modifier = Modifier.fillMaxSize().padding(padding),
                contentAlignment = Alignment.Center,
            ) { CircularProgressIndicator() }
            items.isEmpty() -> Box(
                modifier = Modifier.fillMaxSize().padding(padding),
                contentAlignment = Alignment.Center,
            ) { Text(stringResource(R.string.suspect_empty)) }
            else -> LazyColumn(modifier = Modifier.fillMaxSize().padding(padding)) {
                items(items, key = { it.messageUri }) { item ->
                    MessageListRow(
                        item = item,
                        onClick = { onOpenDetail(item.messageUri) },
                        trailing = {
                            Button(
                                onClick = {
                                    restoreToInbox(context, item.meta) { refreshKey++ }
                                },
                                modifier = Modifier.padding(top = 8.dp),
                            ) {
                                Text(stringResource(R.string.suspect_restore))
                            }
                        },
                    )
                }
            }
        }
    }
}

private suspend fun loadSuspectItems(context: android.content.Context): List<MessageListItem> {
    val app = context.applicationContext as SmsClassifierApplication
    val dao = app.database.classificationDao()
    val smsRepo = SmsProviderRepository(context)
    val metas = dao.listByAction(SmsAction.SUSPECT.name)
    val messages = smsRepo.queryRecentMessages(500).associateBy { smsRepo.messageUriForId(it.id) }
    return metas.mapNotNull { meta ->
        val msg = messages[meta.messageUri] ?: return@mapNotNull null
        MessageListItem(
            messageUri = meta.messageUri,
            address = msg.address,
            body = msg.body,
            date = msg.date,
            meta = meta,
        )
    }
}

private fun restoreToInbox(
    context: android.content.Context,
    meta: ClassificationMeta?,
    onDone: () -> Unit,
) {
    if (meta == null) return
    CoroutineScope(Dispatchers.IO).launch {
        val app = context.applicationContext as SmsClassifierApplication
        app.database.classificationDao().update(
            meta.copy(action = SmsAction.INBOX.name),
        )
        withContext(Dispatchers.Main) { onDone() }
    }
}
