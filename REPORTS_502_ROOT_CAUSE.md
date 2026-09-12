# Reports Detail 502 Root Cause

Date: 2026-08-26  
Runtime: integration  
Flow: Reports → `STEINS;GATE RE:BOOT` (`app_id=4012810`)

## Reproduction

The exact Reports detail flow was opened in the integration runtime and network responses were recorded with CodexShared Chromium.

Two failed responses were observed. They are duplicate requests for the same external capability:

| Request | Method | Params | Status |
|---|---|---|---|
| `http://127.0.0.1:3000/api/steam/achievements/4012810?limit=20` | GET | `limit=20` | 502 |
| `http://127.0.0.1:3000/api/steam/achievements/4012810?limit=20` | GET | `limit=20` | 502 |

Response body for both:

```json
{"detail":"Request to https://api.steampowered.com/ISteamUserStats/GetSchemaForGame/v2 failed with status code 400: <html><head><title>Bad Request</title></head><body><h1>Bad Request</h1>Required parameter 'key' is missing</body></html>"}
```

The duplicate is the same request issued twice during the mounted Reports detail flow; it does not represent two different failed dependencies.

## Trace

- Frontend request: `GET /api/steam/achievements/4012810?limit=20`
- Backend route: `GET /steam/achievements/{app_id}` in `apps/api/senti_next/routes/games.py`
- Backend implementation: `fetch_achievements_with_stats(4012810)` in `apps/api/senti_next/steam_api.py`
- Upstream calls: Steam global achievement percentages and Steam achievement schema. The failing upstream call is `https://api.steampowered.com/ISteamUserStats/GetSchemaForGame/v2`.
- Backend log: `Steam API error fetching achievements for app 4012810: ... status code 400 ... Required parameter 'key' is missing`
- Uvicorn access log: `GET /steam/achievements/4012810?limit=20 HTTP/1.1` → `502 Bad Gateway` (twice)
- External dependency: yes. The failing request depends on Steam Web API and requires a Steam Web API key.

Other Reports detail requests were not the cause of these 502s: analysis, report months, player count, news, and version-event requests returned successfully in the same reproduction. News rendered the truthful `No recent updates available` state.

## Root-cause classification

Classification: **D — external Steam/API unavailable**.

The immediate upstream cause is a missing Steam Web API key. The backend route is behaving as a proxy and translates the upstream 400 into 502. This is not a frontend URL/routing issue, malformed internal data, or a Reports database failure. The integration process also logged an unrelated FTS startup integrity warning; it did not cause this endpoint response.

## Safe closure

No credential, backend proxy behavior, or analytical data was fabricated or changed. The frontend `AchievementsWidget` now renders:

`Player progression temporarily unavailable.`

when this external request fails. The component no longer silently disappears after the request error, and the page does not remain in an indefinite loading state.

## Verification

- Reports detail screenshot: `artifacts/screenshots/reports-detail-502-closed.png`
- The visible page contains the explicit unavailable state and no visible loading skeleton for achievements.
- No page errors or hydration errors were observed after excluding the browser's pre-existing invalid CSP `/api` warning.
- The known remaining 502s are the documented external Steam proxy failure above; there were no unexpected internal Reports API 502s.

