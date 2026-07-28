# AI Shorts Factory

AI Shorts Factory is a fully automated YouTube Shorts content generation pipeline designed for faceless educational and viral content channels.

Content and prompts are tuned for the YouTube Shorts algorithm: an instant scroll-stopping hook (the moment that decides "viewed vs swiped"), escalating retention, and a loop-back ending that drives replays. Topics auto-rotate across proven curiosity formats and subjects while staying inside one cohesive channel identity.

The system automatically generates:

* Viral video ideas
* High-retention YouTube Shorts scripts
* Image generation prompts
* AI voiceovers
* Video assets
* Metadata (titles, descriptions, hashtags)

## Features

* Automated curiosity-driven video generation (what-if, terrifying facts, unsolved mysteries, future predictions, discoveries, cosmic-scale comparisons)
* Science, space, deep-ocean, nature, human-body, disaster and future-focused content
* Topics rotate across formats + subjects so the feed stays varied but on-brand
* AI-generated scripts engineered for the Shorts algorithm (1-second hook, re-hook, escalation, loop-back ending)
* AI-generated image prompts
* AI voiceover integration
* Automatic video assembly
* YouTube Shorts ready output (9:16 format)
* Batch content generation

## Workflow

Topic Generation
→ Script Generation
→ Image Prompt Generation
→ AI Image Creation
→ AI Voice Generation
→ Video Rendering
→ YouTube Shorts Export

## Example Video Topics

* What If The Sun Disappeared For 24 Hours?
* The Signal From Space No One Can Explain
* What If You Fell Into A Black Hole?
* Why Your Brain Deletes Most Of Reality
* What Lives At The Bottom Of The Ocean?

## Tech Stack

* Python
* Windsurf
* Gemini API
* ElevenLabs API
* FFmpeg
* YouTube Data API

## Goal

To reduce the time required to create a YouTube Shorts video from hours to minutes through end-to-end automation.

This project is intended for educational purposes, AI experimentation, and content creation workflow optimization.

## Analytics optimizer

The optimizer compares every upload on the same 24-hour, 72-hour and 7-day
calendar windows. Strategy changes use the 7-day median only after at least
five videos have reached 100 engaged views, preventing old uploads and single
outliers from dominating future topics.

Run the one-time OAuth flow whenever analytics scopes change:

```bash
python -m ai_shorts_factory auth
```

Credentials are saved locally to the ignored `token.json` file. Store its
`refresh_token` securely as `YOUTUBE_REFRESH_TOKEN` without printing or
committing it, then inspect measurement coverage and recommendations with:

```bash
python -m ai_shorts_factory optimize
```

Run the local test suite with:

```bash
python -m unittest discover -s tests -v
```
