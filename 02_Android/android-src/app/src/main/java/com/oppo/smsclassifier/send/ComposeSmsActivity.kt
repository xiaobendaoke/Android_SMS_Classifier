package com.oppo.smsclassifier.send

import android.Manifest
import android.content.pm.PackageManager
import android.os.Bundle
import android.telephony.SmsManager
import android.widget.Toast
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Button
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import androidx.core.content.ContextCompat
import com.oppo.smsclassifier.R
import com.oppo.smsclassifier.ui.common.SmsClassifierTheme

class ComposeSmsActivity : ComponentActivity() {
    private val requestPermission = registerForActivityResult(
        ActivityResultContracts.RequestPermission(),
    ) { granted ->
        if (!granted) {
            Toast.makeText(this, R.string.compose_permission_denied, Toast.LENGTH_SHORT).show()
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val initialAddress = intent?.data?.schemeSpecificPart ?: ""

        setContent {
            SmsClassifierTheme {
                Surface(modifier = Modifier.fillMaxSize()) {
                    var address by rememberSaveable { mutableStateOf(initialAddress) }
                    var body by rememberSaveable { mutableStateOf("") }

                    Column(modifier = Modifier.padding(16.dp)) {
                        Text(
                            text = stringResource(R.string.compose_title),
                            style = MaterialTheme.typography.headlineSmall,
                        )
                        Spacer(modifier = Modifier.height(16.dp))
                        OutlinedTextField(
                            value = address,
                            onValueChange = { address = it },
                            label = { Text(stringResource(R.string.compose_address)) },
                            modifier = Modifier.fillMaxWidth(),
                            singleLine = true,
                        )
                        Spacer(modifier = Modifier.height(8.dp))
                        OutlinedTextField(
                            value = body,
                            onValueChange = { body = it },
                            label = { Text(stringResource(R.string.compose_body)) },
                            modifier = Modifier.fillMaxWidth(),
                            minLines = 4,
                        )
                        Spacer(modifier = Modifier.height(16.dp))
                        Button(
                            onClick = { sendSms(address, body) },
                            modifier = Modifier.fillMaxWidth(),
                            enabled = address.isNotBlank() && body.isNotBlank(),
                        ) {
                            Text(stringResource(R.string.compose_send))
                        }
                    }
                }
            }
        }
    }

    private fun sendSms(address: String, body: String) {
        if (ContextCompat.checkSelfPermission(this, Manifest.permission.SEND_SMS)
            != PackageManager.PERMISSION_GRANTED
        ) {
            requestPermission.launch(Manifest.permission.SEND_SMS)
            return
        }
        try {
            SmsManager.getDefault().sendTextMessage(address, null, body, null, null)
            Toast.makeText(this, R.string.compose_sent, Toast.LENGTH_SHORT).show()
            finish()
        } catch (e: Exception) {
            Toast.makeText(this, R.string.compose_send_failed, Toast.LENGTH_SHORT).show()
        }
    }
}
