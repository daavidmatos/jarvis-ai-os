# JARVIS Local Assistant

The local assistant turns mobile location requests into evidence-based recommendations instead of generic web search.

## User experience

Example:

> JARVIS, onde tem comida italiana para eu comer?

The mobile UI requests device geolocation only when a local query needs it (or when the user enables `LOCAL`). The current coordinates are sent with that request and are not written into JARVIS long-term memory.

JARVIS then:

1. searches Google Places API (New) around the current device location;
2. collects rating, review count, relevant review samples, photo availability, opening state, distance, website and Google Maps links;
3. computes a conservative evidence score using Bayesian rating shrinkage so a 5.0 venue with only a few reviews does not automatically beat an established venue;
4. keeps **quality** and **confidence** separate: missing data lowers confidence, it is not proof that a restaurant is bad;
5. asks the OpenAI JARVIS Core to make the final concise recommendation using only the returned evidence;
6. exposes Maps, photos and reviews links;
7. remembers the recommended place for that conversation session, not the user's coordinates.

If the user replies `sim`, `me guie`, `abrir rota`, etc., JARVIS returns an `open_url` action. The mobile client opens the Google Maps directions link. Google Maps URLs/Places links are universal links and can open the Maps app when available.

## Configuration

Server secret:

```env
GOOGLE_MAPS_API_KEY=
PLACES_DEFAULT_RADIUS_M=5000
PLACES_MAX_CANDIDATES=5
```

Enable **Places API (New)** for the Google Cloud project tied to the key. Keep the key server-side; never embed it in `apps/web/index.html`.

## Tools

- `places.status` — configuration/readiness.
- `places.search` — read-only evidence-based place discovery around supplied coordinates.

## Privacy

Device location is request-scoped context. The orchestrator explicitly labels it ephemeral and does not call the memory engine with the coordinates. The local assistant persists only the last recommended place per session so a follow-up like “sim, me guie” can open directions.

## Current limitation

The Places API supplies photo metadata and direct Google Maps photo links. JARVIS currently uses photo availability as evidence and can open the photo gallery, but it does **not yet perform computer-vision inspection of every venue photo**. That requires the multimodal vision input layer planned for the voice/mobile assistant stack. Review/rating/location evidence is already evaluated now.
