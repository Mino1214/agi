Crypto Regime Map Plan

0. 목표

2020년부터 현재까지 가상화폐 시장을 봉별로 분석해서
시장 상태를 시각적으로 구분하는 레짐 맵을 만든다.

최종 목표는 자동매매가 아니라, 먼저 시장을 다음 상태로 분류하고 차트에 색으로 표시하는 것이다.

* 상승장
* 하락장
* BTC 중심장
* 알트장
* 위험장
* 횡보장

⸻

1. 전체 구조

데이터 수집
↓
데이터 정리
↓
지표 계산
↓
레짐 판별
↓
차트 시각화
↓
사람이 검토
↓
규칙 수정
↓
백테스트 연결

⸻

2. 우선 사용할 봉

1순위: 일봉

레짐 전체 지도를 만들기 위한 기준 봉.

2020 ~ 현재 시장의 큰 흐름 확인용

2순위: 4시간봉

레짐 전환을 조금 더 빠르게 감지하기 위한 보조 봉.

일봉 레짐이 너무 늦게 반응하는지 확인용

3순위: 1시간봉

실제 진입 타이밍을 잡을 때 사용.

레짐 판별용이 아니라 진입 보조용

⸻

3. 데이터 수집

필수 데이터

BTC/USDT OHLCV
ETH/USDT OHLCV
상위 알트코인 OHLCV
거래량

가능하면 추가할 데이터

BTC.D
TOTAL
TOTAL2
TOTAL3
Funding Rate
Open Interest

초기 버전에서는 TOTAL, BTC.D가 없어도 진행한다.

⸻

4. 초기 코인 후보

BTC
ETH
SOL
BNB
XRP
DOGE
LINK
AVAX
ADA
TON

상위 코인 위주로 시작한다.

⸻

5. 계산할 지표

BTC 기준

EMA50
EMA200
ATR
거래량 평균
일간 수익률

ETH/BTC 기준

ETH/BTC 추세
ETH/BTC EMA50
ETH/BTC EMA200

알트 기준

상위 알트 상승 비율
상위 알트 EMA200 위 비율
상위 알트 거래량 증가 비율

⸻

6. 레짐 정의 초안

상승장

BTC > EMA200
EMA50 > EMA200
ATR 안정

하락장

BTC < EMA200
EMA50 < EMA200

BTC 중심장

BTC 상승
ETH/BTC 하락
알트 상승 비율 낮음

알트장

BTC 상승 또는 횡보
ETH/BTC 상승
알트 상승 비율 60% 이상

위험장

BTC 급락
ATR 급증
거래량 폭증

횡보장

BTC가 EMA50 주변
변동성 낮음
방향성 약함

⸻

7. 시각화 방식

BTC 차트 위에 배경색으로 레짐을 표시한다.

초록색 = 상승장
빨간색 = 하락장
파란색 = BTC 중심장
보라색 = 알트장
주황색 = 위험장
회색 = 횡보장

추가로 차트 하단에 레짐 타임라인을 표시한다.

⸻

8. 파일 구조

crypto_regime_map/
│
├─ data/
│  ├─ raw/
│  └─ processed/
│
├─ src/
│  ├─ collector.py
│  ├─ indicators.py
│  ├─ regime.py
│  ├─ visualizer.py
│  └─ main.py
│
├─ config.yaml
├─ requirements.txt
└─ plan.md

⸻

9. 개발 순서

Step 1

BTC 일봉 데이터 수집

Step 2

EMA50, EMA200, ATR 계산

Step 3

BTC 기준 상승장/하락장/횡보장만 먼저 분류

Step 4

BTC 차트에 배경색으로 레짐 표시

Step 5

ETH/BTC 추가

Step 6

알트 상승 비율 추가

Step 7

BTC 중심장/알트장 구분

Step 8

Funding, OI 추가

Step 9

레짐별 전략 백테스트 연결

⸻

10. 초기 목표

처음부터 완성형 봇을 만들지 않는다.

초기 목표는 다음 하나다.

2020년부터 현재까지 BTC 차트에 시장 레짐을 색으로 표시한다.

이후 사람이 직접 보고 다음을 검토한다.

레짐 전환이 너무 늦는가?
레짐이 너무 자주 바뀌는가?
실제 시장 흐름과 맞는가?
하락장을 제대로 피하는가?
알트장을 구분할 수 있는가?

⸻

11. 최종 확장 목표

레짐 시각화
↓
레짐별 전략 성과 분석
↓
레짐별 매매 전략 선택
↓
페이퍼트레이딩
↓
소액 실거래
↓
자동 리스크 관리
