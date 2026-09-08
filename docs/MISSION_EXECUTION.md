# JARVIS Autonomous Mission Execution

JARVIS v0.5 treats substantial goals as persistent missions rather than one-shot chat turns.

## Mission flow

1. User gives an outcome, e.g. `Create and run a Fuel acquisition campaign`.
2. OpenAI Mission Director researches/plans and creates a `MissionEnvelope`.
3. JARVIS asks only for blockers it cannot safely infer (for paid ads, usually the spend ceiling if no standing permission exists).
4. User gives one approval (`OK`).
5. Mission Executor runs the plan, uses connected tools, records every tool result, and stays inside the approved envelope.
6. Monitoring/optimization phases remain in `monitoring` state and receive events through the proactive event queue.

The mission envelope can authorize publishing, external messages, commerce mutations and paid spend. Paid spend is additionally bounded by a daily/total ceiling. A normal high-risk tool still requires per-action approval outside an approved mission.

## Standing permissions

`/v1/permissions` stores optional reusable mandates such as:

- publish to Fuel Instagram;
- respond to customer messages;
- create Fuel coupons;
- manage Google Ads up to R$ 50/day and R$ 1,000 total.

Standing permissions are private server state and are never committed to Git.

## Instagram / Meta

Configure server secrets:

- `META_ACCESS_TOKEN`
- `META_INSTAGRAM_USER_ID`
- `META_APP_SECRET`
- `META_WEBHOOK_VERIFY_TOKEN`
- optionally `META_GRAPH_VERSION`

Tools:

- `instagram.status`
- `instagram.tagged_media`
- `instagram.publish_photo`

Webhook: `/v1/webhooks/meta/instagram`

Instagram publishing requires a publicly reachable HTTPS image URL. JARVIS-generated assets are exposed under `/v1/assets/{opaque-filename}` when the server has an HTTPS `PUBLIC_BASE_URL`.

## Google Ads

The single Google OAuth consent surface is extended with the `https://www.googleapis.com/auth/adwords` scope when the Ads connector is loaded.

Additional server configuration:

- `GOOGLE_ADS_DEVELOPER_TOKEN`
- `GOOGLE_ADS_CUSTOMER_ID`
- optional `GOOGLE_ADS_LOGIN_CUSTOMER_ID`
- `GOOGLE_ADS_API_VERSION` (defaults to `v25`)

Tools:

- `google_ads.status`
- `google_ads.performance`
- `google_ads.create_search_campaign` (creates PAUSED)
- `google_ads.set_campaign_status`

Creation builds budget + Search campaign + ad group + keywords + responsive search ad. Enabling a campaign is separately budget-gated.

## Creative generation

`creative.generate_image` uses the configured OpenAI image model (`OPENAI_IMAGE_MODEL`, default `gpt-image-2`) and saves artifacts to `workspace/generated/`.

## Fuel/Lovable contract

The connector intentionally does not access Lovable/Supabase internals directly. The Fuel application should expose an authenticated stable contract:

- `GET /jarvis/orders`
- `GET /jarvis/analytics/sales`
- `POST /jarvis/coupons`

Configure `FUEL_API_BASE_URL`, `FUEL_API_TOKEN`, and optionally `FUEL_WEBHOOK_SECRET`.

Fuel can send order/payment/customer events to `/v1/webhooks/fuel`; JARVIS adds them to the proactive event queue.

## What still needs external account setup

Code support does not create third-party credentials automatically. Real execution requires the owner to connect/authorize each external account and, for Google Ads, obtain a developer token. Meta webhook subscriptions and permissions must also be enabled in the Meta app configuration. Once credentials exist, missions use them automatically within the user's approved scope.
