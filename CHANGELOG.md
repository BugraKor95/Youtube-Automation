# Changelog

Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). Roadmap: `ROADMAP.md`.

## [Unreleased]

### Status (2026-11-19)
- The last scheduled `Publish YouTube Short` run was on 2026-09-26. GitHub disables scheduled workflows after 60 days without repository activity (the last commit was 2026-07-28), so **nothing has been published since then**. To resume, re-enable the workflow under Actions → Publish YouTube Short → Enable.
- Tests: 9/9 passing (`python -m unittest discover -s tests`).

### Added
- `CHANGELOG.md`, `PATCH-NOTES.md`.

## [0.9.0] - 2026-07-28
- Analytics learning improvements, OAuth security hardening (#22).
- Scheduled publishing is resilient to dropped or delayed cron events (#21).

## [0.8.0] - 2026-07-14
- Niche lock and idea farming anchored to the best-performing video; channel metadata reset script (#20).
- Edge TTS: retries and a fallback voice after repeated failures (#18, #19).
- Swipe-away feedback loop, hook prompt hardening, faster hook-scene zoom (#17).
- Falls back to gemini-2.5-flash-lite when the daily free quota runs out (#16).

## [0.7.0] - 2026-07-09
- Analytics-lag-aware learning, NaN/None validation, retention feedback injected into prompts (#15).
- Retention gate tightened to 80% (#14).
- SEO metadata, long-tail keywords, monetization-weighted topic selection (#13).
- YouTube Analytics API (OAuth2) for the self-learning optimizer (#12).

## [0.6.0] - 2026-07-06
- Self-optimizing viral psychology content system: topic scoring, 5 competing hooks, retention prediction (#11).
- Strategy learnings from analyzed videos (#10).

## [0.5.0] - 2026-07-02
- Idea farming: 4 new categories, 8 new formats, 30+ new subjects.
- Competitor learnings: tighter pacing, stronger hooks, bilingual reach.

## [0.4.0] - 2026-06-30
- Algorithm optimization for retention, engagement and reach.
- Single GitHub Actions workflow with full configuration.

## [0.3.0] - 2026-06-28
- Pexels stock video, voice rotation, 30 topic areas; one consistent voice per video.

## [0.2.0] - 2026-06-27
- Gemini Imagen 4 support and an improved Pollinations pipeline.
- Instant audio, loop structure, vibrant captions; Shorts-tuned content engine.
- Local preview (`generate --preview`).

## [0.1.0] - 2026-06-25
- AI Shorts Factory: generation, rendering, upload and scheduling pipeline.
- Word-by-word animated captions, cinematic color grade, transient-error retries.
