# Google Workspace integration

JARVIS v0.4 starts the Google Workspace layer with Gmail and Google Calendar.

## Goals

- One-time Google OAuth authorization.
- Offline access via refresh token so JARVIS can operate while the user is absent.
- Gmail search/read/draft/send tools.
- Calendar read/create tools.
- Gmail mailbox monitoring through Gmail `users.watch` and Google Cloud Pub/Sub.
- Calendar monitoring through notification channels and an HTTPS webhook.
- Convert incoming Google changes into persistent `proactive_events` that a notifier/automation worker can later evaluate and surface to the user.

## Required server settings

- `PUBLIC_BASE_URL`
- `GOOGLE_OAUTH_CLIENT_ID`
- `GOOGLE_OAUTH_CLIENT_SECRET`
- `GMAIL_PUBSUB_TOPIC` for Gmail push monitoring
- `GOOGLE_PUBSUB_WEBHOOK_SECRET` for the Pub/Sub push endpoint

OAuth callback:

`<PUBLIC_BASE_URL>/v1/integrations/google/callback`

Calendar webhook:

`<PUBLIC_BASE_URL>/v1/webhooks/google/calendar`

Gmail Pub/Sub push endpoint:

`<PUBLIC_BASE_URL>/v1/webhooks/google/gmail?token=<GOOGLE_PUBSUB_WEBHOOK_SECRET>`

## Google Cloud configuration

1. Create a Google Cloud project.
2. Enable Gmail API, Google Calendar API, and Cloud Pub/Sub API.
3. Configure OAuth consent and create an OAuth 2.0 Web Application client.
4. Register the JARVIS callback URL as an authorized redirect URI.
5. Create a Pub/Sub topic for Gmail events.
6. Grant `gmail-api-push@system.gserviceaccount.com` permission to publish to the topic.
7. Create a push subscription targeting the JARVIS Gmail webhook.

## Risk policy

Read operations are LOW risk and can be selected autonomously.

Creating a Gmail draft is MEDIUM risk and can be performed by the current autonomous policy.

Sending email and creating Calendar events are HIGH risk and remain approval-gated. A future standing-permission layer will allow the user to grant durable policies such as "send routine replies from this mailbox" or "schedule meetings inside these hours" without removing the audit trail or global kill switch.

## Monitoring lifecycle

`GoogleMonitoringService` runs while the server is alive. Gmail watches are renewed roughly daily. Calendar channels are renewed near expiration. Webhooks create persistent proactive events; later versions will feed these events into the JARVIS decision engine and mobile notification/voice layer.
