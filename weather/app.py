"""
GS건설 현장 기상/작업통제 현황 시스템
====================================
기상청 API를 활용하여 전국 건설 현장의 실시간 기상 특보 및
혹한기 작업 통제 현황을 모니터링하는 대시보드 앱
"""

# ============================================================
# 라이브러리 임포트
# ============================================================
import os
import re
import io
import math
import time
import base64
import datetime

import pytz
import requests
import pandas as pd
import folium
import streamlit as st
from PIL import Image, ImageDraw, ImageFont
from geopy.geocoders import Nominatim
from streamlit_folium import st_folium


# ============================================================
# 상수 및 설정값
# ============================================================
EXCEL_FILENAME  = "site_list.xlsx"
CACHE_FILENAME  = "site_list_cached.csv"
LOGO_FILENAME   = "gslogo.png"
KST             = pytz.timezone("Asia/Seoul")

# 혹한기 작업 중지 기준 온도 (℃)
TEMP_STOP_ALL   = -15   # 전면(옥내+옥외) 작업 중지
TEMP_STOP_OUT   = -12   # 옥외 작업 중지

# 지도 기본 중심 좌표 (한반도 중심)
MAP_DEFAULT_LAT = 36.3
MAP_DEFAULT_LON = 127.8
MAP_DEFAULT_ZOOM = 7

# 기상청 API Base URL
API_WEATHER_WARN  = "http://apis.data.go.kr/1360000/WthrWrnInfoService/getPwnStatus"
API_ULTRA_FCST    = "http://apis.data.go.kr/1360000/VilageFcstInfoService_2.0/getUltraSrtNcst"

ALLOWED_WARNING_KEYWORDS = ["한파", "폭염", "호우", "대설", "태풍", "강풍"]
ICON_MAP = {
    "한파": "asterisk",
    "건조": "fire",
    "폭염": "sun",
    "호우": "tint",
    "대설": "snowflake-o",
    "태풍": "bullseye",
    "강풍": "flag",
}

geolocator = Nominatim(user_agent="korea_weather_guard_gs_final_update", timeout=15)


# ============================================================
# 페이지 기본 설정
# ============================================================
st.set_page_config(
    page_title="GS건설 현장 기상/작업통제 현황",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
    /* 전체 레이아웃 */
    .block-container { padding-top: 1rem; }

    /* 헤더 박스 */
    .custom-header-box {
        display: flex;
        justify-content: center;
        align-items: center;
        gap: 15px;
        background-color: #f8f9fa;
        border: 1px solid #e0e0e0;
        border-radius: 12px;
        padding: 20px;
        margin-bottom: 10px;
        box-shadow: 0 1px 3px rgba(0,0,0,0.05);
        flex-wrap: wrap;
    }
    .header-title {
        font-size: 1.6rem;
        font-weight: 800;
        color: #005bac;
        margin: 0;
        line-height: 1.2;
        text-align: center;
        white-space: nowrap;
    }
    .header-logo-img { height: 45px; width: auto; }

    /* 다크모드 대응 */
    @media (prefers-color-scheme: dark) {
        .custom-header-box { background-color: #262730; border: 1px solid #464b5d; }
        .header-title { color: #ffffff; }
    }

    /* 요약 메트릭 카드 */
    .metric-card {
        background-color: #ffffff;
        border: 1px solid #e0e0e0;
        border-radius: 8px;
        padding: 10px;
        height: 90px;
        display: flex;
        flex-direction: column;
        justify-content: center;
        align-items: center;
        box-shadow: 0 1px 3px rgba(0,0,0,0.05);
    }
    .metric-label { font-size: 0.85rem; color: #666; font-weight: 600; margin-bottom: 2px; }
    .metric-value { font-size: 1.5rem; font-weight: 800; color: #333; }

    /* 현장 상세 카드 */
    .site-header    { display: flex; align-items: center; gap: 8px; margin-bottom: 5px; flex-wrap: wrap; }
    .site-title     { font-size: 1.3rem; font-weight: 800; color: #1f77b4; margin: 0; line-height: 1.2; word-break: keep-all; }
    .site-addr      { font-size: 0.9rem; color: #555; margin-bottom: 8px; }
    .temp-badge     { font-size: 1.2rem; font-weight: bold; color: #fff; background-color: #1f77b4; padding: 5px 12px; border-radius: 15px; display: inline-block; margin-right: 5px; }
    .time-caption   { font-size: 0.8rem; color: #888; margin-top: 5px; }

    /* 상태 뱃지 */
    .status-badge   { font-size: 0.8rem; font-weight: bold; padding: 3px 8px; border-radius: 4px; color: white; display: inline-block; white-space: nowrap; }
    .badge-normal   { background-color: #28a745; }
    .badge-warning  { background-color: #ff9800; }
    .badge-danger   { background-color: #dc3545; }
    .badge-critical { background-color: #512da8; }

    /* 지도 면책 문구 */
    .map-disclaimer {
        font-size: 0.75rem;
        color: #666;
        background-color: rgba(255,255,255,0.7);
        padding: 2px 5px;
        border-radius: 4px;
        margin-bottom: 2px;
        text-align: right;
    }

    /* 버튼 공통 스타일 */
    .stButton>button { border-radius: 8px; font-weight: bold; }
</style>
""", unsafe_allow_html=True)


# ============================================================
# Secrets 로드
# ============================================================
try:
    API_KEY_ENCODED  = st.secrets["api_key"]
    TELEGRAM_TOKEN   = st.secrets.get("telegram_token", None)
    TELEGRAM_CHAT_ID = st.secrets.get("telegram_chat_id", None)
except FileNotFoundError:
    st.error("secrets.toml 파일이 없거나 api_key가 설정되지 않았습니다.")
    st.stop()


# ============================================================
# Session State 초기화
# ============================================================
_defaults = {
    "weather_data":   None,
    "processed_data": None,
    "selected_site":  None,
    "analysis_done":  False,
}
for key, val in _defaults.items():
    if key not in st.session_state:
        st.session_state[key] = val


# ============================================================
# 유틸리티 함수
# ============================================================

def get_file_path(filename: str) -> str:
    """현재 스크립트 디렉토리 기준 절대 경로 반환"""
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), filename)


def get_base64_of_bin_file(bin_file: str) -> str:
    """바이너리 파일을 Base64 문자열로 인코딩"""
    with open(bin_file, "rb") as f:
        return base64.b64encode(f.read()).decode()


def get_kst_now() -> datetime.datetime:
    """현재 한국 표준시(KST) 반환"""
    return datetime.datetime.now(KST)


# ============================================================
# 텔레그램 알림 함수
# ============================================================

def send_telegram_alert(token: str, chat_id: str, message: str) -> tuple[bool, str]:
    """텔레그램 메시지 전송. (성공 여부, 메시지) 튜플 반환"""
    if not token or not chat_id:
        return False, "텔레그램 토큰 또는 채팅방 ID가 설정되지 않았습니다."

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    try:
        resp = requests.post(url, json={"chat_id": chat_id, "text": message}, timeout=5)
        if resp.status_code == 200:
            return True, "성공적으로 전송했습니다."
        return False, f"전송 실패 (Status: {resp.status_code})"
    except Exception as e:
        return False, f"전송 중 오류 발생: {e}"


def build_telegram_message(df_proc: pd.DataFrame) -> str:
    """분석 완료된 DataFrame으로부터 텔레그램 전송 메시지 구성"""
    now_str = get_kst_now().strftime("%Y년 %m월 %d일 %H:%M 기준")
    lines = [f"🚨 [GS건설 현장 기온 모니터링]\n{now_str}\n"]

    if "temp_val" in df_proc.columns:
        stop_all = df_proc[df_proc["temp_val"] <= TEMP_STOP_ALL]
        stop_out = df_proc[(df_proc["temp_val"] > TEMP_STOP_ALL) & (df_proc["temp_val"] <= TEMP_STOP_OUT)]
    else:
        stop_all = stop_out = pd.DataFrame()

    if not stop_all.empty:
        lines.append(f"\n⛔ 옥외/옥내 작업중지 ({TEMP_STOP_ALL}℃ 이하): {len(stop_all)}개소")
        for _, row in stop_all.iterrows():
            lines.append(f" - {row['현장명']} ({row['temp_val']}℃)")

    if not stop_out.empty:
        lines.append(f"\n🛑 옥외작업중지 ({TEMP_STOP_OUT}℃ 이하): {len(stop_out)}개소")
        for _, row in stop_out.iterrows():
            lines.append(f" - {row['현장명']} ({row['temp_val']}℃)")

    if stop_all.empty and stop_out.empty:
        lines.append(f"\n✅ 현재 혹한기 작업 중지 기준({TEMP_STOP_OUT}℃ 이하)에 해당하는 현장이 없습니다.")

    return "\n".join(lines)


# ============================================================
# 기상청 API 연동 함수
# ============================================================

def dfs_xy_conv(lat: float, lon: float) -> tuple[int, int]:
    """위경도 → 기상청 격자 좌표(nx, ny) 변환"""
    RE, GRID = 6371.00877, 5.0
    SLAT1, SLAT2, OLON, OLAT = 30.0, 60.0, 126.0, 38.0
    XO, YO = 43, 136
    DEGRAD = math.pi / 180.0

    re   = RE / GRID
    sn   = math.log(math.cos(SLAT1 * DEGRAD) / math.cos(SLAT2 * DEGRAD)) / \
           math.log(math.tan(math.pi * 0.25 + SLAT2 * DEGRAD * 0.5) /
                    math.tan(math.pi * 0.25 + SLAT1 * DEGRAD * 0.5))
    sf   = math.pow(math.tan(math.pi * 0.25 + SLAT1 * DEGRAD * 0.5), sn) * \
           math.cos(SLAT1 * DEGRAD) / sn
    ro   = re * sf / math.pow(math.tan(math.pi * 0.25 + OLAT * DEGRAD * 0.5), sn)
    ra   = re * sf / math.pow(math.tan(math.pi * 0.25 + lat * DEGRAD * 0.5), sn)

    theta = lon * DEGRAD - OLON * DEGRAD
    theta = max(min(theta, math.pi), -math.pi)
    theta *= sn

    nx = math.floor(ra * math.sin(theta) + XO + 0.5)
    ny = math.floor(ro - ra * math.cos(theta) + YO + 0.5)
    return int(nx), int(ny)


@st.cache_data(ttl=300)
def get_current_temp(lat: float, lon: float) -> tuple[float | None, str | None]:
    """
    기상청 초단기실황 API로 현재 기온 조회.
    (기온값, '월일 HH:00' 형식의 관측 시각) 튜플 반환.
    값이 없으면 (None, None) 반환.
    """
    try:
        nx, ny = dfs_xy_conv(lat, lon)
        now = get_kst_now()
        # 정각 40분 이전이면 1시간 전 데이터 사용
        target = now - datetime.timedelta(hours=1) if now.minute <= 40 else now
        base_date = target.strftime("%Y%m%d")
        base_time = target.strftime("%H00")

        params = (
            f"?serviceKey={API_KEY_ENCODED}"
            f"&pageNo=1&numOfRows=10&dataType=JSON"
            f"&base_date={base_date}&base_time={base_time}"
            f"&nx={nx}&ny={ny}"
        )
        resp = requests.get(API_ULTRA_FCST + params, timeout=2)
        data = resp.json()

        if data["response"]["header"]["resultCode"] == "00":
            for item in data["response"]["body"]["items"]["item"]:
                if item["category"] == "T1H":
                    time_label = f"{base_date[4:6]}월 {base_date[6:8]}일 {base_time[:2]}:00"
                    return float(item["obsrValue"]), time_label
    except Exception:
        pass
    return None, None


def get_weather_warning_text() -> str | None:
    """기상청 특보 전문 텍스트 조회"""
    url = f"{API_WEATHER_WARN}?serviceKey={API_KEY_ENCODED}&numOfRows=10&pageNo=1&dataType=JSON"
    try:
        resp = requests.get(url, timeout=5)
        data = resp.json()
        items = data["response"]["body"]["items"]["item"]
        if items:
            return items[0].get("t6", "")
    except Exception:
        pass
    return None


def analyze_warnings(full_text: str, keywords: list[str]) -> list[str]:
    """
    특보 전문(full_text)에서 지역 키워드(keywords)에 해당하는 특보 목록 추출.
    건조 특보는 제외하고, ALLOWED_WARNING_KEYWORDS에 포함된 유형만 반환.
    """
    if not full_text:
        return []

    clean_text = full_text.replace("\r", " ").replace("\n", " ")
    detected = []

    for match in re.finditer(r"o\s*([^:]+)\s*:\s*(.*?)(?=o\s|$)", clean_text):
        w_name  = match.group(1).strip()
        content = match.group(2)

        # 건조 특보 제외
        if "건조" in w_name:
            continue

        # 허용된 특보 유형만 처리
        if not any(kw in w_name for kw in ALLOWED_WARNING_KEYWORDS):
            continue

        # 지역 키워드 매칭
        if any(kw in content for kw in keywords):
            detected.append(w_name)

    return list(set(detected))


# ============================================================
# 좌표 변환 함수
# ============================================================

def get_coordinates(address: str) -> tuple[float | None, float | None]:
    """주소 문자열 → (위도, 경도) 변환. 변환 실패 시 (None, None) 반환"""
    if pd.isna(address) or str(address).strip() == "":
        return None, None

    clean_addr = re.sub(r"\([^)]*\)", "", str(address)).strip()
    tokens = clean_addr.split()
    candidates = [clean_addr]
    if len(tokens) > 3:
        candidates.append(" ".join(tokens[:3]))
    if len(tokens) >= 2:
        candidates.append(" ".join(tokens[:2]))

    for cand in candidates:
        try:
            location = geolocator.geocode(cand)
            if location:
                return location.latitude, location.longitude
            time.sleep(0.3)
        except Exception:
            time.sleep(0.5)

    return None, None


# ============================================================
# 데이터 로드 함수
# ============================================================

def load_site_data() -> pd.DataFrame:
    """
    현장 목록 엑셀 파일 로드.
    캐시 CSV가 존재하면 해당 파일 우선 사용.
    최초 로드 시 주소 → 좌표 변환 후 캐시 CSV 저장.
    """
    excel_path = get_file_path(EXCEL_FILENAME)
    cache_path = get_file_path(CACHE_FILENAME)

    # 캐시 파일 우선 사용
    if os.path.exists(cache_path):
        try:
            return pd.read_csv(cache_path)
        except Exception:
            pass

    # 엑셀 파일 없으면 에러
    if not os.path.exists(excel_path):
        st.error(f"❌ 파일을 찾을 수 없습니다: {excel_path}")
        return pd.DataFrame()

    try:
        df = pd.read_excel(excel_path, engine="openpyxl")

        if "주소" in df.columns:
            df["주소"] = df["주소"].fillna("").astype(str)

            # 좌표 컬럼이 없거나 모두 비어있을 때만 변환 수행
            if "lat" not in df.columns or df["lat"].isnull().all():
                with st.status("🚀 최초 1회 위치 분석 중...", expanded=True) as status:
                    lats, lons = [], []
                    total = len(df)
                    for i, addr in enumerate(df["주소"]):
                        if i % 10 == 0:
                            status.update(label=f"주소 변환 중... ({i}/{total})")
                        lat, lon = get_coordinates(addr)
                        lats.append(lat)
                        lons.append(lon)
                    status.update(label="✅ 분석 완료!", state="complete", expanded=False)

                df["lat"] = lats
                df["lon"] = lons
                df.to_csv(cache_path, index=False, encoding="utf-8-sig")

        return df

    except Exception as e:
        st.error(f"❌ 오류 발생: {e}")
        return pd.DataFrame()


# ============================================================
# 상태 판별 & UI 헬퍼 함수
# ============================================================

def classify_site_status(temp: float | None, warnings: list[str]) -> str:
    """현재 기온과 특보 목록을 기반으로 현장 상태 문자열 반환"""
    if temp is not None:
        if temp <= TEMP_STOP_ALL:
            return "⛔ 전면작업중지"
        if temp <= TEMP_STOP_OUT:
            return "🛑 옥외작업중지"
    if warnings:
        return "⚠️ 기상특보"
    return "정상"


def get_map_icon(warnings: list[str], temp: float | None) -> tuple[str, str]:
    """Folium 마커에 사용할 (색상, 아이콘명) 반환"""
    if temp is not None:
        if temp <= TEMP_STOP_ALL:
            return "purple", "ban-circle"
        if temp <= TEMP_STOP_OUT:
            return "red", "minus-sign"

    if not warnings:
        return "blue", "info-sign"

    is_severe = any("경보" in w for w in warnings)
    color = "darkred" if is_severe else "orange"
    icon = "exclamation"
    for keyword, icon_name in ICON_MAP.items():
        if any(keyword in w for w in warnings):
            icon = icon_name
            break
    return color, icon


def get_status_badge_class(status: str) -> str:
    """상태 문자열에 따른 CSS 뱃지 클래스 반환"""
    if "전면" in status:
        return "badge-critical"
    if "옥외" in status:
        return "badge-danger"
    if "특보" in status:
        return "badge-warning"
    return "badge-normal"


def render_metric_card(label: str, value: str, color: str = "#333", icon: str = "") -> None:
    """요약 수치 카드 렌더링"""
    st.markdown(f"""
    <div class="metric-card">
        <div class="metric-label">{icon} {label}</div>
        <div class="metric-value" style="color: {color};">{value}</div>
    </div>
    """, unsafe_allow_html=True)


# ============================================================
# 포스터 생성 함수
# ============================================================

@st.cache_resource
def load_custom_font(size: int = 20):
    """커스텀 폰트 로드 (Pretendard → NanumGothic → 기본 폰트 순으로 시도)"""
    try:
        for fname in ["Pretendard-Bold.ttf", "Pretendard-Medium.ttf", "Pretendard-Regular.ttf"]:
            path = get_file_path(fname)
            if os.path.exists(path):
                return ImageFont.truetype(path, size)

        # 나눔고딕 폴백
        nanum_path = "NanumGothic-Bold.ttf"
        if not os.path.exists(nanum_path):
            try:
                font_url = "https://github.com/google/fonts/raw/main/ofl/nanumgothic/NanumGothic-Bold.ttf"
                r = requests.get(font_url, timeout=3)
                with open(nanum_path, "wb") as f:
                    f.write(r.content)
            except Exception:
                pass
        if os.path.exists(nanum_path):
            return ImageFont.truetype(nanum_path, size)
    except Exception:
        pass
    return ImageFont.load_default()


def create_warning_poster(df: pd.DataFrame, warning_summary: dict, temp_stop_summary: dict) -> bytes:
    """
    A4(300dpi) 크기의 현황 포스터 이미지 생성 후 JPEG 바이트 반환.

    Parameters
    ----------
    df               : 전체 현장 DataFrame
    warning_summary  : {특보명: [현장명, ...]} 딕셔너리
    temp_stop_summary: {'stop_all': [...], 'stop_out': [...]} 딕셔너리
    """
    W, H = 2480, 3508
    img  = Image.new("RGB", (W, H), color="#FFFFFF")
    draw = ImageDraw.Draw(img)

    # 폰트
    font = {
        "title":      load_custom_font(130),
        "subtitle":   load_custom_font(55),
        "section":    load_custom_font(75),
        "box_title":  load_custom_font(65),
        "content":    load_custom_font(50),
        "safety_ttl": load_custom_font(70),
        "safety_cnt": load_custom_font(50),
        "footer":     load_custom_font(40),
    }

    MARGIN_X      = 100
    CONTENT_W     = W - MARGIN_X * 2
    BOX_PAD       = 60
    BOX_RADIUS    = 40
    LINE_SPACING  = 70
    HEADER_H      = 450

    # ── 헤더 ──────────────────────────────────────────────
    draw.rectangle([(0, 0), (W, HEADER_H)], fill="#005bac")

    title_text = "GS건설 현장 기상 및 작업통제 현황"
    bbox = draw.textbbox((0, 0), title_text, font=font["title"])
    draw.text(((W - (bbox[2] - bbox[0])) / 2, 140), title_text, font=font["title"], fill="white")

    time_text = get_kst_now().strftime("%Y년 %m월 %d일 %H:%M 기준")
    bbox = draw.textbbox((0, 0), time_text, font=font["subtitle"])
    draw.text(((W - (bbox[2] - bbox[0])) / 2, 320), time_text, font=font["subtitle"], fill="#dddddd")

    # ── 경고 박스 렌더 헬퍼 ───────────────────────────────
    def draw_warning_box(title: str, title_color: str, bg_color: str,
                         border_color: str, sites: list[str], start_y: int) -> int:
        if not sites:
            return start_y

        sites_str = ", ".join(sites)
        max_w     = CONTENT_W - BOX_PAD * 2
        lines, curr_line = [], ""

        for word in sites_str.split(" "):
            test = curr_line + word + " "
            if draw.textbbox((0, 0), test, font=font["content"])[2] > max_w:
                lines.append(curr_line)
                curr_line = word + " "
            else:
                curr_line = test
        if curr_line:
            lines.append(curr_line)

        box_h = BOX_PAD * 2 + 80 + len(lines) * LINE_SPACING + 20
        draw.rounded_rectangle(
            [(MARGIN_X, start_y), (W - MARGIN_X, start_y + box_h)],
            radius=BOX_RADIUS, fill=bg_color, outline=border_color, width=5,
        )

        tx, ty = MARGIN_X + BOX_PAD, start_y + BOX_PAD
        draw.text((tx, ty), title, font=font["box_title"], fill=title_color)
        ty += 100
        for line in lines:
            draw.text((tx, ty), line, font=font["content"], fill="#333333")
            ty += LINE_SPACING

        return start_y + box_h + 60

    # ── 본문 특보/작업중지 내용 ────────────────────────────
    current_y = HEADER_H + 100
    draw.text((MARGIN_X, current_y), "■ 혹한기 작업 중지 및 기상 특보 현황",
              font=font["section"], fill="#333333")
    current_y += 120

    is_empty = True

    # 전면 작업중지 (-15℃ 이하)
    sites_stop_all = temp_stop_summary.get("stop_all", [])
    if sites_stop_all:
        label = f"⛔ 전면 작업중지 (영하 15℃ 이하, {len(sites_stop_all)}개소)"
        current_y = draw_warning_box(label, "#ffffff", "#311b92", "#512da8", sites_stop_all, current_y)
        is_empty  = False

    # 옥외 작업중지 (-12℃ 이하)
    sites_stop_out = temp_stop_summary.get("stop_out", [])
    if sites_stop_out:
        label = f"🛑 옥외 작업중지 (영하 12℃ 이하, {len(sites_stop_out)}개소)"
        current_y = draw_warning_box(label, "#b71c1c", "#ffebee", "#ef9a9a", sites_stop_out, current_y)
        is_empty  = False

    # 폭염 / 기타 특보
    sites_heat, sites_others = [], []
    for w_name, sites in warning_summary.items():
        if "건조" in w_name:
            continue
        if "폭염" in w_name:
            sites_heat.extend(sites)
        else:
            sites_others.append((w_name, sites))

    if sites_heat:
        label = f"🔥 폭염 특보 ({len(sites_heat)}개소)"
        current_y = draw_warning_box(label, "#d32f2f", "#ffebee", "#ffcdd2",
                                     list(set(sites_heat)), current_y)
        is_empty = False

    for w_name, s_list in sites_others:
        color, bg, bd = "#1565c0", "#e3f2fd", "#90caf9"
        if "한파" in w_name: color, bg, bd = "#0277bd", "#e1f5fe", "#b3e5fc"
        elif "대설" in w_name: color, bg, bd = "#546e7a", "#eceff1", "#cfd8dc"
        current_y = draw_warning_box(f"⚠️ {w_name} ({len(s_list)}개소)",
                                     color, bg, bd, s_list, current_y)
        is_empty = False

    # 이슈 없음 박스
    if is_empty:
        draw.rounded_rectangle(
            [(MARGIN_X, current_y), (W - MARGIN_X, current_y + 300)],
            radius=BOX_RADIUS, fill="#f1f8e9", outline="#c8e6c9", width=5,
        )
        draw.text((MARGIN_X + 60, current_y + 110),
                  "현재 작업 통제 기준 도달 및 기상 특보가 없습니다.",
                  font=font["box_title"], fill="#33691e")
        current_y += 300

    # ── 안전 수칙 박스 ────────────────────────────────────
    BOTTOM_START = H - 1400
    if current_y < BOTTOM_START:
        current_y = BOTTOM_START

    def draw_safety_box(title: str, content: str,
                        t_col: str, bg_col: str, bd_col: str, start_y: int) -> int:
        box_h = 600
        draw.rounded_rectangle(
            [(MARGIN_X, start_y), (W - MARGIN_X, start_y + box_h)],
            radius=BOX_RADIUS, fill=bg_col, outline=bd_col, width=5,
        )
        tx, ty = MARGIN_X + BOX_PAD, start_y + BOX_PAD
        draw.text((tx, ty), title, font=font["safety_ttl"], fill=t_col)
        ty += 110
        draw.multiline_text((tx + 20, ty), content.strip(),
                            font=font["safety_cnt"], fill="#333333", spacing=35)
        return start_y + box_h + 60

    safety_content = (
        "[GS건설 혹한기 작업 중지 기준]\n"
        "• 영하 12℃ 이하: 옥외 작업 중지 (Warm-up, 휴식시간 준수)\n"
        "• 영하 15℃ 이하: 옥내/옥외 전면 작업 중지\n"
        "[한랭질환 예방 수칙]\n"
        "• 따뜻한 옷(3겹 이상), 따뜻한 물, 따뜻한 장소(휴게시설) 마련\n"
        "• 추운 시간대(새벽, 아침) 작업 축소 및 유연한 근무시간 운영"
    )
    current_y = draw_safety_box(
        "※ 혹한기 현장 안전수칙 및 작업 중지 기준 안내",
        safety_content, "#1a237e", "#e8eaf6", "#9fa8da", current_y,
    )

    # ── 푸터 ──────────────────────────────────────────────
    draw.line([(50, H - 150), (W - 50, H - 150)], fill="#cccccc", width=5)
    footer = "GS E&C 안전보건팀"
    bbox   = draw.textbbox((0, 0), footer, font=font["footer"])
    draw.text(((W - (bbox[2] - bbox[0])) / 2, H - 100), footer,
              font=font["footer"], fill="#888888")

    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=95)
    return buf.getvalue()


# ============================================================
# 사이드바
# ============================================================
with st.sidebar:
    st.header("⚙️ 설정")

    # 텔레그램 전송
    st.markdown("### 📤 알림 전송")
    if st.button("🚀 텔레그램 전송", use_container_width=True):
        if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
            st.error("텔레그램 토큰 또는 Chat ID가 설정되지 않았습니다.")
        elif st.session_state.processed_data is None:
            st.warning("먼저 데이터를 업데이트하여 분석을 완료해주세요.")
        else:
            msg = build_telegram_message(st.session_state.processed_data)
            with st.spinner("텔레그램 전송 중..."):
                success, log = send_telegram_alert(TELEGRAM_TOKEN, TELEGRAM_CHAT_ID, msg)
                if success:
                    st.success("✅ 전송 완료!")
                else:
                    st.error(f"❌ 전송 실패: {log}")

    st.divider()

    # 위치 데이터 재분석
    if st.button("🔄 데이터/위치 재분석", use_container_width=True):
        cache_path = get_file_path(CACHE_FILENAME)
        if os.path.exists(cache_path):
            os.remove(cache_path)
        st.session_state.weather_data   = None
        st.session_state.processed_data = None
        st.session_state.analysis_done  = False
        st.cache_data.clear()
        st.rerun()


# ============================================================
# 메인 화면
# ============================================================

# ── 헤더 ──────────────────────────────────────────────────
logo_path  = get_file_path(LOGO_FILENAME)
img_base64 = get_base64_of_bin_file(logo_path) if os.path.exists(logo_path) else ""

st.markdown(f"""
<div class="custom-header-box">
    <div class="header-title">GS건설 현장 기상정보 시스템</div>
    <img src="data:image/png;base64,{img_base64}" class="header-logo-img">
</div>
""", unsafe_allow_html=True)

# ── 실시간 업데이트 버튼 ───────────────────────────────────
col_btn, _ = st.columns([2, 8])
with col_btn:
    if st.button("🔄 실시간 데이터 업데이트", use_container_width=True):
        st.cache_data.clear()
        st.session_state.processed_data = None
        st.session_state.analysis_done  = False
        st.rerun()

# ── 현장 기본 데이터 로드 (최초 1회) ─────────────────────
if st.session_state.weather_data is None:
    st.session_state.weather_data = load_site_data()

df = st.session_state.weather_data
if df.empty:
    st.stop()

# ── 실시간 기상 분석 (processed_data 없을 때만 실행) ──────
if st.session_state.processed_data is None:
    full_text = get_weather_warning_text()
    temp_df   = df.copy()

    # 분석 컬럼 초기화
    temp_df["warnings"]    = None
    temp_df["temp_val"]    = None
    temp_df["temp_time"]   = None
    temp_df["status_label"] = "정상"

    total_sites = len(temp_df)
    progress_bar = st.progress(0)
    status_text  = st.empty()

    for i, row in temp_df.iterrows():
        status_text.caption(f"🌡️ 실시간 기온 분석 중... ({i + 1}/{total_sites}) - {row['현장명']}")
        progress_bar.progress((i + 1) / total_sites)

        # 기상 특보 매칭
        addr     = str(row.get("주소", ""))
        keywords = [
            t[:-1] for t in addr.replace(",", " ").split()
            if t.endswith(("시", "군")) and len(t[:-1]) >= 2
        ]
        w_list = analyze_warnings(full_text, keywords) if keywords else []
        temp_df.at[i, "warnings"] = w_list

        # 실시간 기온 조회
        current_temp, temp_time = None, None
        if pd.notna(row["lat"]):
            current_temp, temp_time = get_current_temp(row["lat"], row["lon"])
        temp_df.at[i, "temp_val"]  = current_temp
        temp_df.at[i, "temp_time"] = temp_time

        # 상태 판별
        temp_df.at[i, "status_label"] = classify_site_status(current_temp, w_list)

    status_text.empty()
    progress_bar.empty()

    st.session_state.processed_data = temp_df
    st.session_state.analysis_done  = True

# ── 분석 결과 집계 ────────────────────────────────────────
df_final      = st.session_state.processed_data
stop_all_list = df_final[df_final["status_label"] == "⛔ 전면작업중지"]["현장명"].tolist()
stop_out_list = df_final[df_final["status_label"] == "🛑 옥외작업중지"]["현장명"].tolist()
warn_only_list= df_final[df_final["status_label"] == "⚠️ 기상특보"]["현장명"].tolist()

# 특보 요약 딕셔너리 재구성 (포스터용)
warning_summary_final: dict[str, list[str]] = {}
for _, row in df_final.iterrows():
    for w in (row["warnings"] or []):
        warning_summary_final.setdefault(w, []).append(row["현장명"])

temp_stop_summary_final = {"stop_all": stop_all_list, "stop_out": stop_out_list}

# ── 요약 메트릭 카드 ─────────────────────────────────────
m1, m2, m3, m4 = st.columns(4)
with m1: render_metric_card("전체 현장",    str(len(df_final)),       color="#333",    icon="🏗️")
with m2: render_metric_card("전면작업중지", str(len(stop_all_list)),  color="#512da8", icon="⛔")
with m3: render_metric_card("옥외작업중지", str(len(stop_out_list)),  color="#d32f2f", icon="🛑")
with m4: render_metric_card("기상 특보",   str(len(warn_only_list)), color="#ff9800", icon="⚠️")

st.divider()

# ── 좌(현장 상세) / 우(지도) 레이아웃 ────────────────────
col_left, col_right = st.columns([4, 6])

with col_left:
    st.markdown("##### 🔍 현장 상세 확인")
    site_list = df_final["현장명"].tolist()
    curr_idx  = site_list.index(st.session_state.selected_site) \
                if st.session_state.selected_site in site_list else None

    selected_option = st.selectbox(
        "현장 선택", site_list, index=curr_idx,
        placeholder="현장명을 입력하세요", label_visibility="collapsed",
    )
    if selected_option != st.session_state.selected_site:
        st.session_state.selected_site = selected_option
        st.rerun()

    if st.session_state.selected_site:
        target = df_final[df_final["현장명"] == st.session_state.selected_site].iloc[0]
        ws         = target["warnings"]
        curr_temp  = target["temp_val"]
        t_time     = target["temp_time"]
        status_txt = target["status_label"]
        badge_cls  = get_status_badge_class(status_txt)

        with st.container(border=True):
            st.markdown(f"""
            <div class="site-header">
                <span class="site-title">📍 {target['현장명']}</span>
                <span class="status-badge {badge_cls}">{status_txt}</span>
            </div>
            <div class="site-addr">{target['주소']}</div>
            """, unsafe_allow_html=True)

            if curr_temp is not None:
                st.markdown(f"""
                <div><span class="temp-badge">🌡️ {curr_temp}℃</span></div>
                <div class="time-caption">기상청 {t_time} 실시간 관측 기준</div>
                """, unsafe_allow_html=True)

                if curr_temp <= TEMP_STOP_ALL:
                    st.error("⛔ [긴급] 현재 영하 15도 이하입니다. 옥내/옥외 모든 작업을 중지하십시오.")
                elif curr_temp <= TEMP_STOP_OUT:
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

    # 포스터 다운로드
    st.markdown("##### 📋 현황 포스터 다운로드")
    with st.container(height=120, border=True):
        try:
            poster_bytes = create_warning_poster(
                df_final, warning_summary_final, temp_stop_summary_final
            )
            filename = f"현장기상_작업통제현황_{get_kst_now().strftime('%Y%m%d_%H%M')}.jpg"
            st.download_button(
                "🖼️ 현황 포스터(A4) 다운로드", data=poster_bytes,
                file_name=filename, mime="image/jpeg", use_container_width=True,
            )
        except Exception as e:
            st.error(f"포스터 생성 오류: {e}")


with col_right:
    valid_coords = df_final.dropna(subset=["lat", "lon"])
    st.markdown(
        "<div class='map-disclaimer'>"
        "⚠️ 색상 구분: 보라색(-15℃↓), 빨간색(-12℃↓), 주황/적색(특보), 파란색(정상)"
        "</div>",
        unsafe_allow_html=True,
    )

    if not valid_coords.empty:
        # 선택된 현장 중심 or 기본값
        if st.session_state.selected_site:
            sel = df_final[df_final["현장명"] == st.session_state.selected_site]
            if not sel.empty:
                c_lat, c_lon, zoom = sel.iloc[0]["lat"], sel.iloc[0]["lon"], 10
            else:
                c_lat, c_lon, zoom = MAP_DEFAULT_LAT, MAP_DEFAULT_LON, MAP_DEFAULT_ZOOM
        else:
            c_lat, c_lon, zoom = MAP_DEFAULT_LAT, MAP_DEFAULT_LON, MAP_DEFAULT_ZOOM

        m = folium.Map(location=[c_lat, c_lon], zoom_start=zoom, tiles="cartodbpositron")

        for _, row in valid_coords.iterrows():
            color, icon_name = get_map_icon(row["warnings"], row["temp_val"])
            popup_msg = f"{row['현장명']}: {row['temp_val']}℃ / {row['status_label']}"
            folium.Marker(
                [row["lat"], row["lon"]],
                tooltip=popup_msg,
                icon=folium.Icon(color=color, icon=icon_name, prefix="fa"),
            ).add_to(m)

        map_data = st_folium(m, width=None, height=600)

        # 지도 마커 클릭 → 현장 선택
        if map_data and map_data.get("last_object_clicked_tooltip"):
            clicked_name = map_data["last_object_clicked_tooltip"].split(":")[0].strip()
            if clicked_name != st.session_state.selected_site:
                st.session_state.selected_site = clicked_name
                st.rerun()
