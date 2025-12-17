import streamlit as st
import pandas as pd
import requests
import datetime
import re
import folium
from streamlit_folium import st_folium
from geopy.geocoders import Nominatim
import time
import json
import math
import os
import base64
from PIL import Image, ImageDraw, ImageFont
import io

# ==========================================
# 1. 페이지 설정
# ==========================================
st.set_page_config(
    page_title="통합 기상특보 상황실",
    layout="wide",
    initial_sidebar_state="collapsed"
)

st.markdown("""
    <style>
        /* 기본 여백 조정 */
        .block-container {
            padding-top: 1rem;
            padding-bottom: 2rem;
            padding-left: 1rem;
            padding-right: 1rem;
        }

        /* ==========================================
           [1] 타이틀 + 로고 박스 (중앙 정렬 유지)
        ========================================== */
        .custom-header-box {
            display: flex; 
            justify-content: center; /* 중앙 정렬 (수정 금지) */
            align-items: center;     
            gap: 20px;               
            
            background-color: #f8f9fa;
            border: 1px solid #e0e0e0;
            border-radius: 15px;
            padding: 20px;
            margin-bottom: 20px;
            box-shadow: 0 2px 5px rgba(0,0,0,0.05);
        }

        .header-title {
            font-size: 2.0rem; 
            font-weight: 800;
            color: #333;
            margin: 0;
            line-height: 1.2;
            text-align: center; 
        }
        
        .header-logo-img {
            width: 80px; 
            height: auto;
        }

        @media (prefers-color-scheme: dark) {
            .custom-header-box { background-color: #262730; border: 1px solid #464b5d; }
            .header-title { color: #ffffff; }
        }

        @media only screen and (max-width: 600px) {
            .custom-header-box {
                flex-direction: column; 
                gap: 10px;
                padding: 15px;
            }
            .header-title {
                font-size: 1.5rem; 
                word-break: keep-all; 
            }
            .header-logo-img {
                width: 60px; 
            }
        }

        /* ==========================================
           [기타 기존 스타일]
        ========================================== */
        .metric-card { background-color: #ffffff; border: 1px solid #e0e0e0; border-radius: 10px; padding: 15px; height: 100px; display: flex; flex-direction: column; justify-content: center; align-items: center; box-shadow: 0 2px 5px rgba(0,0,0,0.05); }
        @media (prefers-color-scheme: dark) { .metric-card { background-color: #262730; border: 1px solid #464b5d; } .metric-label { color: #fafafa !important; } .metric-value { color: #ffffff !important; } .scroll-box { background-color: #262730 !important; color: #fff !important; border: 1px solid #464b5d !important; } .site-title { color: #4da6ff !important; } .site-addr { color: #ccc !important; } }
        .metric-label { font-size: 0.9rem; color: #666; margin-bottom: 5px; font-weight: 600; }
        .metric-value { font-size: 2.0rem; font-weight: 800; color: #333; }
        .site-title { font-size: 1.4rem; font-weight: 800; color: #1f77b4; margin: 0; line-height: 1.3; word-break: keep-all; }
        .site-addr { font-size: 0.95rem; color: #555; margin-bottom: 10px; }
        .temp-badge { font-size: 1.1rem; font-weight: bold; color: #fff; background-color: #1f77b4; padding: 6px 12px; border-radius: 20px; display: inline-block; margin-bottom: 10px; }
        .site-header { display: flex; align-items: center; gap: 10px; margin-bottom: 5px; flex-wrap: wrap; }
        .status-badge { font-size: 0.9rem; font-weight: bold; padding: 4px 8px; border-radius: 6px; color: white; display: inline-block; white-space: nowrap; flex-shrink: 0; }
        .badge-normal { background-color: #28a745; }
        .badge-warning { background-color: #dc3545; }
        .scroll-box { height: 120px; overflow-y: auto; background-color: #f8f9fa; padding: 15px; border-radius: 8px; border: 1px solid #e0e0e0; font-size: 0.9rem; line-height: 1.6; color: #333; white-space: pre-wrap; }
        
        @media only screen and (max-width: 768px) {
            div[data-testid="column"] { width: 100% !important; flex: 1 1 auto !important; min-width: auto !important; }
            .metric-card { margin-bottom: 10px; }
            .site-header { flex-direction: column; align-items: flex-start; gap: 5px; }
            .metric-value { font-size: 1.8rem; }
            .temp-badge { font-size: 1.0rem; padding: 5px 10px; }
            .site-addr { font-size: 0.9rem; }
        }
    </style>
    """, unsafe_allow_html=True)

# ==========================================
# 2. 설정 & 초기화
# ==========================================
try:
    API_KEY_ENCODED = st.secrets["api_key"]
except FileNotFoundError:
    st.error("secrets.toml 파일이 없거나 api_key가 설정되지 않았습니다.")
    st.stop()
    
EXCEL_FILENAME = "site_list.xlsx"
CACHE_FILENAME = "site_list_cached.csv"
LOGO_FILENAME = "gslogo.png"

if 'weather_data' not in st.session_state:
    st.session_state.weather_data = None
if 'selected_site' not in st.session_state:
    st.session_state.selected_site = None

geolocator = Nominatim(user_agent="korea_weather_guard_final_flush_right", timeout=15)

# ==========================================
# 3. 함수 정의
# ==========================================

def get_file_path(filename):
    current_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(current_dir, filename)

def get_base64_of_bin_file(bin_file):
    with open(bin_file, 'rb') as f:
        data = f.read()
    return base64.b64encode(data).decode()

# [추가] 한글 폰트 자동 다운로드 및 로드 함수
@st.cache_resource
def load_korean_font(size=20):
    font_url = "https://github.com/google/fonts/raw/main/ofl/nanumgothic/NanumGothic-Bold.ttf"
    font_path = "NanumGothic-Bold.ttf"
    
    if not os.path.exists(font_path):
        try:
            r = requests.get(font_url)
            with open(font_path, "wb") as f:
                f.write(r.content)
        except:
            pass # 다운로드 실패 시 기본 폰트 사용

    try:
        return ImageFont.truetype(font_path, size)
    except:
        return ImageFont.load_default()

# [추가] 포스터 생성 함수
def create_warning_poster(warning_summary, total_sites, normal_sites_count):
    # 1. 캔버스 설정 (A4 비율 축소: 800 x 1131)
    W, H = 800, 1131
    img = Image.new('RGB', (W, H), color='white')
    draw = ImageDraw.Draw(img)
    
    # 2. 폰트 로드
    title_font = load_korean_font(50)
    subtitle_font = load_korean_font(30)
    content_title_font = load_korean_font(28)
    content_font = load_korean_font(22)
    footer_font = load_korean_font(20)

    # 3. 상단 헤더 그리기 (파란색 배경)
    header_height = 150
    draw.rectangle([(0, 0), (W, header_height)], fill="#005bac") # GS Blue 색상
    
    # 타이틀
    title_text = "GS건설 현장 기상특보 현황"
    # textbbox를 사용하여 텍스트 크기 계산
    bbox = draw.textbbox((0, 0), title_text, font=title_font)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]
    draw.text(((W - text_w) / 2, (header_height - text_h) / 2 - 10), title_text, font=title_font, fill="white")

    # 4. 날짜 및 개요
    current_time = datetime.datetime.now().strftime('%Y년 %m월 %d일 %H:%M 기준')
    summary_text = f"총 현장: {total_sites}  |  이상 없음: {normal_sites_count}  |  특보 발령: {total_sites - normal_sites_count}"
    
    draw.text((50, 180), current_time, font=subtitle_font, fill="#555555")
    draw.text((50, 230), summary_text, font=content_title_font, fill="#333333")
    
    draw.line([(50, 280), (W-50, 280)], fill="#dddddd", width=2)

    # 5. 특보 리스트 그리기
    y_position = 320
    
    if not warning_summary:
        # 특보가 없을 때 가운데에 메시지 표시
        msg = "현재 발령된 기상 특보가 없습니다."
        bbox = draw.textbbox((0, 0), msg, font=subtitle_font)
        msg_w = bbox[2] - bbox[0]
        draw.text(((W - msg_w) / 2, y_position + 100), msg, font=subtitle_font, fill="#28a745")
    else:
        for w_name, sites in warning_summary.items():
            # 특보 제목 (예: 한파주의보)
            color = "red" if "경보" in w_name else "#ff6600"
            draw.text((50, y_position), f"⚠️ {w_name} ({len(sites)}개소)", font=content_title_font, fill=color)
            y_position += 45
            
            # 현장 목록 (줄바꿈 처리)
            sites_str = ", ".join(sites)
            margin = 50
            max_width = W - (margin * 2)
            words = sites_str.split(' ')
            line = ""
            for word in words:
                test_line = line + word + " "
                bbox = draw.textbbox((0, 0), test_line, font=content_font)
                line_w = bbox[2] - bbox[0]
                
                if line_w > max_width:
                    draw.text((margin, y_position), line, font=content_font, fill="#333333")
                    line = word + " "
                    y_position += 35
                else:
                    line = test_line
            draw.text((margin, y_position), line, font=content_font, fill="#333333")
            y_position += 60 # 다음 특보 사이 간격

            if y_position > H - 100:
                draw.text((margin, y_position), "... (이하 생략)", font=content_font, fill="#999999")
                break

    # 6. 하단 푸터
    draw.line([(50, H-80), (W-50, H-80)], fill="#dddddd", width=2)
    footer_text = "GS E&C 안전보건팀"
    bbox = draw.textbbox((0, 0), footer_text, font=footer_font)
    f_w = bbox[2] - bbox[0]
    draw.text(((W - f_w) / 2, H - 50), footer_text, font=footer_font, fill="#999999")

    # 7. 이미지 바이트 변환
    img_byte_arr = io.BytesIO()
    img.save(img_byte_arr, format='JPEG', quality=95)
    img_byte_arr = img_byte_arr.getvalue()
    
    return img_byte_arr

def dfs_xy_conv(v1, v2):
    RE = 6371.00877
    GRID = 5.0
    SLAT1 = 30.0
    SLAT2 = 60.0
    OLON = 126.0
    OLAT = 38.0
    XO = 43
    YO = 136
    DEGRAD = math.pi / 180.0
    re = RE / GRID
    slat1 = SLAT1 * DEGRAD
    slat2 = SLAT2 * DEGRAD
    olon = OLON * DEGRAD
    olat = OLAT * DEGRAD
    sn = math.tan(math.pi * 0.25 + slat2 * 0.5) / math.tan(math.pi * 0.25 + slat1 * 0.5)
    sn = math.log(math.cos(slat1) / math.cos(slat2)) / math.log(sn)
    sf = math.tan(math.pi * 0.25 + slat1 * 0.5)
    sf = math.pow(sf, sn) * math.cos(slat1) / sn
    ro = math.tan(math.pi * 0.25 + olat * 0.5)
    ro = re * sf / math.pow(ro, sn)
    ra = math.tan(math.pi * 0.25 + (v1) * DEGRAD * 0.5)
    ra = re * sf / math.pow(ra, sn)
    theta = v2 * DEGRAD - olon
    if theta > math.pi: theta -= 2.0 * math.pi
    if theta < -math.pi: theta += 2.0 * math.pi
    theta *= sn
    x = math.floor(ra * math.sin(theta) + XO + 0.5)
    y = math.floor(ro - ra * math.cos(theta) + YO + 0.5)
    return int(x), int(y)

def get_current_temp(lat, lon):
    try:
        nx, ny = dfs_xy_conv(lat, lon)
        now = datetime.datetime.now()
        if now.minute <= 45: 
            now = now - datetime.timedelta(hours=1)
        base_date = now.strftime('%Y%m%d')
        base_time = now.strftime('%H00')
        base_url = "http://apis.data.go.kr/1360000/VilageFcstInfoService_2.0/getUltraSrtNcst"
        query_params = f"?serviceKey={API_KEY_ENCODED}&pageNo=1&numOfRows=10&dataType=JSON&base_date={base_date}&base_time={base_time}&nx={nx}&ny={ny}"
        full_url = base_url + query_params
        response = requests.get(full_url, timeout=5)
        try:
            data = response.json()
        except json.JSONDecodeError:
            return None
        if data['response']['header']['resultCode'] == '00':
            items = data['response']['body']['items']['item']
            for item in items:
                if item['category'] == 'T1H': 
                    return float(item['obsrValue'])
        return None
    except Exception:
        return None

def get_coordinates(address):
    if pd.isna(address) or str(address).strip() == "":
        return None, None
    try:
        clean_addr = re.sub(r'\([^)]*\)', '', str(address)).strip()
        candidates = [clean_addr]
        tokens = clean_addr.split()
        if len(tokens) > 3: candidates.append(" ".join(tokens[:3]))
        if len(tokens) >= 2: candidates.append(" ".join(tokens[:2]))
        for cand in candidates:
            try:
                location = geolocator.geocode(cand)
                if location: return location.latitude, location.longitude
                time.sleep(0.3)
            except Exception:
                time.sleep(0.5)
                continue
        return None, None
    except Exception:
        return None, None

def load_data_once():
    excel_path = get_file_path(EXCEL_FILENAME)
    cache_path = get_file_path(CACHE_FILENAME)

    if os.path.exists(cache_path):
        try:
            df = pd.read_csv(cache_path)
            return df
        except Exception:
            pass
    
    if not os.path.exists(excel_path):
        st.error(f"❌ 파일을 찾을 수 없습니다: {excel_path}")
        return pd.DataFrame()

    try:
        df = pd.read_excel(excel_path, engine='openpyxl')
        if '주소' in df.columns:
            df['주소'] = df['주소'].fillna('').astype(str)
            
            if 'lat' not in df.columns or df['lat'].isnull().all():
                with st.status("🚀 최초 1회 위치 분석 중... (다음부턴 바로 열립니다)", expanded=True) as status:
                    lats, lons = [], []
                    total = len(df)
                    for i, addr in enumerate(df['주소']):
                        percent = int((i + 1) / total * 100)
                        status.update(label=f"주소 변환 중... {percent}% ({i+1}/{total})")
                        lat, lon = get_coordinates(addr)
                        lats.append(lat)
                        lons.append(lon)
                    status.update(label="✅ 분석 완료! 데이터를 저장합니다.", state="complete", expanded=False)
                
                df['lat'] = lats
                df['lon'] = lons
                df.to_csv(cache_path, index=False, encoding='utf-8-sig')
        else:
            st.error("❌ '주소' 컬럼이 없습니다.")
            return pd.DataFrame()
        return df
    except PermissionError:
        st.error("🔒 엑셀 파일이 열려있습니다. 닫고 새로고침 해주세요.")
        return pd.DataFrame()
    except Exception as e:
        st.error(f"❌ 오류 발생: {e}")
        return pd.DataFrame()

def get_weather_status():
    base_url = "http://apis.data.go.kr/1360000/WthrWrnInfoService/getPwnStatus"
    url = f"{base_url}?serviceKey={API_KEY_ENCODED}&numOfRows=10&pageNo=1&dataType=JSON"
    try:
        response = requests.get(url, timeout=5)
        data = response.json()
        items = data['response']['body']['items']['item']
        if not items: return None
        return items[0].get('t6', '')
    except Exception:
        return None

def analyze_all_warnings(full_text, keywords):
    if not full_text: return []
    clean_text = full_text.replace('\r', ' ').replace('\n', ' ')
    detected_warnings = []
    matches = re.finditer(r"o\s*([^:]+)\s*:\s*(.*?)(?=o\s|$)", clean_text)
    for match in matches:
        warning_name = match.group(1).strip()
        content = match.group(2)
        for key in keywords:
            if key in content:
                detected_warnings.append(warning_name)
                break
    return list(set(detected_warnings))

def get_icon_and_color(warning_list):
    if not warning_list: return "blue", "info-sign"
    is_warning = any("경보" in w for w in warning_list)
    color = "red" if is_warning else "orange"
    main_w = warning_list[0]
    if "한파" in main_w: icon = "asterisk"
    elif "건조" in main_w: icon = "fire"
    elif "폭염" in main_w: icon = "sun"
    elif "호우" in main_w: icon = "tint"
    elif "대설" in main_w: icon = "snowflake-o"
    elif "태풍" in main_w: icon = "bullseye"
    elif "강풍" in main_w: icon = "flag"
    else: icon = "exclamation"
    return color, icon

def render_custom_metric(label, value, color="#333", icon=""):
    html = f"""
    <div class="metric-card" title="{label}">
        <div class="metric-label">{icon} {label}</div>
        <div class="metric-value" style="color: {color};">{value}</div>
    </div>
    """
    st.markdown(html, unsafe_allow_html=True)

# ==========================================
# [사이드바]
# ==========================================
with st.sidebar:
    st.header("⚙️ 설정")
    st.write("엑셀에 현장이 추가되었나요?")
    if st.button("🔄 데이터 새로고침 (재분석)", use_container_width=True):
        cache_path = get_file_path(CACHE_FILENAME)
        if os.path.exists(cache_path):
            os.remove(cache_path)
        st.session_state.weather_data = None
        st.rerun()

# ==========================================
# 4. 메인 화면 로직
# ==========================================

# [수정] 박스 형태로 타이틀과 로고를 중앙 정렬하여 그리기
logo_path = get_file_path(LOGO_FILENAME)
img_base64 = ""
if os.path.exists(logo_path):
    img_base64 = get_base64_of_bin_file(logo_path)

st.markdown(
    f"""
    <div class="custom-header-box">
        <div class="header-title">GS건설 현장 기상정보</div>
        <img src="data:image/png;base64,{img_base64}" class="header-logo-img">
    </div>
    """,
    unsafe_allow_html=True
)

if st.session_state.weather_data is None:
    st.session_state.weather_data = load_data_once()

df = st.session_state.weather_data

if not df.empty:
    full_text = get_weather_status()
    df['warnings'] = None
    
    warning_summary = {}
    warn_sites_list = []
    normal_sites_list = []
    
    if full_text:
        for i, row in df.iterrows():
            addr = str(row.get('주소', ''))
            keywords = []
            tokens = addr.replace(',', ' ').split()
            for token in tokens:
                if token.endswith("시") or token.endswith("군"):
                    core_name = token[:-1]
                    if len(core_name) >= 2: keywords.append(core_name)
            w_list = []
            if keywords:
                w_list = analyze_all_warnings(full_text, keywords)
                df.at[i, 'warnings'] = w_list
                if w_list:
                    warn_sites_list.append(f"{row['현장명']} ({', '.join(w_list)})")
                    for w in w_list:
                        if w not in warning_summary: warning_summary[w] = []
                        warning_summary[w].append(row['현장명'])
                else:
                    normal_sites_list.append(row['현장명'])
            else:
                normal_sites_list.append(row['현장명'])

    # [1] 상단 현황판 (3단 카드)
    m1, m2, m3 = st.columns(3)
    with m1: render_custom_metric("총 현장", f"{len(df)}", color="#333", icon="🏗️")
    with m2: render_custom_metric("특보 발령", f"{len(warn_sites_list)}", color="#FF4B4B", icon="🚨")
    with m3: render_custom_metric("이상 없음", f"{len(normal_sites_list)}", color="#00CC96", icon="✅")
    
    now_str = datetime.datetime.now().strftime('%Y년 %m월 %d일 %H:%M')
    st.markdown(f"<div style='text-align: center; color: gray; font-size: 0.8rem; margin-top: 5px; margin-bottom: 20px;'>기준: {now_str}</div>", unsafe_allow_html=True)

    # [2] 기상청 특보 전문 (위치: 현황판 아래)
    st.markdown("##### 📢 기상청 특보 전문")
    if full_text:
        text = full_text.replace('\n', ' ').replace('\r', ' ').strip()
        formatted_text = text.replace("o ", "\n o ").strip()
        formatted_text = formatted_text.lstrip('\n ').strip()
        
        st.markdown(
            f"""
            <div class="scroll-box">
                {formatted_text.replace(chr(10), '<br>')}
            </div>
            """, 
            unsafe_allow_html=True
        )
    else:
        st.info("현재 수신된 특보 데이터가 없습니다.")

    st.divider()

    # =========================================================================
    # [메인 레이아웃] 좌측(검색패널) 3.5 vs 우측(지도) 6.5
    # =========================================================================
    col_left, col_right = st.columns([3.5, 6.5])

    # --------------------------
    # [좌측 패널]
    # --------------------------
    with col_left:
        # 1. 검색창
        st.markdown("##### 🔍 현장 검색")
        site_list = df['현장명'].tolist()
        current_index = site_list.index(st.session_state.selected_site) if st.session_state.selected_site in site_list else None
        
        selected_option = st.selectbox(
            "현장 선택", 
            site_list, 
            index=current_index,
            placeholder="현장명을 입력해주세요", 
            label_visibility="collapsed"
        )
        
        if selected_option != st.session_state.selected_site:
            st.session_state.selected_site = selected_option
            st.rerun()
            
        st.write("") # 간격

        # 2. 선택된 현장 상세 정보
        is_site_selected = st.session_state.selected_site is not None
        
        if is_site_selected:
            target_row = df[df['현장명'] == st.session_state.selected_site].iloc[0]
            ws = target_row['warnings'] if target_row['warnings'] else []
            
            current_temp = None
            if pd.notna(target_row['lat']) and pd.notna(target_row['lon']):
                current_temp = get_current_temp(target_row['lat'], target_row['lon'])
            
            with st.container(border=True):
                status_html = f'<span class="status-badge badge-warning">🚨 특보 발령</span>' if ws else f'<span class="status-badge badge-normal">✅ 이상 없음</span>'
                st.markdown(f"""
                    <div class="site-header">
                        <span class="site-title">📍 {target_row['현장명']}</span>
                        {status_html}
                    </div>
                """, unsafe_allow_html=True)
                
                st.markdown(f"<div class='site-addr'>{target_row['주소']}</div>", unsafe_allow_html=True)
                
                if current_temp is not None:
                    st.markdown(f"<span class='temp-badge'>🌡️ {current_temp}℃</span>", unsafe_allow_html=True)
                else:
                    st.caption("기온 로딩 중...")
                
                if ws:
                    st.markdown("---")
                    for w in ws:
                        if "경보" in w: st.markdown(f":red[**🔥 {w}**]")
                        else: st.markdown(f":orange[**⚠️ {w}**]")
        else:
            st.info("👆 위에서 현장을 검색하거나, 지도 마커를 클릭하세요.")

        st.write("") 
        
        # 3. 특보별 현장 리스트 및 다운로드
        st.markdown("##### 📋 특보 발령 현황")
        
        list_height_px = 280 if is_site_selected else 430
        
        with st.container(height=list_height_px, border=True):
            # [수정] 버튼을 if문 밖으로 꺼내서 항상 보이게 함
            poster_img_bytes = create_warning_poster(warning_summary, len(df), len(normal_sites_list))
            today_str = datetime.datetime.now().strftime("%Y%m%d")
            
            st.download_button(
                label="🖼️ 특보 현황 포스터 다운로드",
                data=poster_img_bytes,
                file_name=f"기상특보현황_{today_str}.jpg",
                mime="image/jpeg",
                use_container_width=True
            )
            
            st.divider() # 구분선

            if warning_summary:
                for w_name, sites in warning_summary.items():
                    with st.container(border=True):
                        if "경보" in w_name:
                            st.markdown(f":red[**🔥 {w_name} ({len(sites)})**]")
                        else:
                            st.markdown(f"**⚠️ {w_name} ({len(sites)})**")
                        
                        for s in sites:
                            st.caption(f"• {s}")
            else:
                st.info("현재 특보 발령 중인 현장이 없습니다.")

    # --------------------------
    # [우측 패널] - 지도
    # --------------------------
    with col_right:
        valid_coords = df.dropna(subset=['lat', 'lon'])
        if not valid_coords.empty:
            
            if st.session_state.selected_site:
                sel = df[df['현장명'] == st.session_state.selected_site]
                if not sel.empty:
                    c_lat, c_lon = sel.iloc[0]['lat'], sel.iloc[0]['lon']
                    z_start = 11
                else:
                    c_lat, c_lon = 36.5, 127.5
                    z_start = 7
            else:
                c_lat, c_lon = 36.5, 127.5
                z_start = 7
            
            m = folium.Map(location=[c_lat, c_lon], zoom_start=z_start)
            
            for i, row in valid_coords.iterrows():
                ws = row['warnings'] if row['warnings'] else []
                color, icon_name = get_icon_and_color(ws)
                warn_msg = ", ".join(ws) if ws else "이상 없음"
                
                tooltip_html = f"{row['현장명']}:{warn_msg}"
                
                folium.Marker(
                    [row['lat'], row['lon']],
                    tooltip=tooltip_html,
                    icon=folium.Icon(color=color, icon=icon_name, prefix='fa')
                ).add_to(m)
            
            map_data = st_folium(m, width=None, height=550) 
            
            if map_data and map_data.get("last_object_clicked_tooltip"):
                clicked_name = map_data["last_object_clicked_tooltip"].split(":")[0].strip()
                if clicked_name != st.session_state.selected_site:
                    st.session_state.selected_site = clicked_name
                    st.rerun()
        else:
            st.error("지도에 표시할 수 있는 현장이 없습니다.")

st.divider()


