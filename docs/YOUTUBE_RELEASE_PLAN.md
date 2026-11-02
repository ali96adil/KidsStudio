# YouTube release planning — no network writes

`kidsstudio.youtube_release_plan.plan_visibility_change` prepares a
**non-executable** decision report for a single episode and YouTube video ID.

The plan requires:
- Latest owner creative review = `approved`
- Latest independent release decision = `release_authorized`
- Current privacy supplied to planner = `private`
- Valid 11-character YouTube video ID

It never calls Google/YouTube and cannot publish. The `current_privacy`
parameter is a caller-provided observation, **not verified YouTube state**.
A true `ready_for_manual_release` is not authorization to skip owner login,
video ownership checks, or a fresh YouTube API privacy check.

Before implementing an actual public visibility change:
1. Use authenticated YouTube Data API to verify video belongs to the
   connected channel and is still private.
2. Verify the episode-to-video mapping is trusted and immutable for the action.
3. Re-read both owner decisions immediately before changing visibility.
4. Require authenticated owner confirmation bound to this exact video.
5. Log request, response, errors and resulting visibility without secrets.
6. Fail closed on timeouts, API errors, revoked decisions or mismatched IDs.

The existing Pi private-upload pipeline must remain private until all
production controls are verified.
