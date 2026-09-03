# Rhodes Reader KR

한국 명일방주 스토리를 Android에서 읽기 편하게 만든 개인용 리더 앱이다.

앱은 `050644zf/ArknightsStoryTextReader`의 한국 서버 화면을 사용하고, 원본 리더가 사용하는 `050644zf/ArknightsStoryJson` 데이터 갱신을 그대로 따라간다.

## 1.0.0 기능

- 한국 서버 메뉴로 즉시 시작
- 마지막으로 보던 페이지 자동 복귀
- 페이지별 스크롤 위치 저장/복원
- 5초 간격 읽기 위치 자동 저장
- 북마크 추가/삭제/목록 및 현재 상태 표시
- 글자 크기 85 / 100 / 115 / 130%
- 읽는 동안 화면 계속 켜기
- 현재 페이지 공유
- 웹 캐시 초기화
- 외부 링크는 기본 브라우저로 분리
- Reader 내부 탐색은 HTTPS만 허용
- 파일/콘텐츠 URI 접근 차단

## 빌드

필요 환경:

- JDK 17
- Android Gradle Plugin 9.4.0
- Gradle 9.6.0
- Android SDK Platform 36
- Android Build Tools 36.0.0
- minSdk 26

GitHub Actions의 `Build Android APK` 워크플로가 main 브랜치 push 때 debug APK를 빌드하고, `v1.0.0` Release에 설치 가능한 APK를 첨부한다.

## Upstream

- Reader: https://github.com/050644zf/ArknightsStoryTextReader
- Story data: https://github.com/050644zf/ArknightsStoryJson

## 권리 고지

이 저장소의 Android 셸 코드는 별도 구현이다. 원본 리더의 라이선스와 명일방주 게임 콘텐츠 및 이미지 권리는 각각 원 권리자에게 있다. 공개 재배포나 상업적 이용 전에는 해당 권리 조건을 별도로 확인해야 한다.
