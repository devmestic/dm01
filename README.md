# Rhodes Reader KR

명일방주 한국어 스토리를 **인터넷 없이** 읽는 Android 네이티브 리더다.

## v2.0.0 구조

`Android native UI → APK assets/story_index.json + assets/story/**.json`

WebView를 사용하지 않고, 앱에는 `INTERNET` 권한도 없다. GitHub Actions 빌드 시 `050644zf/ArknightsStoryJson`의 최신 `ko_KR/gamedata/story` 전체를 가져와 APK 내부 assets로 패키징한다. 설치 뒤에는 네트워크 연결이 없어도 목록 탐색과 본문 열람이 가능하다.

## 기능

- 한국어 스토리 전체 오프라인 패키징
- 이벤트별 탐색
- 스토리/이벤트/작전명/소개 검색
- 대사, 내레이션/자막, 선택지, 분기 표시
- 읽던 위치 저장/복원
- 북마크
- 글자 크기 85 / 100 / 115 / 130%
- 읽는 동안 화면 계속 켜기
- 마지막 읽던 스토리 복귀

## 빌드

GitHub Actions가 아래 순서로 자동 빌드한다.

1. 앱 저장소 checkout
2. `ArknightsStoryJson`을 sparse checkout하여 `ko_KR/gamedata/story`만 가져오기
3. `scripts/prepare_story_assets.py`로 전체 JSON을 `app/src/main/assets/story`에 복사하고 `story_index.json` 생성
4. Android APK 빌드
5. APK 내부에 오프라인 assets가 실제 포함됐는지 검증
6. `v2.0.0` GitHub Release 발행

필요 환경은 JDK 17, Android SDK 36, Build Tools 36.0.0, Gradle 9.6.0이다.

## Upstream

- Story reader: https://github.com/050644zf/ArknightsStoryTextReader
- Story JSON: https://github.com/050644zf/ArknightsStoryJson

## 범위

v2.0.0은 **스토리 텍스트 데이터 전체 오프라인**을 목표로 한다. 배경/캐릭터 일러스트, BGM, 효과음 등의 게임 미디어 리소스는 APK 용량과 권리 문제 때문에 포함하지 않는다.
