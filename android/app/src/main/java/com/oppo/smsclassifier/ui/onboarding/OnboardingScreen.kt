package com.oppo.smsclassifier.ui.onboarding

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import com.oppo.smsclassifier.R
import com.oppo.smsclassifier.role.SmsRoleManager

@Composable
fun OnboardingScreen(
    onContinue: () -> Unit,
    onRequestRole: () -> Unit,
) {
    val context = LocalContext.current
    val roleHeld = SmsRoleManager.isRoleHeld(context)

    Column(
        modifier = Modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
            .padding(24.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        Text(
            text = stringResource(R.string.onboarding_title),
            style = MaterialTheme.typography.headlineMedium,
        )
        Text(
            text = stringResource(R.string.onboarding_privacy),
            style = MaterialTheme.typography.bodyLarge,
        )
        Text(
            text = stringResource(R.string.onboarding_role_hint),
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.secondary,
        )
        Spacer(modifier = Modifier.height(8.dp))
        Button(
            onClick = onRequestRole,
            modifier = Modifier.fillMaxWidth(),
            enabled = !roleHeld,
        ) {
            Text(
                if (roleHeld) {
                    stringResource(R.string.onboarding_role_granted)
                } else {
                    stringResource(R.string.onboarding_request_role)
                },
            )
        }
        Button(
            onClick = onContinue,
            modifier = Modifier.fillMaxWidth(),
        ) {
            Text(stringResource(R.string.onboarding_continue))
        }
    }
}
