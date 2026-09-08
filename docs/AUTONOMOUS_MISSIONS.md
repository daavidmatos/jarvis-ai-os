# Autonomous Missions

JARVIS must support goal-level missions rather than only request/response workflows.

Example: `Create the best advertising campaign for Fuel and execute it.`

## Mission lifecycle

1. UNDERSTAND — collect company context, connected-account data, memory, web evidence and current performance.
2. DESIGN — choose the strategy, channels, audiences, offer, creative system, measurement plan and execution DAG.
3. BLOCKERS — ask only for information that is genuinely required to continue (for example a spend ceiling or missing account authorization).
4. APPROVAL — present one concise proposed mission when standing permission does not already cover it.
5. EXECUTE — autonomously run approved low/medium-risk steps and approved high-impact steps within the mission's permission envelope.
6. MONITOR — watch events, metrics, inboxes, comments, errors, spend and conversions.
7. OPTIMIZE — make reversible changes automatically inside the authorized envelope.
8. ESCALATE — contact the user only for meaningful exceptions, policy conflicts, budget expansion or decisions outside standing permission.
9. REPORT — proactively summarize what changed, what JARVIS did and why.

## Approval model

Approval is not per-click. The user can approve an entire mission envelope, for example:

- objective: acquire Fuel customers
- channels: Google Ads + Instagram organic
- daily ad-spend ceiling: R$ 50
- total campaign ceiling: R$ 500
- allow autonomous creative drafts/publishing: yes
- allow autonomous bid/budget reallocations inside ceiling: yes
- allow customer coupon issuance under configured campaign rules: yes
- require confirmation for spend above ceiling, destructive account changes, legal claims or new external commitments

Standing permissions can persist for future missions. Revocation must be immediate.

## Marketing mission example

Input: `Create a campaign where customers who post Fuel and tag us receive a discount.`

JARVIS should be able to:

- inspect current brand/product context and prior campaign performance;
- decide campaign mechanics and anti-abuse rules;
- choose coupon value and duration inside a configured promotion policy, or ask once if no such policy exists;
- create campaign copy, story/feed/reel creative briefs and image/video generation jobs;
- publish/schedule assets through connected social tools when authorized;
- monitor Instagram mentions/tags through the approved Meta/Instagram API integration;
- validate campaign eligibility;
- create/assign a single-use coupon through Fuel's commerce connector;
- send the customer the coupon through an allowed channel;
- log every action and measure redemptions, CAC/revenue impact and abuse signals;
- adjust creative/copy and campaign rules inside the approved mission envelope.

## Google Ads mission example

Input: `Create a Google Ads campaign to sell Fuel.`

JARVIS should research and decide campaign structure, keywords/audiences, landing page, ad copy, exclusions, conversion measurement and bidding approach. It must ask for a spend limit if neither the mission nor standing permissions provide one. It can create campaign resources in PAUSED state during preparation. Enabling spend or increasing spend must stay inside the user's approved budget envelope.

## Interaction principle

JARVIS should prefer decisions over questions. Ask only when a missing fact materially blocks execution or falls outside the user's authorization. Questions that can be answered safely from connected data, memory, web research or reasonable reversible defaults should be resolved autonomously.
