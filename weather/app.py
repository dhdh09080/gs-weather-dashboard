# [수정된 함수] A4 포스터 생성 (폭염 경보/주의보 분리 + 한파 -12/-15 분리)
def create_warning_poster_v2(full_df, warning_summary):
    # A4 Size (300dpi)
    W, H = 2480, 3508
    img = Image.new('RGB', (W, H), color='white')
    draw = ImageDraw.Draw(img)
    
    # 폰트 사이즈 설정
    font_title = load_custom_font(140)
    font_subtitle = load_custom_font(60)
    font_section = load_custom_font(70)
    font_content = load_custom_font(50)
    font_footer = load_custom_font(45)

    # 1. 헤더 (GS건설 현장 기상특보 현황)
    header_height = 400
    draw.rectangle([(0, 0), (W, header_height)], fill="#005bac")
    
    title_text = "GS건설 현장 기상특보 현황"
    bbox = draw.textbbox((0, 0), title_text, font=font_title)
    text_w = bbox[2] - bbox[0]
    draw.text(((W - text_w) / 2, 120), title_text, font=font_title, fill="white")

    current_time = datetime.datetime.now().strftime('%Y년 %m월 %d일 %H:%M 기준')
    bbox = draw.textbbox((0, 0), current_time, font=font_subtitle)
    text_w = bbox[2] - bbox[0]
    draw.text(((W - text_w) / 2, 280), current_time, font=font_subtitle, fill="#dddddd")

    # 2. 데이터 분류 및 필터링 (4개 그룹으로 분리)
    sites_heat_warning = []  # 폭염 경보
    sites_heat_advisory = [] # 폭염 주의보
    sites_cold_15 = []       # 한파 경보 (영하 15도)
    sites_cold_12 = []       # 한파 주의보 (영하 12도)
    
    filtered_sites_for_map = [] # 지도용
    
    has_heat = False
    has_cold = False

    for w_name, sites in warning_summary.items():
        # 지도용 데이터 수집 (한파 또는 폭염만)
        if "한파" in w_name or "폭염" in w_name:
            for s in sites:
                site_row = full_df[full_df['현장명'] == s]
                if not site_row.empty:
                    filtered_sites_for_map.append(site_row.iloc[0])

        # 리스트용 데이터 분류
        if "폭염경보" in w_name:
            sites_heat_warning.extend(sites)
            has_heat = True
        elif "폭염주의보" in w_name:
            sites_heat_advisory.extend(sites)
            has_heat = True
        elif "한파경보" in w_name:
            sites_cold_15.extend(sites)
            has_cold = True
        elif "한파주의보" in w_name:
            sites_cold_12.extend(sites)
            has_cold = True
            
    # 중복 제거 및 정렬
    sites_heat_warning = sorted(list(set(sites_heat_warning)))
    sites_heat_advisory = sorted(list(set(sites_heat_advisory)))
    sites_cold_15 = sorted(list(set(sites_cold_15)))
    sites_cold_12 = sorted(list(set(sites_cold_12)))

    # 지도 생성을 위한 DF
    map_df = pd.DataFrame(filtered_sites_for_map) if filtered_sites_for_map else pd.DataFrame(columns=['lat', 'lon', 'warnings', '현장명'])

    # 3. 레이아웃 2분할 (지도 / 리스트)
    body_y = header_height + 50
    half_w = W // 2
    
    # [Left] 지도 이미지
    map_img = generate_static_map_image(map_df, width=half_w - 100, height=1200)
    img.paste(map_img, (50, body_y))
    draw.rectangle([(50, body_y), (half_w - 50, body_y + 1200)], outline="#cccccc", width=3)
    
    # [Right] 특보 리스트 출력 함수
    list_x = half_w + 50
    list_y = body_y
    
    draw.text((list_x, list_y), "■ 특보 발령 현장 목록", font=font_section, fill="#333333")
    list_y += 100
    
    def draw_site_group(title, color, site_list, current_y):
        if not site_list: return current_y
        
        # 타이틀 출력
        draw.text((list_x, current_y), title, font=font_section, fill=color)
        current_y += 70
        
        # 현장명 줄바꿈 출력
        sites_str = ", ".join(site_list)
        max_width = W - list_x - 50
        words = sites_str.split(' ')
        line = ""
        
        for word in words:
            test_line = line + word + " "
            bbox = draw.textbbox((0, 0), test_line, font=font_content)
            if (bbox[2] - bbox[0]) > max_width:
                draw.text((list_x, current_y), line, font=font_content, fill="#555555")
                line = word + " "
                current_y += 60
            else:
                line = test_line
        draw.text((list_x, current_y), line, font=font_content, fill="#555555")
        return current_y + 90 # 그룹 간 간격

    # 출력 순서: 폭염경보 -> 폭염주의보 -> 한파경보(-15) -> 한파주의보(-12)
    if not (sites_heat_warning or sites_heat_advisory or sites_cold_15 or sites_cold_12):
        draw.text((list_x, list_y), "현재 한파/폭염 특보 발령 현장이 없습니다.", font=font_content, fill="#28a745")
    else:
        # 1. 폭염 경보 (Red)
        if sites_heat_warning:
            list_y = draw_site_group(f"🔥 폭염 경보 ({len(sites_heat_warning)}개소)", "#ff0000", sites_heat_warning, list_y)
            
        # 2. 폭염 주의보 (Orange)
        if sites_heat_advisory:
            list_y = draw_site_group(f"☀️ 폭염 주의보 ({len(sites_heat_advisory)}개소)", "#ff6600", sites_heat_advisory, list_y)

        # 3. 영하 15도 이하 (한파경보 - Navy)
        if sites_cold_15:
            list_y = draw_site_group(f"❄️ 영하 15도 이하 ({len(sites_cold_15)}개소)", "#000080", sites_cold_15, list_y)

        # 4. 영하 12도 이하 (한파주의보 - Blue)
        if sites_cold_12:
            list_y = draw_site_group(f"📉 영하 12도 이하 ({len(sites_cold_12)}개소)", "#1f77b4", sites_cold_12, list_y)
            
        # 공간 부족 체크
        if list_y > (body_y + 1150):
             draw.text((list_x, body_y + 1150), "... (공간 부족으로 이하 생략)", font=font_content, fill="#999999")

    # 4. 하단 안전보건 정보 (조건부 텍스트)
    info_y = body_y + 1200 + 80
    box_margin = 50
    
    # (1) 폭염 정보 (경보나 주의보 하나라도 있으면 출력)
    if has_heat:
        title = "※ 폭염 시 현장 안전수칙 및 온열질환 안내"
        # 경보가 있으면 더 진한 빨강
        color = "#ff0000" if sites_heat_warning else "#ff6600"
        draw.text((box_margin, info_y), title, font=font_section, fill=color)
        info_y += 90
        
        content = """
[폭염 5대 기본 수칙] 물, 바람·그늘, 휴식, 보냉장구, 응급조치
[온열질환 증상] 열사병(의식없음/체온40도↑), 열탈진(땀많음/구토), 열경련(근육경련)
        """
        if sites_heat_warning:
            content += "\n[추가] 폭염 경보 시 무더위 시간대(14:00~17:00) 옥외작업 중지 권고"
            
        draw.multiline_text((box_margin + 20, info_y), content.strip(), font=font_content, fill="#333333", spacing=15)
        info_y += 250 

    # (2) 한파 정보
    if has_cold:
        title = "※ 한파(혹한) 시 현장 안전수칙 및 한랭질환 안내"
        color = "#000080" if sites_cold_15 else "#1f77b4"
        draw.text((box_margin, info_y), title, font=font_section, fill=color)
        info_y += 90
        
        content = """
[한파안전 5대 기본수칙] 따뜻한 옷, 따뜻한 쉼터, 따뜻한 물, 작업시간대 조정, 119 신고
[한랭질환 증상] 저체온증(몸떨림/말어눌), 동상(피부변색/감각저하), 침수병(부종/통증)
        """
        if sites_cold_15:
             content += "\n[추가] 영하 15도 이하 시 옥외작업 시간 단축 및 휴식시간 연장 필수"
             
        draw.multiline_text((box_margin + 20, info_y), content.strip(), font=font_content, fill="#333333", spacing=15)

    # 5. 푸터
    draw.line([(50, H-150), (W-50, H-150)], fill="#dddddd", width=4)
    footer_text = "GS E&C 안전보건팀"
    bbox = draw.textbbox((0, 0), footer_text, font=font_footer)
    f_w = bbox[2] - bbox[0]
    draw.text(((W - f_w) / 2, H - 100), footer_text, font=font_footer, fill="#999999")

    img_byte_arr = io.BytesIO()
    img.save(img_byte_arr, format='JPEG', quality=95)
    return img_byte_arr.getvalue()
