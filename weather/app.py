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
    page_title="GS건설 현장 기상특보",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# CSS 스타일 최적화 (여백 축소 및 시인성 강화)
st.markdown("""
    <style>
        /* 상단 여백 최소화 */
        .block-container {
            padding-top: 1rem;
            padding-bottom: 1rem;
            padding-left: 1rem;
            padding-right: 1rem;
        }

        /* 헤더 박스 스타일 */
        .custom-header-box {
            display: flex; 
            justify-content: center; 
            align-items: center;     
            gap: 15px;               
            background-color: #f8f9fa;
            border: 1px solid #e0e0e0;
            border-radius: 12px;
            padding: 15px;
            margin-bottom: 10px;
            box-shadow: 0 1px 3px rgba(0,0,0,0.05);
            flex-wrap: wrap; /* 화면 작을 때 줄바꿈 허용 */
        }

        .header-title {
            font-size: 1.8rem; 
            font-weight: 800;
            color: #005bac; /* GS Blue */
            margin: 0;
            line-height: 1.2;
            text-align: center; 
            white-space: nowrap;
        }
        
        .header-logo-img {
            height: 50px; /* 로고 크기 최적화 */
            width: auto;
        }

        /* 다크모드 대응 */
        @media (prefers-color-scheme: dark) {
            .custom-header-box { background-color: #262730; border: 1px solid #464b5d; }
            .header-title { color: #ffffff; }
        }

        /* 모바일 대응 */
        @media only screen and (max-width: 600px) {
            .header-title { font-size: 1.4rem; white-space: normal; word-break: keep-all; }
        }

        /* 메트릭 카드 (높이 축소) */
        .metric-card { 
            background-color: #ffffff; 
            border: 1px solid #e0e0e0; 
            border-radius: 8px; 
            padding: 10px; 
            height: 80px; 
            display: flex; 
            flex-direction: column; 
            justify-content: center; 
            align-items: center; 
            box-shadow: 0 1px 3px rgba(0,0,0,0.05); 
        }
        .metric-label { font-size: 0.85rem; color: #666; font-weight: 600; margin-bottom: 2px; }
        .metric-value { font-size: 1.6rem; font-weight: 800; color: #333; }
        
        /* 다크모드 메트릭 */
        @media (prefers-color-scheme: dark) { 
            .metric-card { background-color: #262730; border: 1px solid #464b5d; } 
            .metric-label { color: #fafafa !important; } 
            .metric-value { color: #ffffff !important; }
        }

        /* 현장 상세 정보 스타일 */
        .site-title { font-size: 1.3rem; font-weight: 800; color: #1f77b4; margin: 0; line-height: 1.2; word-break: keep-all; }
        .site-addr { font-size: 0.9rem; color: #555; margin-bottom: 8px; }
        .temp-badge { font-size: 1.2rem; font-weight: bold; color: #fff; background-color: #1f77b4; padding: 5px 12px; border-radius: 15px; display: inline-block; margin-right: 5px; }
        .time-caption { font-size: 0.8rem; color: #888; margin-top: 5px; }
        .site-header { display: flex; align-items: center; gap: 8px; margin-bottom: 5px; flex-wrap: wrap; }
        
        .status-badge { font-size: 0.8rem; font-weight: bold; padding: 3px 8px; border-radius: 4px; color: white; display: inline-block; white-space: nowrap; }
        .badge-normal { background-color: #28a745; }
        .badge-warning { background-color: #dc3545; }
        
        /* 지도 면책 조항 */
        .map-disclaimer {
            font-size: 0.75rem;
            color: #666;
            background-color: rgba(255, 255, 255, 0.7);
            padding: 2px 5px;
            border-radius: 4px;
            margin-bottom: 2px;
            text-align: right;
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

geolocator = Nominatim(user_agent="korea_weather_guard_gs", timeout=15)

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

# 한글 폰트 로드
@st.cache_resource
def load_korean_font(size=20):
    font_url = "https://github.com/google/fonts/raw/main/ofl/nanumgothic/NanumGothic-Bold.ttf"
    font_path = "NanumGothic-Bold.ttf"
    if not os.path.exists(font_path):
        try:
            r = requests.get(font_url)
            with open(font_path, "wb") as f:
                f.write(r.content)
        except: pass
    try:
        return ImageFont.truetype(font_path, size)
    except:
        return ImageFont.load_default()

# 포스터 생성 (기존 유지)
def create_warning_poster(warning_summary, total_sites, normal_sites_count):
    W, H = 800, 1131
    img = Image.new('RGB', (W, H), color='white')
    draw = ImageDraw.Draw(img)
    title_font = load_korean_font(50)
    subtitle_font = load_korean_font(30)
    content_title_font = load_korean_font(28)
    content_font = load_korean_font(22)
    footer_font = load_korean_font(20)

    header_height = 150
    draw.rectangle([(0, 0), (W, header_height)], fill="#005bac")
    
    title_text = "GS건설 현장 기상특보 현황"
    bbox = draw.textbbox((0, 0), title_text, font=title_font)
    text_w, text_h = bbox[2] - bbox[0], bbox[3] - bbox[1]
    draw.text(((W - text_w) / 2, (header_height - text_h) / 2 - 10), title_text, font=title_font, fill="white")

    current_time = datetime.datetime.now().strftime('%Y년 %m월 %d일 %H:%M 기준')
    summary_text = f"총 현장: {total_sites}  |  이상 없음: {normal_sites_count}  |  특보 발령: {total_sites - normal_sites_count}"
    
    draw.text((50, 180), current_time, font=subtitle_font, fill="#555555")
    draw.text((50, 230), summary_text, font=content_title_font, fill="#333333")
    draw.line([(50, 280), (W-50, 280)], fill="#dddddd", width=2)

    y_position = 320
    if not warning_summary:
        msg = "현재 발령된 기상 특보가 없습니다."
        bbox = draw.textbbox((0, 0), msg, font=subtitle_font)
        msg_w = bbox[2] - bbox[0]
        draw.text(((W - msg_w) / 2, y_position + 100), msg, font=subtitle_font, fill="#28a745")
    else:
        for w_name, sites in warning_summary.items():
            color = "red" if "경보" in w_name else "#ff6600"
            draw.text((50, y_position), f"⚠️ {w_name} ({len(sites)}개소)", font=content_title_font, fill=color)
            y_position += 45
            sites_str = ", ".join(sites)
            margin, max_width = 50, W - 100
            words = sites_str.split(' ')
            line = ""
            for word in words:
                test_line = line + word + " "
                bbox = draw.textbbox((0, 0), test_line, font=content_font)
                if (bbox[2] - bbox[0]) > max_width:
                    draw.text((margin, y_position), line, font=content_font, fill="#333333")
                    line = word + " "
                    y_position += 35
                else:
                    line = test_line
            draw.text((margin, y_position), line, font=content_font, fill="#333333")
            y_position += 60
            if y_position > H - 100:
                draw.text((margin, y_position), "... (이하 생략)", font=content_font, fill="#999999")
                break

    draw.line([(50, H-80), (W-50, H-80)], fill="#dddddd", width=2)
    footer_text = "GS E&C 안전보건팀"
    bbox = draw.textbbox((0, 0), footer_text, font=footer_font)
    f_w = bbox[2] - bbox[0]
    draw.text(((W - f_w) / 2, H - 50), footer_text, font=footer_font, fill="#999999")

    img_byte_arr = io.BytesIO()
    img.save(img_byte_arr, format='JPEG', quality=95)
    return img_byte_arr.getvalue()

def dfs_xy_conv(v1, v2):
    RE, GRID = 6371.00877, 5.0
    SLAT1, SLAT2, OLON, OLAT = 30.0, 60.0, 126.0, 38.0
    XO, YO = 43, 136
    DEGRAD = math.pi / 180.0
    re = RE / GRID
    slat1, slat2 = SLAT1 * DEGRAD, SLAT2 * DEGRAD
    olon, olat = OLON * DEGRAD, OLAT * DEGRAD
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

# [최적화] 기온 데이터 캐싱 (TTL 10분) - API 호출 최소화
@st.cache_data(ttl=600)
# [수정] 캐시 데코레이터(@st.cache_data)를 제거하여 클릭 시 무조건 실시간 호출하도록 변경
def get_current_temp_optimized(lat, lon):
    try:
        nx, ny = dfs_xy_conv(lat, lon)
        
        # 현재 시간
        now = datetime.datetime.now()
        
        # 기상청 초단기실황(NCST) 생성 기준: 매시 40분
        # 예: 10시 39분 -> 9시 데이터 사용 / 10시 41분 -> 10시 데이터 사용
        if now.minute <= 40: 
            target_time = now - datetime.timedelta(hours=1)
        else:
            target_time = now
            
        base_date = target_time.strftime('%Y%m%d')
        base_time = target_time.strftime('%H00') # 정시 기준
        
        base_url = "http://apis.data.go.kr/1360000/VilageFcstInfoService_2.0/getUltraSrtNcst"
        query_params = f"?serviceKey={API_KEY_ENCODED}&pageNo=1&numOfRows=10&dataType=JSON&base_date={base_date}&base_time={base_time}&nx={nx}&ny={ny}"
        
        # 타임아웃을 3초로 설정하여 너무 오래 걸리면 패스
        response = requests.get(base_url + query_params, timeout=3)
        
        data = response.json()
        
        if data['response']['header']['resultCode'] == '00':
            items = data['response']['body']['items']['item']
            for item in items:
                if item['category'] == 'T1H': # 기온
                    # 날짜/시간 포맷팅 (예: 12월 19일 03:00)
                    formatted_time = f"{base_date[4:6]}월 {base_date[6:8]}일 {base_time[:2]}:00"
                    return float(item['obsrValue']), formatted_time
                    
        return None, None
    except Exception as e:
        # 에러 발생 시 로그 출력 (디버깅용) 혹은 None 반환
        return None, None

def get_coordinates(address):
    if pd.isna(address) or str(address).strip() == "": return None, None
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
            except:
                time.sleep(0.5)
                continue
        return None, None
    except: return None, None

def load_data_once():
    excel_path = get_file_path(EXCEL_FILENAME)
    cache_path = get_file_path(CACHE_FILENAME)
    
    # 캐시 파일 있으면 바로 로드
    if os.path.exists(cache_path):
        try: return pd.read_csv(cache_path)
        except: pass
    
    if not os.path.exists(excel_path):
        st.error(f"❌ 파일을 찾을 수 없습니다: {excel_path}")
        return pd.DataFrame()

    try:
        df = pd.read_excel(excel_path, engine='openpyxl')
        if '주소' in df.columns:
            df['주소'] = df['주소'].fillna('').astype(str)
            if 'lat' not in df.columns or df['lat'].isnull().all():
                with st.status("🚀 최초 1회 위치 분석 중...", expanded=True) as status:
                    lats, lons = [], []
                    total = len(df)
                    for i, addr in enumerate(df['주소']):
                        if i % 10 == 0: status.update(label=f"주소 변환 중... ({i}/{total})")
                        lat, lon = get_coordinates(addr)
                        lats.append(lat)
                        lons.append(lon)
                    status.update(label="✅ 분석 완료!", state="complete", expanded=False)
                df['lat'], df['lon'] = lats, lons
                df.to_csv(cache_path, index=False, encoding='utf-8-sig')
        return df
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
    except: return None

def analyze_all_warnings(full_text, keywords):
    if not full_text: return []
    clean_text = full_text.replace('\r', ' ').replace('\n', ' ')
    detected_warnings = []
    matches = re.finditer(r"o\s*([^:]+)\s*:\s*(.*?)(?=o\s|$)", clean_text)
    for match in matches:
        w_name = match.group(1).strip()
        content = match.group(2)
        for key in keywords:
            if key in content:
                detected_warnings.append(w_name)
                break
    return list(set(detected_warnings))

def get_icon_and_color(warning_list):
    if not warning_list: return "blue", "info-sign"
    is_warning = any("경보" in w for w in warning_list)
    color = "red" if is_warning else "orange"
    main_w = warning_list[0]
    icon_map = {"한파": "asterisk", "건조": "fire", "폭염": "sun", "호우": "tint", "대설": "snowflake-o", "태풍": "bullseye", "강풍": "flag"}
    icon = "exclamation"
    for k, v in icon_map.items():
        if k in main_w: icon = v; break
    return color, icon

def render_custom_metric(label, value, color="#333", icon=""):
    html = f"""
    <div class="metric-card">
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
    if st.button("🔄 데이터/위치 재분석", use_container_width=True):
        if os.path.exists(get_file_path(CACHE_FILENAME)):
            os.remove(get_file_path(CACHE_FILENAME))
        st.session_state.weather_data = None
        st.rerun()

# ==========================================
# 4. 메인 화면 로직
# ==========================================

# 로고 로드
logo_path = get_file_path(LOGO_FILENAME)
img_base64 = get_base64_of_bin_file(logo_path) if os.path.exists(logo_path) else ""

# [수정] 헤더 레이아웃 개선
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
    warn_sites, normal_sites = [], []

    if full_text:
        for i, row in df.iterrows():
            addr = str(row.get('주소', ''))
            keywords = [t[:-1] for t in addr.replace(',', ' ').split() if t.endswith(('시', '군')) and len(t[:-1]) >= 2]
            w_list = analyze_all_warnings(full_text, keywords) if keywords else []
            df.at[i, 'warnings'] = w_list
            if w_list:
                warn_sites.append(f"{row['현장명']}")
                for w in w_list:
                    if w not in warning_summary: warning_summary[w] = []
                    warning_summary[w].append(row['현장명'])
            else:
                normal_sites.append(row['현장명'])

    # [1] 상단 지표 (높이 축소됨)
    m1, m2, m3 = st.columns(3)
    with m1: render_custom_metric("총 현장", f"{len(df)}", color="#333", icon="🏗️")
    with m2: render_custom_metric("특보 발령", f"{len(warn_sites)}", color="#FF4B4B", icon="🚨")
    with m3: render_custom_metric("이상 없음", f"{len(normal_sites)}", color="#00CC96", icon="✅")
    
    # [2] 기상청 특보 전문 (공간 절약을 위해 Expander 사용)
    st.write("") # 약간의 여백
    with st.expander("📢 기상청 특보 전문 보기 (클릭하여 펼치기)", expanded=False):
        if full_text:
            text = full_text.replace("o ", "\n o ").strip()
            st.text(text)
        else:
            st.info("현재 수신된 특보 데이터가 없습니다.")

    st.divider()

    # =========================================================================
    # 메인 레이아웃: 좌측(3.5) vs 우측(6.5)
    # =========================================================================
    col_left, col_right = st.columns([3.5, 6.5])

    # --------------------------
    # [좌측 패널]
    # --------------------------
    with col_left:
        st.markdown("##### 🔍 현장 검색")
        site_list = df['현장명'].tolist()
        # 세션 상태에 따라 인덱스 찾기
        curr_idx = site_list.index(st.session_state.selected_site) if st.session_state.selected_site in site_list else None
        
        selected_option = st.selectbox(
            "현장 선택", site_list, index=curr_idx,
            placeholder="현장명을 입력하세요", label_visibility="collapsed"
        )
        
        if selected_option != st.session_state.selected_site:
            st.session_state.selected_site = selected_option
            st.rerun()

        # 선택된 현장 정보 표시 (여기가 핵심 최적화 구간)
        if st.session_state.selected_site:
            target_row = df[df['현장명'] == st.session_state.selected_site].iloc[0]
            ws = target_row['warnings'] if target_row['warnings'] else []
            
            # [최적화] 클릭된 현장의 기온만 API 호출 (Cache 적용됨)
            current_temp, temp_time = None, None
            if pd.notna(target_row['lat']):
                current_temp, temp_time = get_current_temp_optimized(target_row['lat'], target_row['lon'])
            
            with st.container(border=True):
                status_html = f'<span class="status-badge badge-warning">🚨 특보 발령</span>' if ws else f'<span class="status-badge badge-normal">✅ 이상 없음</span>'
                st.markdown(f"""
                    <div class="site-header">
                        <span class="site-title">📍 {target_row['현장명']}</span>
                        {status_html}
                    </div>
                    <div class='site-addr'>{target_row['주소']}</div>
                """, unsafe_allow_html=True)
                
                # 기온 및 시간 표시
                if current_temp is not None:
                    st.markdown(f"""
                        <div>
                            <span class='temp-badge'>🌡️ {current_temp}℃</span>
                        </div>
                        <div class='time-caption'>기상청 {temp_time} 기준</div>
                    """, unsafe_allow_html=True)
                else:
                    st.caption("기온 데이터 수신 대기 중...")
                
                if ws:
                    st.markdown("---")
                    for w in ws:
                        color_md = ":red" if "경보" in w else ":orange"
                        st.markdown(f"{color_md}[**⚠️ {w}**]")

        else:
            st.info("지도에서 마커를 클릭하거나 위에서 현장을 검색하세요.")

        st.write("") 
        
        # 특보 리스트 및 다운로드
        st.markdown("##### 📋 특보 현황 요약")
        # 높이를 고정하여 스크롤 유도 (전체 페이지 길이 단축)
        with st.container(height=300, border=True):
            poster_img_bytes = create_warning_poster(warning_summary, len(df), len(normal_sites))
            st.download_button(
                "🖼️ 현황 포스터 다운로드", data=poster_img_bytes,
                file_name=f"기상특보_{datetime.datetime.now().strftime('%Y%m%d')}.jpg",
                mime="image/jpeg", use_container_width=True
            )
            st.divider()
            if warning_summary:
                for w_name, sites in warning_summary.items():
                    color_md = ":red" if "경보" in w_name else ":orange"
                    st.markdown(f"{color_md}[**{w_name} ({len(sites)})**]")
                    st.caption(", ".join(sites))
            else:
                st.caption("현재 특보 발령 현장이 없습니다.")

    # --------------------------
    # [우측 패널] - 지도
    # --------------------------
    with col_right:
        valid_coords = df.dropna(subset=['lat', 'lon'])
        
        # 지도 정확도 안내 문구 추가
        st.markdown("<div class='map-disclaimer'>⚠️ 본 지도는 OpenStreetMap(무료) 기반으로 실제 위치와 약간의 오차가 있을 수 있습니다.</div>", unsafe_allow_html=True)

        if not valid_coords.empty:
            if st.session_state.selected_site:
                sel = df[df['현장명'] == st.session_state.selected_site]
                if not sel.empty:
                    c_lat, c_lon, z_start = sel.iloc[0]['lat'], sel.iloc[0]['lon'], 11
                else:
                    c_lat, c_lon, z_start = 36.5, 127.5, 7
            else:
                c_lat, c_lon, z_start = 36.3, 127.8, 7  # 중심점 조정
            
            # 지도 생성
            m = folium.Map(location=[c_lat, c_lon], zoom_start=z_start, tiles='cartodbpositron') # 깔끔한 타일로 변경

            for i, row in valid_coords.iterrows():
                ws = row['warnings'] if row['warnings'] else []
                color, icon_name = get_icon_and_color(ws)
                warn_msg = ", ".join(ws) if ws else "이상 없음"
                
                # 툴팁에 현장명 표시
                folium.Marker(
                    [row['lat'], row['lon']],
                    tooltip=f"{row['현장명']} : {warn_msg}",
                    icon=folium.Icon(color=color, icon=icon_name, prefix='fa')
                ).add_to(m)
            
            # 높이 약간 축소하여 한눈에 들어오게
            map_data = st_folium(m, width=None, height=500) 
            
            # 지도 클릭 이벤트 처리
            if map_data and map_data.get("last_object_clicked_tooltip"):
                clicked_info = map_data["last_object_clicked_tooltip"]
                if clicked_info:
                    clicked_name = clicked_info.split(":")[0].strip()
                    if clicked_name != st.session_state.selected_site:
                        st.session_state.selected_site = clicked_name
                        st.rerun()

