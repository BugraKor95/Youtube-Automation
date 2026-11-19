# Patch notes

## Current status

- **Publishing is paused:** GitHub turned off the scheduled workflow because the repository saw no activity for 60 days. The last video went out on 26 September 2026.
- Before turning publishing back on, decide whether it's worth it; see "Assessment" below.

## July 2026

- The channel now stays in one niche and produces new ideas from its best-performing video.
- If voice generation fails, a backup voice is used, so videos are no longer skipped.
- If the daily free AI quota runs out, a lighter model takes over.
- The optimizer learns from views, retention and subscriber data.
- Scheduled publishing is resilient to delayed or dropped cron runs.

## June 2026

- First release: a fully automated Shorts pipeline from topic to script, visuals, voiceover, captions, render and upload, publishing twice a day.

## Assessment

- **Monetization thresholds:**
  - Today: 10 million Shorts views in 90 days, or 1,000 subscribers plus 4,000 watch hours.
  - New applicants from 1 February 2027: 20 million views or 8,000 hours.
- **Revenue:** Shorts pay roughly USD 0.01–0.07 per 1,000 views.
- **Policy risk:** YouTube's "inauthentic / mass-produced content" policy is the biggest threat to fully automated channels.
- **Recommendation:** Run the optimizer report (`python -m ai_shorts_factory optimize`) to review the channel's last 90 days. If the channel got fewer than 1 million views in that period, don't turn publishing back on; keep the project as a portfolio piece.
