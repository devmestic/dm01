# Rhodes Reader KR

한국어 명일방주 스토리를 Android에서 완전히 오프라인으로 읽기 위한 네이티브 리더다.

## v3.0.0 · Full Local Media

v3는 WebView나 네트워크 런타임에 의존하지 않는다. 빌드할 때 최신 한국어 스토리 JSON을 가져오고, 각 스토리에서 실제 참조하는 미디어 키를 분석해 필요한 로컬 자산만 APK assets에 패키징한다.

- 전체 `ko_KR` 스토리 JSON
- 이벤트 배너
- 스토리 배경
- 스토리 CG / 이미지 / 아이템 컷
- Character 명령이 참조하는 캐릭터·NPC 컷
- PlayMusic BGM
- PlaySound 효과음
- 네이티브 이벤트/스토리 탐색 및 검색
- 북마크
- 마지막 읽던 스토리 및 스크롤 위치 복원
- 글자 크기
- 화면 계속 켜기
- 로컬 BGM/SFX 자동 재생 토글
- APK 미디어 팩 커버리지 표시

앱 매니페스트에는 `INTERNET` 권한이 없고 WebView도 사용하지 않는다.

## 빌드 데이터 흐름

1. `050644zf/ArknightsStoryJson`의 `ko_KR/gamedata/story`와 이벤트 배너를 읽는다.
2. `scripts/prepare_full_assets.py`가 1차로 모든 스토리 JSON을 APK assets용으로 정리한다.
3. 스토리 명령에서 Background/Image/Character/PlayMusic/PlaySound 참조를 수집한다.
4. 이미지 후보는 `fexli/ArknightsResource`의 `avgs`에서, 음원 후보는 `PseudoMon/arknights-audio`의 `music`, `avg`, `player`에서 찾아 참조된 파일만 패키징한다.
5. `media_index.json`에 요청 수, 매칭 수, 누락 키, 용량 통계를 기록한다.
6. GitHub Actions에서 APK를 빌드하고 story/media index와 실제 media assets가 포함됐는지 검사한다.

## 공개 배포 정책

앱 코드는 공개 저장소에서 관리한다. 다만 게임 원본 미디어는 별도의 권리 대상이고 일부 커뮤니티 저장소 역시 명시적인 재배포 라이선스를 제공하지 않으므로, **미디어 포함 APK는 자동으로 공개 GitHub Release에 발행하지 않는다.** 개인용 빌드 산출물은 GitHub Actions artifact로 생성한다.

## 출처 / 권리

- Reader inspiration / story processing: `050644zf/ArknightsStoryTextReader` (MIT for project code)
- Story data: `050644zf/ArknightsStoryJson`
- Image indexing source: `fexli/ArknightsResource`
- Audio indexing source: `PseudoMon/arknights-audio`
- Arknights game content © Hypergryph / Studio Montagne / Yostar and respective rights holders.

저장소의 Android 코드와 빌드 스크립트 라이선스가 게임 원본 콘텐츠의 권리를 변경하지 않는다.
