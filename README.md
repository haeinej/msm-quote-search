# MSM 협가표 단가 조회 시스템

한국밸브 CAST CARBON STEEL VALVE [SCPH2/WCB] 협가표 기반 단가 자동 조회 시스템.

## 기능

- 제품명, 압력 등급, 사이즈, 할인율으로 협가표 단가 자동 조회
- 한국어/영어 자연어 입력 지원 (`게이트밸브 80A 할인 40` / `GATE 10K 80A -40%`)
- 원본 협가표 테이블 검증 (매칭된 셀 하이라이트)
- 재질 불일치 경고 (SCPH2/WCB 외 재질 입력 시)

## 설치 및 실행

```bash
pip install -r requirements.txt
python seed_data.py     # DB 생성 (최초 1회)
streamlit run app.py    # 앱 실행 → http://localhost:8501
```

## 할인율 범위

0% (정가), -40%, -42%, -45%, -47%

## 구조

| 파일 | 역할 |
|---|---|
| `seed_data.py` | PDF 가격 데이터 → SQLite DB |
| `parser.py` | 자연어 검색어 → 구조화 조건 |
| `lookup.py` | DB 조회 엔진 |
| `app.py` | Streamlit UI |
