# Raspberry Pi: YouTube OAuth preparation

This is a **read-only inspection prerequisite**, not a publishing setup.

## One-time owner authorization

1. In Google Cloud Console, create or select a project and enable YouTube Data API v3.
2. Configure an OAuth consent screen and an OAuth client appropriate for a
   local/desktop authorization flow. Configure the consent screen's testing
   or production status and test users as appropriate.
3. Use a trusted local authorization flow to obtain a refresh token for the
   correct YouTube channel. For video status inspection use a read-only
   YouTube scope where supported (for example
   `https://www.googleapis.com/auth/youtube.readonly`).
4. Store client ID, client secret and refresh token on the Pi **outside**
   the repository, in a file owned by the service user with mode `0600`.
   Do not paste secrets into chat, CI logs, GitHub issues or commit history.
5. Exchange the refresh token using
   `kidsstudio.youtube_oauth_token.refresh_access_token`; pass the
   short-lived access token directly to
   `kidsstudio.youtube_release_inspection.inspect_release`.
6. Supply the expected YouTube channel ID from trusted owner configuration.
   Verify the returned video ID and channel ID match before considering any
   release eligibility.

The OAuth consent flow and secure Pi secret provisioning are **not yet
implemented** in this repository. The refresh module requires an existing
refresh token. YouTube account and channel access have not been tested live.

Security: do not log OAuth request bodies, access tokens or refresh tokens.
Do not expose these modules via unauthenticated LAN endpoints. Google may
revoke or expire refresh tokens; handle refresh failure as a closed gate.
