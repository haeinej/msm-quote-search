"""
MSM SOLUTION 협가표 단가 조회 시스템
Streamlit UI
"""
import streamlit as st
import pandas as pd
from parser import parse_query
from lookup import lookup, get_full_discount_table

st.set_page_config(page_title="MSM 협가표 조회", page_icon="🔍", layout="wide")

# --- Styles ---
st.markdown("""
<style>
    .big-price {
        font-size: 2.4rem;
        font-weight: 700;
        color: #1a73e8;
        margin: 0.2rem 0;
    }
    .source-info {
        font-size: 0.9rem;
        color: #666;
        margin-top: 0.3rem;
    }
    .tag {
        display: inline-block;
        background: #e8f0fe;
        color: #1a73e8;
        padding: 0.2rem 0.6rem;
        border-radius: 1rem;
        font-size: 0.85rem;
        margin-right: 0.4rem;
        margin-bottom: 0.3rem;
    }
    .tag-empty {
        background: #fce8e6;
        color: #d93025;
    }
    .match-exact { color: #1e8e3e; font-weight: 600; }
    .match-multiple { color: #e8710a; font-weight: 600; }
    .match-none { color: #d93025; font-weight: 600; }
</style>
""", unsafe_allow_html=True)


def render_validation_table(matched_row: dict):
    """Render the original price table with the matched cell highlighted."""
    discount_rate = matched_row["discount_rate"]
    rows = get_full_discount_table(discount_rate)
    if not rows:
        return

    st.markdown(f"**원본 표 검증:** {matched_row['source_table_title']}")

    records = []
    for r in rows:
        col_name = f"{r['product_type']} {r['pressure_class']}"
        records.append({
            "사이즈": f"{r['size_a']}({r['size_inch']})",
            "sort_key": int(r["size_a"].replace("A", "")),
            "col": col_name,
            "price": r["unit_price"],
        })

    df = pd.DataFrame(records)
    pivot = df.pivot_table(index=["sort_key", "사이즈"], columns="col", values="price", aggfunc="first")
    pivot = pivot.sort_index(level=0)
    pivot.index = pivot.index.droplevel(0)

    col_order = []
    for pt in ["GATE", "GLOBE", "SW-CHECK", "Y-STRAINER"]:
        for pc in ["10K", "20K"]:
            c = f"{pt} {pc}"
            if c in pivot.columns:
                col_order.append(c)
    pivot = pivot[[c for c in col_order if c in pivot.columns]]

    match_col = f"{matched_row['product_type']} {matched_row['pressure_class']}"
    match_size = f"{matched_row['size_a']}({matched_row['size_inch']})"

    def highlight(col):
        return [
            "background-color: #c6f6d5; font-weight: bold"
            if col.name == match_col and pivot.index[i] == match_size
            else ""
            for i, v in enumerate(col)
        ]

    styled = pivot.style.apply(highlight, axis=0).format(
        lambda x: f"{int(x):,}" if pd.notna(x) else "주문생산",
        na_rep="주문생산",
    )

    st.dataframe(styled, use_container_width=True, height=500)


# --- Main UI ---
st.title("MSM 협가표 단가 조회")
st.caption("한국밸브 CAST CARBON STEEL VALVE [SCPH2/WCB] — 2022.01.01")

query = st.text_input(
    "제품 검색",
    placeholder="예: SCPH2 GATE V/V 10K 80A -40%  /  게이트밸브 80A 할인 40",
    label_visibility="collapsed",
)

if not query:
    st.info("제품명, 압력 등급, 사이즈, 할인율을 입력하세요.")
    st.stop()

parsed = parse_query(query)

# --- Parsed Conditions ---
st.markdown("#### 검색 조건 해석")
labels = {
    "product_type": "제품군",
    "pressure_class": "압력 등급",
    "size_a": "사이즈",
    "discount_rate": "할인율",
}
tags_html = ""
missing = []
for key, label in labels.items():
    val = parsed.get(key)
    if val:
        tags_html += f'<span class="tag">{label}: {val}</span>'
    else:
        tags_html += f'<span class="tag tag-empty">{label}: 미입력</span>'
        missing.append(key)
if parsed.get("connection_type"):
    tags_html += f'<span class="tag">연결: {parsed["connection_type"]}</span>'
st.markdown(tags_html, unsafe_allow_html=True)

for warning in parsed.get("warnings", []):
    st.warning(warning)

# --- Manual Override for Missing Fields ---
if missing:
    cols = st.columns(len(missing))
    for i, key in enumerate(missing):
        with cols[i]:
            if key == "product_type":
                pt = st.selectbox("제품군 선택", ["", "GATE", "GLOBE", "SW-CHECK", "Y-STRAINER"])
                if pt:
                    parsed["product_type"] = pt
            elif key == "pressure_class":
                pc = st.selectbox("압력 등급 선택", ["", "10K", "20K"])
                if pc:
                    parsed["pressure_class"] = pc
            elif key == "size_a":
                sizes = ["", "50A", "65A", "80A", "100A", "125A", "150A", "200A", "250A", "300A", "350A", "400A", "450A", "500A"]
                sa = st.selectbox("사이즈 선택", sizes)
                if sa:
                    parsed["size_a"] = sa
            elif key == "discount_rate":
                dr = st.selectbox("할인율 선택", ["", "0% (정가)", "-40%", "-42%", "-45%", "-47%"])
                if dr:
                    parsed["discount_rate"] = dr.split(" ")[0]  # strip "(정가)"

# --- Lookup ---
result = lookup(parsed)
status = result["status"]

st.markdown("---")

if status == "exact":
    r = result["results"][0]
    st.markdown("#### 조회 결과")
    st.markdown('<span class="match-exact">정확 매칭 (1건)</span>', unsafe_allow_html=True)

    c1, c2 = st.columns([1, 2])
    with c1:
        st.markdown(f'<div class="big-price">{r["unit_price"]:,} KRW</div>', unsafe_allow_html=True)
        st.markdown(f"""
<div class="source-info">
<b>제품군:</b> {r['product_type']} ({r['construction_type']})<br>
<b>압력:</b> {r['pressure_class']}<br>
<b>사이즈:</b> {r['size_a']} ({r['size_inch']})<br>
<b>할인율:</b> {r['discount_rate']}<br>
<b>원본:</b> {r['source_file']} p.{r['source_page']}<br>
<b>표:</b> {r['source_table_title']}
</div>
""", unsafe_allow_html=True)

    with c2:
        render_validation_table(r)

elif status == "multiple":
    st.markdown("#### 조회 결과")
    st.markdown(
        f'<span class="match-multiple">복수 매칭 ({result["count"]}건) — 조건을 추가해 주세요</span>',
        unsafe_allow_html=True,
    )

    df = pd.DataFrame(result["results"])
    display_cols = ["product_type", "construction_type", "pressure_class", "size_a", "size_inch", "discount_rate", "unit_price", "source_table_title"]
    display_cols = [c for c in display_cols if c in df.columns]
    df_display = df[display_cols].copy()
    col_names = ["제품군", "구조", "압력", "사이즈", "인치", "할인율", "단가(KRW)", "원본 표"]
    df_display.columns = col_names[: len(display_cols)]
    if "단가(KRW)" in df_display.columns:
        df_display["단가(KRW)"] = df_display["단가(KRW)"].apply(lambda x: f"{x:,}")
    st.dataframe(df_display, use_container_width=True, hide_index=True)

else:
    st.markdown("#### 조회 결과")
    st.markdown('<span class="match-none">협가표 내 매칭 없음</span>', unsafe_allow_html=True)
    st.info("해당 조건에 맞는 협가표 데이터가 없습니다. 제조사 견적 문의가 필요할 수 있습니다.")
