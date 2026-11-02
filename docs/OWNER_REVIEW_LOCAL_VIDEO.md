# Owner review with local video

The review server is **loopback-only** and intended for testing on the Mac or Pi
itself. It is not a phone-accessible production service.

Create a private directory containing a rendered video and a registry JSON.
The registry format is shown in `examples/owner_review_media.json`.
Relative video paths must remain under the media root.

```bash
python -m kidsstudio.owner_review_web \
  --db ~/kidsstudio-data/reviews.sqlite \
  --episode red-ar \
  --media-root ~/kidsstudio-data/private-videos \
  --media-registry ~/kidsstudio-data/private-media.json
```

Open `http://127.0.0.1:8768/` on the same computer. A native HTML5 player
appears when a video is registered for that episode. The review decision and
notes are stored separately in SQLite. No video is uploaded or published.

Security and production limitations:
- Do **not** port-forward or bind this test server to a public interface.
- No phone login, authentication, TLS or multi-user permissions exist yet.
- Video response currently streams entire files without HTTP byte ranges;
  seeking in large videos may be limited.
- The page does not import YouTube private videos; it plays local media only.
- Real Mac-to-Pi delivery and owner approval still need integration testing.
