import streamlit as st
import FinanceDataReader as fdr
import mplfinance as mpf
import matplotlib.pyplot as plt
from datetime import datetime, timedelta
import json
from streamlit_lottie import st_lottie
import pandas as pd

st.set_page_config(page_title="🔍 주식 정보 시각화")

# 시장 데이터를 읽어오는 함수 (미국 주식 호환)
@st.cache_data(ttl=3600)
def getData(code, datestart, dateend):
    try:
        df = fdr.DataReader(code, datestart, dateend)
        if 'Change' in df.columns:
            df = df.drop(columns='Change')
        return df
    except Exception as e:
        st.error(f"데이터를 가져올 수 없습니다: {code} ({e})")
        return None

@st.cache_data
def get_symbols(market='KOSPI', sort='Marcap'):
    try:
        df = fdr.StockListing(market)
        
        # 컬럼명 통일 (미국 시장 호환)
        rename_rules = {
            'MarketCap': 'Marcap', 
            'Price': 'Close', 
            'Symbol': 'Code'
        }
        df = df.rename(columns=rename_rules)
        
        # 숫자 컬럼을 안전하게 숫자로 변환
        for col in ['Close', 'Marcap']:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')
        
        # 정렬
        actual_sort = sort if sort in df.columns else 'Code'
        ascending = False if actual_sort == 'Marcap' else True
        df = df.sort_values(by=actual_sort, ascending=ascending)
        
        return df
    except Exception as e:
        st.error(f"주식 목록을 가져올 수 없습니다: {e}")
        return None

@st.cache_resource
def load_lottie_local(filepath):
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return None

def render_header():
    col1, col2, col3 = st.columns([1, 4, 1], vertical_alignment="center")
    with col1:
        lottie_path = "./resources/header_logo.json"
        lottie_json = load_lottie_local(lottie_path)
        if lottie_json: 
            st_lottie(lottie_json, speed=1, width=120, height=120, key="main_logo")
        else: 
            st.markdown("### 🔍")
    with col2:
        st.markdown("<h1 style='text-align: center;'>🔍 주식 정보 시각화</h1>", unsafe_allow_html=True)
    with col3:
        if st.button("🔄", use_container_width=True):
            # 모든 상태 초기화
            for key in list(st.session_state.keys()):
                del st.session_state[key]
            st.rerun()

def chart(chart_code, ndays, chart_style, volume, show_bb, show_rsi, show_macd):
    code = chart_code.strip().upper()
    date_end = datetime.today().date()
    date_start = (date_end - timedelta(days=ndays + 50))
    
    df = getData(code, date_start, date_end)
    if df is None or df.empty:
        st.error(f"📉 '{code}' 데이터 오류")
        return

    # --- [지표 계산] ---
    df['MA20'] = df['Close'].rolling(window=20).mean()
    df['std'] = df['Close'].rolling(window=20).std()
    df['BB_Upper'] = df['MA20'] + (df['std'] * 2)
    df['BB_Lower'] = df['MA20'] - (df['std'] * 2)

    delta = df['Close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    df['RSI'] = 100 - (100 / (1 + (gain / loss)))

    exp1 = df['Close'].ewm(span=12, adjust=False).mean()
    exp2 = df['Close'].ewm(span=26, adjust=False).mean()
    df['MACD'] = exp1 - exp2
    df['Signal'] = df['MACD'].ewm(span=9, adjust=False).mean()
    df['Hist'] = df['MACD'] - df['Signal']
    
    df = df.iloc[-ndays:]

    # --- [동적 패널 구성] ---
    apds = []
    # 패널 번호 관리 (0: 메인, 1: 거래량(고정))
    current_panel = 2 if volume else 1 
    ratios = [6] # 메인 차트 비율
    if volume: ratios.append(2) # 거래량 패널 비율

    # 볼린저 밴드 (메인 패널 0에 추가)
    if show_bb:
        apds.append(mpf.make_addplot(df['BB_Upper'], color='silver', width=0.7, alpha=0.5))
        apds.append(mpf.make_addplot(df['BB_Lower'], color='silver', width=0.7, alpha=0.5))

    # RSI (동적 패널 할당)
    if show_rsi:
        apds.append(mpf.make_addplot(df['RSI'], panel=current_panel, color='orange', ylabel='RSI'))
        ratios.append(2)
        current_panel += 1

    # MACD (동적 패널 할당)
    if show_macd:
        apds.append(mpf.make_addplot(df['MACD'], panel=current_panel, color='fuchsia', ylabel='MACD'))
        apds.append(mpf.make_addplot(df['Signal'], panel=current_panel, color='blue'))
        apds.append(mpf.make_addplot(df['Hist'], panel=current_panel, type='bar', color='gray', alpha=0.3))
        ratios.append(2)

    marketcolors = mpf.make_marketcolors(up='red', down='blue', edge='black', wick={'up':'red', 'down':'blue'}, volume='inherit')
    mpf_style = mpf.make_mpf_style(base_mpf_style=chart_style, marketcolors=marketcolors)

    # 차트 그리기
    fig, axlist = mpf.plot(
        df, type='candle', volume=volume, addplot=apds,
        style=mpf_style, figsize=(14, 8 + (len(ratios)*2)), # 패널 개수에 따라 높이 자동 조절
        panel_ratios=tuple(ratios), # 계산된 비율 적용
        mav=(5, 10, 30), mavcolors=('red', 'green', 'blue'),
        returnfig=True
    )
    
    st.session_state.plt_fig = fig

# 🔥 클릭 가능한 주식 목록
def create_clickable_dataframe(df):
    """클릭 시 목록 숨기고 그래프 fullscreen"""
    if df is None or df.empty:
        return
    
    st.markdown("**📈 종목 클릭**")
    
    df_display = df.head(100).reset_index(drop=True)
    
    # 고정된 높이(예: 400px)의 스크롤 컨테이너 생성
    with st.container(height=400):
        for idx, row in df_display.iterrows():
            col1, col2, col3, col4, col5 = st.columns([1.5, 1.5, 2.5, 2, 1])
            
            with col1:
                if st.button(f"📈 {row['Code']}", key=f"btn_code_{idx}", use_container_width=True):
                    st.session_state.code_index = str(row['Code'])
                    st.session_state.auto_chart_trigger = True
                    st.session_state.plt_fig = None 
                    st.session_state.df_title = ""
                    st.session_state.df_date = ""
                    st.rerun()
            
            with col2:
                st.markdown(f"**{row.get('Name', 'N/A')}**")
            
            with col3:
                close_price = row.get('Close')
                if pd.notna(close_price):
                    st.write(f"현재가: {close_price:,.0f}") # metric 대신 가벼운 텍스트 권장
                
            with col4:
                marcap = row.get('Marcap')
                if pd.notna(marcap):
                    st.caption(f"시총: {marcap:,.0f}")
            
            with col5:
                st.caption(row.get('Market', 'N/A'))
        

# 초기화
render_header()

# 📍 상태 초기화
if 'show_list' not in st.session_state:
    st.session_state.show_list = True  # 기본값: 목록 표시
if 'ascending' not in st.session_state:
    st.session_state.ascending = False
if 'df_result' not in st.session_state:
    st.session_state.df_result = None
if 'ndays' not in st.session_state:
    st.session_state.ndays = 30
if 'code_index' not in st.session_state:
    st.session_state.code_index = ""
if 'chart_style' not in st.session_state:
    st.session_state.chart_style = 'default'
if 'volume' not in st.session_state:
    st.session_state.volume = True
if 'plt_fig' not in st.session_state:
    st.session_state.plt_fig = None
if 'auto_chart_trigger' not in st.session_state:
    st.session_state.auto_chart_trigger = False

# 🚀 1단계: 주식 목록 (show_list=True일 때만)

st.markdown("---")
st.header("주식 목록 가져오기")

with st.form(key='get_list'):
    col1, col2, col3 = st.columns([1, 1, 1])
    
    with col1:
        market = st.selectbox('시장 선택', 
                            options=['KOSPI', 'KOSDAQ', 'NASDAQ', 'NYSE', 'S&P500', 'ALL'], 
                            index=0)
    with col2:
        sort = st.selectbox('정렬 기준', options=['Marcap', 'Name', 'Code'], index=0)
    with col3:
        order = st.radio('정렬 순서', options=['내림차순', '오름차순'], 
                        index=0, horizontal=True)
        st.session_state.ascending = (order == '오름차순')
    
    submit_button = st.form_submit_button(label='📊', use_container_width=True)

if submit_button:
    with st.spinner('주식 목록을 가져오는 중...'):
        df = get_symbols(market=market, sort=sort)
        if df is not None:
            st.session_state.show_list = True
            if sort in df.columns:
                df = df.sort_values(by=sort, ascending=st.session_state.ascending)
            st.session_state.df_result = df

# 🔥 클릭 가능한 목록 (목록 모드에서만)
if st.session_state.show_list and st.session_state.df_result is not None:
    create_clickable_dataframe(st.session_state.df_result)

# 2단계: 수동 입력 (항상 표시)
st.header("주식 차트 시각화")

with st.form(key='get_chart'):
    col1, col2, col3= st.columns([1, 2, 1])
    
    with col1:
        ndays = st.number_input('과거 N일', min_value=10, max_value=365, 
                              value=st.session_state.ndays, step=10)
    
    with col2:
        code_input = st.text_input(
            '직접 입력 (예: 005930, AAPL)', 
            value=st.session_state.code_index,
            placeholder="종목코드 입력"
        )
    
    with col3:
        chart_style = st.selectbox('차트 스타일', 
                                 options=['default', 'binance', 'classic', 'yahoo', 'charles'], 
                                 index=0)
    
    c1, c2, c3, c4 = st.columns(4)
    with c1: volume = st.checkbox('거래량', value=st.session_state.get('volume', True))
    with c2: show_bb = st.checkbox('볼린저 밴드', value=True)
    with c3: show_rsi = st.checkbox('RSI', value=True)
    with c4: show_macd = st.checkbox('MACD', value=True)
    
    chart_submit = st.form_submit_button(label='🎨', use_container_width=True)

if (chart_submit and code_input.strip()) or st.session_state.auto_chart_trigger:
    # 자동 트리거일 경우 입력값 교체
    current_code = st.session_state.code_index if st.session_state.auto_chart_trigger else code_input
    
    # 트리거 초기화 (무한 루프 방지)
    st.session_state.auto_chart_trigger = False
    
    # 1. 기존 차트 삭제 (새 종목을 위해)
    st.session_state.plt_fig = None
    
    # 2. 차트 새로 생성 (chart 함수 내부에서 plt_fig, df_title 등을 세션에 저장함)
    with st.spinner('차트 생성 중...'):
        chart(current_code, ndays, chart_style, volume, show_bb, show_rsi, show_macd)
    st.rerun()
    

# 🎯 최종 차트 출력 (세션에 그림이 있다면 어디서든 항상 표시)
if st.session_state.plt_fig is not None:
    st.markdown(st.session_state.df_title, unsafe_allow_html=True)
    st.markdown(st.session_state.df_date, unsafe_allow_html=True)
    st.pyplot(st.session_state.plt_fig)
    