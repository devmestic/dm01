# PROJECT STATUS

## Rhodes Reader KR v2.0.0

Status: release candidate

Architecture:
- Native Android Activity/UI
- No WebView
- No INTERNET permission
- All Korean story JSON files embedded into APK assets during CI build
- Build-time generated story index

Implemented:
- Event browser
- Full-text metadata search
- Native story renderer for dialogue/multiline/subtitle/sticker/decision/predicate/comment
- Fallback rendering for future text-bearing story commands
- Per-story reading position persistence
- Bookmarks
- Last-read story
- Text scaling
- Keep-screen-on preference
- GitHub Actions offline dataset packaging and APK verification

Data scope:
- Complete `ko_KR/gamedata/story/**/*.json` dataset from `050644zf/ArknightsStoryJson`
- Text/story commands only. Game images/audio are intentionally not bundled.
