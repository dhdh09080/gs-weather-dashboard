import streamlit as st
import pandas as pd
import requests
import datetime
import re
import folium
import pytz
from streamlit_folium import st_folium
from geopy.geocoders import Nominatim
import time
import math
import os
import base64
from PIL import Image, ImageDraw, ImageFont
import io

# ==========================================
# 1. 페이지 설정
# ==========================================
st.set_page_config(
    page_title="GS건설 현장 기상/작업통제 현황",
    layout="wide",
    initial_sidebar_state="collapsed"
)

st.markdown("""
    <style>
        .block-container { padding-top: 3rem; padding-bottom: 1rem; padding-left: 1rem; padding-right: 1rem; }
        .custom-header-box {
            display: flex; justify-content: center; align-items: center; gap: 15px;
            background-color: #f8f9fa; border: 1px solid #e0e0e0; border-radius: 12px;
            padding: 20px; margin-bottom: 10px; box-shadow: 0 1px 3px rgba(0,0,0,0.05); flex-wrap: wrap;
        }
        .header-title { font-size: 1.6rem; font-weight: 800; color: #005bac; margin: 0; line-height: 1.2; text-align: center; white-space: nowrap; }
        .header-logo-img { height: 45px; width: auto; }
        @media (prefers-color-scheme: dark) {
            .custom-header-box { background-color: #262730; border: 1px solid #464b5d; }
            .header-title { color: #ffffff; }
        }
        .metric-card { 
            background-color: #ffffff; border: 1px solid #e0e0e0; border-radius: 8px; 
            padding: 10px; height: 90px; display: flex; flex-direction: column; 
            justify-content: center; align-items: center; box-shadow: 0 1px 3px rgba(0,0,0,0.05); 
        }
        .metric-label { font-size: 0.85rem; color: #666; font-weight: 600; margin-bottom: 2px; }
        .metric-value { font-size: 1.5rem; font-weight: 800; color: #333; }
        .site-title { font-size: 1.3rem; font-weight: 800; color: #1f77b4; margin: 0; line-height: 1.2; word-break: keep-all; }
        .site-addr { font-size: 0.9rem; color: #555; margin-bottom: 8px; }
        .temp-badge { font-size: 1.2rem; font-weight: bold; color: #fff; background-color: #1f77b4; padding: 5px 12px; border-radius: 15px; display: inline-block; margin-right: 5px; }
        .time-caption { font-size: 0.8rem; color: #888; margin-top: 5px; }
        .site-header { display: flex; align-items: center; gap: 8px; margin-bottom: 5px; flex-wrap: wrap; }
        .status-badge { font-size: 0.8rem; font-weight: bold; padding: 3px 8px; border-radius: 4px; color: white; display: inline-block; white-space: nowrap; }
        .badge-normal { background-color: #28a745; }
        .badge-warning { background-color: #ff9800; }
        .badge-danger { background-color: #dc3545; } 
        .badge-critical { background-color: #512da8; }
        .map-disclaimer { font-size: 0.75rem; color: #666; background-color: rgba(255, 255, 255, 0.7); padding: 2px 5px; border-radius: 4px; margin-bottom: 2px; text-align: right; }
        
        .stButton>button { border-radius: 8px; font-weight: bold; }
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

geolocator = Nominatim(user_agent="korea_weather_guard_gs_final_update", timeout=15)

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

@st.cache_resource
def load_custom_font(size=20):
    try:
        font_files = ["Pretendard-Bold.ttf", "Pretendard-Medium.ttf", "Pretendard-Regular.ttf"]
        for f in font_files:
            path = get_file_path(f)
            if os.path.exists(path): return ImageFont.truetype(path, size)
        
        font_url = "https://github.com/google/fonts/raw/main/ofl/nanumgothic/NanumGothic-Bold.ttf"
        font_path = "NanumGothic-Bold.ttf"
        if not os.path.exists(font_path):
            try:
                r = requests.get(font_url, timeout=3)
                with open(font_path, "wb") as f: f.write(r.content)
            except: pass 
        if os.path.exists(font_path): return ImageFont.truetype(font_path, size)
    except: pass
    return ImageFont.load_default()

# -----------------------------------------------------------
# [포스터 생성 함수 - 수정됨]
# -----------------------------------------------------------
def create_warning_poster(full_df, warning_summary, temp_stop_summary):
    # A4 Size (300dpi)
    W, H = 2480, 3508
    img = Image.new('RGB', (W, H), color='#FFFFFF')
    draw = ImageDraw.Draw(img)
    
    # 폰트 로드
    font_title = load_custom_font(130)
    font_subtitle = load_custom_font(55)
    font_section = load_custom_font(75)
    font_box_title = load_custom_font(65)
    font_content = load_custom_font(50) # 폰트 사이즈 조정
    font_safety_title = load_custom_font(70)
    font_safety_content = load_custom_font(50)
    font_footer = load_custom_font(40)

    # 레이아웃 설정
    margin_x = 100
    content_width = W - (margin_x * 2)
    box_padding = 60
    box_radius = 40
    line_sp = 70

    # 1. 헤더
    header_height = 450
    draw.rectangle([(0, 0), (W, header_height)], fill="#005bac")
    
    title_text = "GS건설 현장 기상 및 작업통제 현황"
    bbox = draw.textbbox((0, 0), title_text, font=font_title)
    text_w = bbox[2] - bbox[0]
    draw.text(((W - text_w) / 2, 140), title_text, font=font_title, fill="white")

    kst = pytz.timezone('Asia/Seoul')
    current_time = datetime.datetime.now(kst).strftime('%Y년 %m월 %d일 %H:%M 기준')
    
    bbox = draw.textbbox((0, 0), current_time, font=font_subtitle)
    text_w = bbox[2] - bbox[0]
    draw.text(((W - text_w) / 2, 320), current_time, font=font_subtitle, fill="#dddddd")

    # 2. 박스 그리기 함수
    def draw_warning_box(title, title_color, bg_color, border_color, sites, start_y):
        if not sites: return start_y
        
        sites_str = ", ".join(sites)
        max_w = content_width - (box_padding * 2)
        lines = []
        words = sites_str.split(' ')
        curr_line = ""
        for word in words:
            test_line = curr_line + word + " "
            if draw.textbbox((0, 0), test_line, font=font_content)[2] > max_w:
                lines.append(curr_line)
                curr_line = word + " "
            else:
                curr_line = test_line
        if curr_line: lines.append(curr_line)
        
        box_h = box_padding * 2 + 80 + (len(lines) * line_sp) + 20
        draw.rounded_rectangle([(margin_x, start_y), (W - margin_x, start_y + box_h)], 
                               radius=box_radius, fill=bg_color, outline=border_color, width=5)
        
        tx, ty = margin_x + box_padding, start_y + box_padding
        draw.text((tx, ty), title, font=font_box_title, fill=title_color)
        ty += 100
        for line in lines:
            draw.text((tx, ty), line, font=font_content, fill="#333333")
            ty += line_sp
            
        return start_y + box_h + 60 

    current_y = header_height + 100
    draw.text((margin_x, current_y), "■ 혹한기 작업 중지 및 기상 특보 현황", font=font_section, fill="#333333")
    current_y += 120

    is_empty = True
    
    # [우선순위 1] -15도 이하 (전면 작업 중지)
    sites_stop_all = temp_stop_summary.get('stop_all', [])
    if sites_stop_all:
        current_y = draw_warning_box(f"⛔ 전면 작업중지 (영하 15℃ 이하, {len(sites_stop_all)}개소)", 
                                     "#ffffff", "#311b92", "#512da8", sites_stop_all, current_y)
        is_empty = False

    # [우선순위 2] -12도 이하 (옥외 작업 중지)
    sites_stop_out = temp_stop_summary.get('stop_out', [])
    if sites_stop_out:
        current_y = draw_warning_box(f"🛑 옥외 작업중지 (영하 12℃ 이하, {len(sites_stop_out)}개소)", 
                                     "#b71c1c", "#ffebee", "#ef9a9a", sites_stop_out, current_y)
        is_empty = False

    # [우선순위 3] 기상청 특보 (이미 작업중지에 포함된 현장은 제외할 수도 있으나, 여기선 다 보여줌)
    # 기존 코드의 warning_summary 활용
    sites_heat_warning = []
    sites_others = [] 
    
    # (폭염 등 다른 특보 분류 - 겨울철이라 적겠지만 로직 유지)
    for w_name, sites in warning_summary.items():
        if "건조" in w_name: continue
        # 한파 특보는 위 작업중지와 겹칠 수 있으나 기상청 공식 발령이므로 표기
        if "폭염" in w_name: sites_heat_warning.extend(sites)
        else: sites_others.append((w_name, sites))
    
    if sites_heat_warning:
         current_y = draw_warning_box(f"🔥 폭염 특보 ({len(sites_heat_warning)}개소)", "#d32f2f", "#ffebee", "#ffcdd2", list(set(sites_heat_warning)), current_y)
         is_empty = False

    # 기타 특보 (한파주의보/경보 포함)
    for w_name, s_list in sites_others:
        # 작업 중지 대상인 현장은 기상청 특보 리스트에서 뺄 것인지? -> 중복되더라도 정보 제공 차원에서 표시하되 색상을 다르게
        color = "#1565c0"; bg = "#e3f2fd"; bd = "#90caf9"
        if "한파" in w_name: color="#0277bd"; bg="#e1f5fe"; bd="#b3e5fc"
        elif "대설" in w_name: color="#546e7a"; bg="#eceff1"; bd="#cfd8dc"
        
        current_y = draw_warning_box(f"⚠️ {w_name} ({len(s_list)}개소)", color, bg, bd, s_list, current_y)
        is_empty = False

    if is_empty:
        draw.rounded_rectangle([(margin_x, current_y), (W - margin_x, current_y + 300)], radius=box_radius, fill="#f1f8e9", outline="#c8e6c9", width=5)
        draw.text((margin_x + 60, current_y + 110), "현재 작업 통제 기준 도달 및 기상 특보가 없습니다.", font=font_box_title, fill="#33691e")
        current_y += 300

    # 3. 하단 안전수칙
    bottom_start_y = H - 1400 
    if current_y < bottom_start_y: current_y = bottom_start_y

    def draw_safety_box(title, content, color_set, start_y):
        t_col, bg_col, bd_col = color_set
        box_h = 600
        draw.rounded_rectangle([(margin_x, start_y), (W - margin_x, start_y + box_h)], 
                               radius=box_radius, fill=bg_col, outline=bd_col, width=5)
        
        tx, ty = margin_x + box_padding, start_y + box_padding
        draw.text((tx, ty), title, font=font_safety_title, fill=t_col)
        ty += 110
        draw.multiline_text((tx + 20, ty), content.strip(), font=font_safety_content, fill="#333333", spacing=35)
        return start_y + box_h + 60

    # 겨울철 안전수칙 고정 출력
    content = """
[GS건설 혹한기 작업 중지 기준]
• 영하 12℃ 이하: 옥외 작업 중지 (Warm-up, 휴식시간 준수)
• 영하 15℃ 이하: 옥내/옥외 전면 작업 중지
[한랭질환 예방 수칙]
• 따뜻한 옷(3겹 이상), 따뜻한 물, 따뜻한 장소(휴게시설) 마련
• 추운 시간대(새벽, 아침) 작업 축소 및 유연한 근무시간 운영
    """
    current_y = draw_safety_box("※ 혹한기 현장 안전수칙 및 작업 중지 기준 안내", content, ("#1a237e", "#e8eaf6", "#9fa8da"), current_y)

    # 4. 푸터
    draw.line([(50, H-150), (W-50, H-150)], fill="#cccccc", width=5)
    footer_text = "GS E&C 안전보건팀"
    bbox = draw.textbbox((0, 0), footer_text, font=font_footer)
    f_w = bbox[2] - bbox[0]
    draw.text(((W - f_w) / 2, H - 100), footer_text, font=font_footer, fill="#888888")

    img_byte_arr = io.BytesIO()
    img.save(img_byte_arr, format='JPEG', quality=95)
    return img_byte_arr.getvalue()

# ==========================================
# 5. 좌표 변환 및 API
# ==========================================
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

# [수정] 기온 캐시 제거 (실시간성 중요) -> 또는 TTL 짧게
@st.cache_data(ttl=300) 
def get_current_temp_optimized(lat, lon):
    try:
        nx, ny = dfs_xy_conv(lat, lon)
        
        kst = pytz.timezone('Asia/Seoul')
        now = datetime.datetime.now(kst)
        
        # 기상청 초단기실황 API (매시 정각 호출 권장, 40분 이후)
        if now.minute <= 40: 
            target_time = now - datetime.timedelta(hours=1)
        else:
            target_time = now
        base_date = target_time.strftime('%Y%m%d')
        base_time = target_time.strftime('%H00') 
        base_url = "http://apis.data.go.kr/1360000/VilageFcstInfoService_2.0/getUltraSrtNcst"
        query_params = f"?serviceKey={API_KEY_ENCODED}&pageNo=1&numOfRows=10&dataType=JSON&base_date={base_date}&base_time={base_time}&nx={nx}&ny={ny}"
        response = requests.get(base_url + query_params, timeout=2) # 타임아웃 짧게
        data = response.json()
        if data['response']['header']['resultCode'] == '00':
            items = data['response']['body']['items']['item']
            for item in items:
                if item['category'] == 'T1H': 
                    formatted_time = f"{base_date[4:6]}월 {base_date[6:8]}일 {base_time[:2]}:00"
                    return float(item['obsrValue']), formatted_time
        return None, None
    except Exception:
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
    
    ALLOWED_KEYWORDS = ["한파", "폭염", "호우", "대설", "태풍", "강풍"]
    
    for match in matches:
        w_name = match.group(1).strip()
        content = match.group(2)
        
        if "건조" in w_name: continue
            
        is_allowed = False
        for allowed in ALLOWED_KEYWORDS:
            if allowed in w_name:
                is_allowed = True
                break
        
        if not is_allowed: continue 

        for key in keywords:
            if key in content:
                detected_warnings.append(w_name)
                break
                
    return list(set(detected_warnings))

def get_icon_and_color(warning_list, temp_val):
    # 1순위: 온도 기준 작업 중지
    if temp_val is not None:
        if temp_val <= -15:
            return "purple", "ban-circle" # 전면 중지
        if temp_val <= -12:
            return "red", "minus-sign" # 옥외 중지

    # 2순위: 기상청 특보
    if not warning_list: return "blue", "info-sign"
    is_warning = any("경보" in w for w in warning_list)
    color = "orange" if not is_warning else "darkred"
    
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
        st.cache_data.clear()
        st.rerun()

# ==========================================
# 4. 메인 화면 로직
# ==========================================

logo_path = get_file_path(LOGO_FILENAME)
img_base64 = get_base64_of_bin_file(logo_path) if os.path.exists(logo_path) else ""

st.markdown(
    f"""
    <div class="custom-header-box">
        <div class="header-title">GS건설 현장 기상정보 시스템</div>
        <img src="data:image/png;base64,{img_base64}" class="header-logo-img">
    </div>
    """,
    unsafe_allow_html=True
)

col_btn, _ = st.columns([2, 8])
with col_btn:
    if st.button("🔄 실시간 데이터 업데이트", use_container_width=True):
        st.cache_data.clear()
        st.session_state.weather_data = None
        st.rerun()

if st.session_state.weather_data is None:
    st.session_state.weather_data = load_data_once()

df = st.session_state.weather_data

if not df.empty:
    full_text = get_weather_status()
    df['warnings'] = None
    df['temp_val'] = None 
    df['temp_time'] = None
    df['status_label'] = "정상" # 디폴트

    warning_summary = {}
    temp_stop_summary = {"stop_all": [], "stop_out": []} # -15도, -12도 현장 저장
    
    warn_sites, normal_sites = [], []

    # ----------------------------------------------------
    # [핵심 수정] 모든 현장에 대해 기온 조회 (Loop)
    # ----------------------------------------------------
    total_sites = len(df)
    
    # 세션 스테이트에 기온 데이터가 이미 있는지 확인 (새로고침 시 재호출 방지 로직이 필요하면 추가 가능)
    # 여기선 '실시간 업데이트'를 위해 매번 로딩바를 띄우고 조회합니다.
    
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    # 기온 데이터 컬럼이 비어있다면 채워넣기
    sites_with_issues = []

    for i, row in df.iterrows():
        # 진행률 표시 (너무 빠르면 생략 가능하나 API 호출 딜레이 고려)
        status_text.caption(f"🌡️ 실시간 기온 분석 중... ({i+1}/{total_sites}) - {row['현장명']}")
        progress_bar.progress((i + 1) / total_sites)
        
        # 1. 기상청 특보 분석
        addr = str(row.get('주소', ''))
        keywords = [t[:-1] for t in addr.replace(',', ' ').split() if t.endswith(('시', '군')) and len(t[:-1]) >= 2]
        w_list = analyze_all_warnings(full_text, keywords) if keywords else []
        df.at[i, 'warnings'] = w_list
        
        # 2. 실시간 기온 조회 (좌표 있는 경우만)
        current_temp, temp_time = None, None
        if pd.notna(row['lat']):
            current_temp, temp_time = get_current_temp_optimized(row['lat'], row['lon'])
            df.at[i, 'temp_val'] = current_temp
            df.at[i, 'temp_time'] = temp_time

        # 3. 상태 판별 로직
        site_status = "정상"
        is_issue = False
        
        # -15도 이하 (전면 중지)
        if current_temp is not None and current_temp <= -15:
            site_status = "⛔ 전면작업중지"
            temp_stop_summary["stop_all"].append(row['현장명'])
            is_issue = True
        # -12도 이하 (옥외 중지)
        elif current_temp is not None and current_temp <= -12:
            site_status = "🛑 옥외작업중지"
            temp_stop_summary["stop_out"].append(row['현장명'])
            is_issue = True
        # 기상청 특보 존재
        elif w_list:
            site_status = "⚠️ 기상특보"
            is_issue = True
        
        df.at[i, 'status_label'] = site_status
        
        if is_issue:
            warn_sites.append(row['현장명'])
        else:
            normal_sites.append(row['현장명'])
            
        # 특보 요약 집계
        for w in w_list:
            if w not in warning_summary: warning_summary[w] = []
            warning_summary[w].append(row['현장명'])
            
    status_text.empty()
    progress_bar.empty()
    
    # ----------------------------------------------------
    # 대시보드 출력
    # ----------------------------------------------------
    m1, m2, m3, m4 = st.columns(4)
    with m1: render_custom_metric("전체 현장", f"{len(df)}", color="#333", icon="🏗️")
    with m2: render_custom_metric("전면작업중지", f"{len(temp_stop_summary['stop_all'])}", color="#512da8", icon="⛔")
    with m3: render_custom_metric("옥외작업중지", f"{len(temp_stop_summary['stop_out'])}", color="#d32f2f", icon="🛑")
    with m4: render_custom_metric("기상 특보", f"{len(warn_sites) - len(temp_stop_summary['stop_all']) - len(temp_stop_summary['stop_out'])}", color="#ff9800", icon="⚠️")
    
    st.divider()

    col_left, col_right = st.columns([4, 6])

    with col_left:
        st.markdown("##### 🔍 현장 상세 확인")
        site_list = df['현장명'].tolist()
        curr_idx = site_list.index(st.session_state.selected_site) if st.session_state.selected_site in site_list else None
        
        selected_option = st.selectbox(
            "현장 선택", site_list, index=curr_idx,
            placeholder="현장명을 입력하세요", label_visibility="collapsed"
        )
        
        if selected_option != st.session_state.selected_site:
            st.session_state.selected_site = selected_option
            st.rerun()

        if st.session_state.selected_site:
            target_row = df[df['현장명'] == st.session_state.selected_site].iloc[0]
            ws = target_row['warnings']
            curr_temp = target_row['temp_val']
            t_time = target_row['temp_time']
            status_txt = target_row['status_label']
            
            # 뱃지 스타일 결정
            badge_cls = "badge-normal"
            if "전면" in status_txt: badge_cls = "badge-critical"
            elif "옥외" in status_txt: badge_cls = "badge-danger"
            elif "특보" in status_txt: badge_cls = "badge-warning"
            
            with st.container(border=True):
                st.markdown(f"""
                    <div class="site-header">
                        <span class="site-title">📍 {target_row['현장명']}</span>
                        <span class="status-badge {badge_cls}">{status_txt}</span>
                    </div>
                    <div class='site-addr'>{target_row['주소']}</div>
                """, unsafe_allow_html=True)
                
                if curr_temp is not None:
                    st.markdown(f"""
                        <div>
                            <span class='temp-badge'>🌡️ {curr_temp}℃</span>
                        </div>
                        <div class='time-caption'>기상청 {t_time} 실시간 관측 기준</div>
                    """, unsafe_allow_html=True)
                    
                    # 작업 중지 메시지 강조
                    if curr_temp <= -15:
                        st.error("⛔ [긴급] 현재 영하 15도 이하입니다. 옥내/옥외 모든 작업을 중지하십시오.")
                    elif curr_temp <= -12:
                        st.error("🛑 [경고] 현재 영하 12도 이하입니다. 옥외 작업을 중지하고 보온 조치하십시오.")
                        
                else:
                    st.caption("기온 데이터 수신 실패")
                
                if ws:
                    st.markdown("---")
                    st.caption("발효 중인 기상청 특보:")
                    for w in ws:
                        color_md = ":red" if "경보" in w else ":orange"
                        st.markdown(f"{color_md}[**⚠️ {w}**]")
        else:
            st.info("지도 마커를 클릭하거나 목록에서 현장을 선택하세요.")

        st.write("") 
        
        st.markdown("##### 📋 현황 포스터 다운로드")
        with st.container(height=120, border=True):
            try:
                # 포스터 생성 시 temp_stop_summary 전달
                poster_img_bytes = create_warning_poster(df, warning_summary, temp_stop_summary)
                
                kst = pytz.timezone('Asia/Seoul')
                now_kst = datetime.datetime.now(kst)
                
                st.download_button(
                    "🖼️ 현황 포스터(A4) 다운로드", data=poster_img_bytes,
                    file_name=f"현장기상_작업통제현황_{now_kst.strftime('%Y%m%d_%H%M')}.jpg",
                    mime="image/jpeg", use_container_width=True
                )
            except Exception as e:
                st.error(f"포스터 생성 오류: {e}")

    with col_right:
        valid_coords = df.dropna(subset=['lat', 'lon'])
        st.markdown("<div class='map-disclaimer'>⚠️ 색상 구분: 보라색(-15℃↓), 빨간색(-12℃↓), 주황/적색(특보), 파란색(정상)</div>", unsafe_allow_html=True)

        if not valid_coords.empty:
            if st.session_state.selected_site:
                sel = df[df['현장명'] == st.session_state.selected_site]
                if not sel.empty:
                    c_lat, c_lon, z_start = sel.iloc[0]['lat'], sel.iloc[0]['lon'], 10
                else:
                    c_lat, c_lon, z_start = 36.5, 127.5, 7
            else:
                c_lat, c_lon, z_start = 36.3, 127.8, 7 
            
            m = folium.Map(location=[c_lat, c_lon], zoom_start=z_start, tiles='cartodbpositron') 

            for i, row in valid_coords.iterrows():
                ws = row['warnings']
                temp = row['temp_val']
                status = row['status_label']
                
                # 색상/아이콘 결정 로직 (온도 우선)
                color, icon_name = get_icon_and_color(ws, temp)
                
                popup_msg = f"{row['현장명']}: {temp}℃ / {status}"
                
                folium.Marker(
                    [row['lat'], row['lon']],
                    tooltip=popup_msg,
                    icon=folium.Icon(color=color, icon=icon_name, prefix='fa')
                ).add_to(m)
            
            map_data = st_folium(m, width=None, height=600) 
            
            if map_data and map_data.get("last_object_clicked_tooltip"):
                clicked_info = map_data["last_object_clicked_tooltip"]
                if clicked_info:
                    clicked_name = clicked_info.split(":")[0].strip()
                    if clicked_name != st.session_state.selected_site:
                        st.session_state.selected_site = clicked_name
                        st.rerun()
