# Kids Studio: review versus public release

There are two independent owner decisions:

1. **Creative review** (owner_review_store): needs_review,
   changes_requested, approved. The review page writes only this decision.
2. **Public release authorization** (owner_release_gate): hold (default),
   release_authorized. Only a separate, explicitly authenticated owner action
   may write release_authorized.

A video is eligible for public release only when the **latest** review state
is approved and the **latest** release decision is release_authorized.
A later hold immediately revokes eligibility. This is a policy check, **not**
a YouTube publishing implementation.

Safety rules:
- Private YouTube upload must remain private until owner explicitly authorizes release.
- No agent, QA check, script or video-review form may automatically authorize public release.
- The release gate does not perform network requests or change YouTube visibility.
- Production publishing must re-check both decisions immediately before each
  visibility change and audit its outcome. Do not treat this preliminary gate
  as a complete publication workflow.
- The current owner review HTTP server is loopback-only. Phone access and
  production authentication remain unimplemented.
