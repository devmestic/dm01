# Rhodes Reader KR · Project Status

## Current

- Target: v3.0.0 Full Local Media
- Architecture: Android native UI → bundled story JSON + bundled story-referenced media → local rendering/playback
- WebView: none
- INTERNET permission: none
- Public media release: disabled

## v3 scope

- [x] Full Korean story JSON bundling
- [x] Media reference collector for background/image/character/music/SFX commands
- [x] Event banner pack
- [x] Local image renderer
- [x] Local character/NPC cut renderer
- [x] Local BGM loop playback
- [x] Local SFX playback
- [x] Media coverage statistics in `media_index.json`
- [x] Native reader/search/bookmarks/reading-position persistence
- [ ] CI coverage verification against current upstream snapshot
- [ ] Installable v3 artifact verification

The two unchecked items are completed only after the GitHub Actions full-media build succeeds.
