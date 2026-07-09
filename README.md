# Odds AI Pro V18 Custom Leagues

## 이번 수정
우리가 대화했던 리그만 반영했습니다.

### 야구
- MLB
- KBO
- NPB

### 축구
- K리그1
- K리그2
- J1
- J2
- EPL
- 라리가
- 세리에A
- 분데스리가
- 리그1
- UEFA 챔피언스리그 / 유로파리그 / 컨퍼런스리그
- MLS

### 농구
- NBA
- WNBA
- KBL

### 배구
- V리그
- 일본 V리그
- FIVB 국제경기

### 하키
- NHL

### 미식축구
- NFL

## 추가된 표시
- 🟢 강력추천
- 🟡 관찰
- 🔴 배팅금지
- 🔥 Away Sharp Pick / Home Sharp Pick

## 핵심 필터
- 야구 탭에서 1X2 / X / Draw 마켓 자동 제외
- 허용 리그 외 경기 자동 제외
- 정상 경기와 제외 경기 화면 분리
- KST 경기 시간 / 시작까지 남은 시간 / 종목 / 국가 / 리그 / 마켓 표시

## 실행
```bash
pip install -r requirements.txt
python app.py
```

브라우저:
```text
http://127.0.0.1:5000
```

## 실시간 API
```bash
ODDS_API_KEY=본인키
MIN_START_MINUTES=10
MAX_START_MINUTES=720
```

주의: 사용 중인 Odds API 상품에서 일부 리그 키가 지원되지 않으면 해당 리그는 자동으로 스킵됩니다.


## Render 배포 설정

Build Command:

```bash
pip install -r requirements.txt
```

Start Command:

```bash
gunicorn app:app
```

이번 버전은 `gunicorn: command not found` 오류가 나지 않도록 `requirements.txt`에 `gunicorn`을 포함했습니다.
