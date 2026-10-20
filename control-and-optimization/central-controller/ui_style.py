# ui_style.py
# ------------------------------------------------------------
# Appearance layer for Smart Lighting Controller
# ------------------------------------------------------------

import streamlit as st


# =========================
# Easy UI configuration
# =========================

APP_TITLE = "Smart Lighting Controller"
APP_SUBTITLE = "Management dashboard"

PRIMARY_COLOR = "#2563eb"
PRIMARY_DARK = "#1e3a8a"
BACKGROUND_1 = "#eef4ff"
BACKGROUND_2 = "#f8fbff"
TEXT_DARK = "#0f172a"
TEXT_MUTED = "#64748b"
CARD_BG = "rgba(255, 255, 255, 0.94)"
BORDER_COLOR = "rgba(148, 163, 184, 0.30)"


def apply_ui_style():
    st.markdown(
        f"""
        <style>
        .block-container {{
            padding-top: 3.0rem !important;
            padding-bottom: 2.5rem !important;
            max-width: 1500px;
        }}

        .stApp {{
            background:
                radial-gradient(circle at top left, rgba(37, 99, 235, 0.13), transparent 34%),
                linear-gradient(135deg, {BACKGROUND_1} 0%, {BACKGROUND_2} 45%, #ffffff 100%);
        }}

        .smart-header {{
            padding: 1.05rem 1.35rem;
            border-radius: 24px;
            background: linear-gradient(135deg, {TEXT_DARK} 0%, {PRIMARY_DARK} 50%, {PRIMARY_COLOR} 100%);
            box-shadow: 0 16px 38px rgba(15, 23, 42, 0.20);
            color: white;
            margin-bottom: 1.0rem;
        }}

        .smart-header h1 {{
            margin: 0;
            padding: 0;
            color: white;
            font-size: 1.9rem;
            line-height: 1.15;
            letter-spacing: -0.04em;
            font-weight: 850;
        }}

        .smart-header p {{
            margin: 0.35rem 0 0.75rem 0;
            color: rgba(255,255,255,0.82);
            font-size: 0.95rem;
        }}

        .mqtt-pill {{
            display: inline-flex;
            align-items: center;
            gap: 0.4rem;
            padding: 0.28rem 0.65rem;
            border-radius: 999px;
            font-size: 0.78rem;
            font-weight: 750;
            background: rgba(255, 255, 255, 0.14);
            border: 1px solid rgba(255, 255, 255, 0.22);
        }}
        
        div.stButton > button {{
            min-height: 2.8rem;
            font-size: 0.95rem;
            font-weight: 850;
        }}

        .mqtt-ok {{ color: #bbf7d0; }}
        .mqtt-bad {{ color: #fecaca; }}

        .fixed-refresh {{
            position: fixed;
            right: 24px;
            bottom: 24px;
            z-index: 999999;
            background: {PRIMARY_COLOR};
            color: white !important;
            text-decoration: none !important;
            border-radius: 999px;
            padding: 0.78rem 1.05rem;
            font-weight: 850;
            box-shadow: 0 14px 34px rgba(37, 99, 235, 0.34);
            border: 1px solid rgba(255,255,255,0.40);
        }}

        .fixed-refresh:hover {{
            background: {PRIMARY_DARK};
            color: white !important;
            transform: translateY(-1px);
        }}

        .power-watch {{
            position: fixed;
            right: 8px;
            top: 95px;
            width: 120px;
            z-index: 999998;
            background: rgba(253, 253, 255, 0.96);
            border: 1px solid rgba(37, 99, 235, 0.42);
            border-radius: 15px;
            padding: 0.95rem 0.78rem;
            box-shadow: 0 14px 34px rgba(15, 23, 42, 0.14);
            color: {TEXT_DARK};
        }}

        .power-watch-title {{
            font-size: 1.3rem;
            font-weight: 990;
            text-transform: uppercase;
            letter-spacing: 0.1em;
            color: {PRIMARY_DARK};
            margin-bottom: 0.7rem;
        }}

        .power-watch-row {{
            display: flex;
            justify-content: space-between;
            align-items: baseline;
            gap: 0.6rem;
            font-size: 0.9rem;
            line-height: 2.5;
            white-space: nowrap;
        }}

        .power-watch-row span {{
            color: {TEXT_MUTED};
            font-weight: 1000;
        }}

        .power-watch-row strong {{
            color: {TEXT_DARK};
            font-weight: 1000;
        }}

        .power-watch-divider {{
            height: 2px;
            background: rgba(37, 99, 235, 0.42);
            margin: 0.7rem 1;
        }}

        .power-watch-total strong {{
            font-size: 1.1rem;
            color: #245EDF;
        }}

        .power-watch-savings strong {{
            font-size: 1.3rem;
            color: #22B14C;
        }}

        @media (max-width: 1300px) {{
            .power-watch {{
                display: none;
            }}
        }}

        .summary-grid {{
            display: grid;
            grid-template-columns: repeat(4, minmax(0, 1fr));
            gap: 0.7rem;
            margin: 0.6rem 0 0.9rem 0;
        }}

        .calibration-table-wrap {{
            width: 100%;
            overflow-x: auto;
            border: 1px solid {BORDER_COLOR};
            border-radius: 14px;
            margin: 0.4rem 0 1.2rem 0;
            background: rgba(255, 255, 255, 0.96);
        }}

        .calibration-table-wrap table {{
            width: 100%;
            border-collapse: collapse;
            font-size: 0.94rem;
        }}

        .calibration-table-wrap th {{
            background: #f8fafc !important;
            color: #0f172a !important;
            font-size: 1.08rem !important;
            font-weight: 950 !important;
            padding: 0.72rem 0.62rem !important;
            border: 1px solid rgba(148, 163, 184, 0.28) !important;
            text-align: left !important;
        }}

        .calibration-table-wrap td {{
            padding: 0.64rem 0.62rem !important;
            border: 1px solid rgba(148, 163, 184, 0.24) !important;
            color: #0f172a !important;
        }}

        .calibration-table-wrap td:first-child {{
            font-size: 1.02rem !important;
            font-weight: 950 !important;
        }}

        .summary-card {{
            background: {CARD_BG};
            border: 1px solid {BORDER_COLOR};
            border-radius: 18px;
            padding: 0.75rem 0.9rem;
            box-shadow: 0 8px 22px rgba(15, 23, 42, 0.055);
        }}

        .summary-label {{
            color: {TEXT_MUTED};
            font-size: 0.70rem;
            font-weight: 850;
            text-transform: uppercase;
            letter-spacing: 0.06em;
        }}

        .summary-value {{
            color: {TEXT_DARK};
            font-size: 1.05rem;
            font-weight: 850;
            margin-top: 0.12rem;
        }}
        
        .smart-nav {{
            display: grid;
            grid-template-columns: repeat(4, minmax(0, 1fr));
            gap: 0;
            margin: 0.2rem 0 1.7rem 0;
            background: rgba(255, 255, 255, 0.94);
            border: 1px solid {BORDER_COLOR};
            border-radius: 18px;
            overflow: hidden;
            box-shadow: 0 8px 22px rgba(15, 23, 42, 0.055);
        }}

        .smart-nav-item {{
            display: flex;
            align-items: center;
            justify-content: center;
            min-height: 3.15rem;
            text-decoration: none !important;
            color: {TEXT_DARK} !important;
            font-size: 1.02rem;
            font-weight: 900;
            border-right: 1px solid rgba(148, 163, 184, 0.24);
            transition: all 0.15s ease-in-out;
            background: rgba(255, 255, 255, 0.88);
        }}

        .smart-nav-item:last-child {{
            border-right: none;
        }}

        .smart-nav-item:hover {{
            background: rgba(37, 99, 235, 0.08);
            color: {PRIMARY_DARK} !important;
        }}

        .smart-nav-item.active {{
            background: linear-gradient(135deg, {PRIMARY_DARK}, {PRIMARY_COLOR});
            color: white !important;
            box-shadow: inset 0 -4px 0 rgba(255, 255, 255, 0.25);
        }}

        div[data-testid="stTabs"] button {{
            border-radius: 999px;
            font-weight: 750;
            padding: 0.38rem 0.8rem;
            font-size: 0.88rem;
        }}

        div[data-testid="stTabs"] button[aria-selected="true"] {{
            background: rgba(37, 99, 235, 0.11);
            color: {PRIMARY_DARK};
        }}

        div[data-testid="stExpander"] {{
            border: 1px solid {BORDER_COLOR};
            border-radius: 18px;
            background: {CARD_BG};
            box-shadow: 0 8px 22px rgba(15, 23, 42, 0.06);
            overflow: hidden;
            margin-bottom: 0.6rem;
        }}

        div[data-testid="stExpander"] details summary {{
            font-weight: 850;
            color: {TEXT_DARK};
        }}

        div[data-testid="stExpander"] p,
        div[data-testid="stExpander"] label,
        div[data-testid="stExpander"] span {{
            font-size: 0.88rem;
        }}

        div.stButton > button {{
            border-radius: 13px;
            border: 1px solid rgba(37, 99, 235, 0.22);
            background: white;
            color: {TEXT_DARK};
            font-weight: 750;
            min-height: 2.35rem;
            box-shadow: 0 6px 14px rgba(15, 23, 42, 0.07);
            transition: all 0.15s ease-in-out;
        }}

        div.stButton > button:hover {{
            border-color: {PRIMARY_COLOR};
            color: {PRIMARY_DARK};
            transform: translateY(-1px);
            box-shadow: 0 10px 22px rgba(37, 99, 235, 0.14);
        }}

        div.stButton > button[kind="primary"],
        div.stButton button[data-testid="stBaseButton-primary"] {{
            background: linear-gradient(135deg, #ffffff 0%, #eff6ff 100%) !important;
            border: 2px solid {PRIMARY_COLOR} !important;
            color: {TEXT_DARK} !important;
            font-weight: 1000 !important;
            box-shadow: 0 10px 24px rgba(37, 99, 235, 0.18) !important;
        }}

        div.stButton > button[kind="primary"] *,
        div.stButton button[data-testid="stBaseButton-primary"] *,
        div.stButton > button[kind="primary"] p,
        div.stButton button[data-testid="stBaseButton-primary"] p {{
            color: {TEXT_DARK} !important;
            font-weight: 1000 !important;
        }}

        div.stButton > button[kind="primary"]:hover,
        div.stButton button[data-testid="stBaseButton-primary"]:hover {{
            background: linear-gradient(135deg, #eff6ff 0%, #dbeafe 100%) !important;
            color: {PRIMARY_DARK} !important;
            transform: translateY(-1px);
        }}

        div[data-testid="stSlider"] {{
            padding-top: 0.1rem;
            padding-bottom: 0.1rem;
        }}

        div[data-testid="stNumberInput"] input {{
            border-radius: 12px;
        }}

        div[data-testid="stDataFrame"] {{
            border-radius: 16px;
            overflow: hidden;
            border: 1px solid {BORDER_COLOR};
            box-shadow: 0 8px 24px rgba(15, 23, 42, 0.05);
        }}

        div[data-testid="stCodeBlock"] {{
            border-radius: 16px;
            overflow: hidden;
            box-shadow: 0 8px 22px rgba(15, 23, 42, 0.08);
        }}

        div[data-testid="stAlert"] {{
            border-radius: 16px;
            border: 1px solid rgba(148, 163, 184, 0.30);
            box-shadow: 0 8px 20px rgba(15, 23, 42, 0.045);
        }}

        .mini-info {{
            display: flex;
            flex-wrap: wrap;
            gap: 0.45rem;
            margin: 0.35rem 0 0.6rem 0;
        }}

        .mini-pill {{
            background: #f8fafc;
            border: 1px solid #e2e8f0;
            color: #334155;
            border-radius: 999px;
            padding: 0.20rem 0.55rem;
            font-size: 0.76rem;
            font-weight: 750;
        }}

        .online-pill {{
            background: #dcfce7;
            color: #166534;
            border-color: #86efac;
        }}

        .offline-pill {{
            background: #fee2e2;
            color: #991b1b;
            border-color: #fecaca;
        }}

        @media (max-width: 900px) {{
            .summary-grid {{
                grid-template-columns: repeat(2, minmax(0, 1fr));
            }}

            .smart-header h1 {{
                font-size: 1.5rem;
            }}
        }}

        @media (max-width: 600px) {{
            .summary-grid {{
                grid-template-columns: 1fr;
            }}

            .fixed-refresh {{
                right: 16px;
                bottom: 16px;
            }}
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_app_header(mqtt_connected: bool):
    if mqtt_connected:
        mqtt_status = '<span class="mqtt-pill mqtt-ok">* MQTT Connected</span>'
    else:
        mqtt_status = '<span class="mqtt-pill mqtt-bad">* MQTT Disconnected</span>'

    st.markdown(
        f"""
        <div class="smart-header">
            <h1>{APP_TITLE}</h1>
            <p>{APP_SUBTITLE}</p>
            {mqtt_status}
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_fixed_refresh():
    st.markdown(
        """
        <a class="fixed-refresh" href="./" target="_self">Refresh</a>
        """,
        unsafe_allow_html=True,
    )


def render_fixed_power_watch(power_rows, total_power: float, savings_percent: float):
    html_parts = ['<div class="power-watch">', '<div class="power-watch-title">Power</div>']

    for row in power_rows:
        html_parts.append(
            '<div class="power-watch-row">'
            f'<span>{row["label"]}</span>'
            f'<strong>{row["watts"]:.1f} W</strong>'
            '</div>'
        )

    html_parts.extend(
        [
            '<div class="power-watch-divider"></div>',
            '<div class="power-watch-row power-watch-total">'
            '<span>Total</span>'
            f'<strong>{total_power:.1f} W</strong>'
            '</div>',
            '<div class="power-watch-row power-watch-savings">'
            '<span>Savings</span>'
            f'<strong>{savings_percent:.0f}%</strong>'
            '</div>',
            '</div>',
        ]
    )

    st.markdown("".join(html_parts), unsafe_allow_html=True)


def render_dashboard_summary(panel_count: int, sensor_count: int, mqtt_connected: bool, mode_text: str = "Manual"):
    mqtt_text = "Connected" if mqtt_connected else "Disconnected"

    st.markdown(
        f"""
        <div class="summary-grid">
            <div class="summary-card">
                <div class="summary-label">Panels</div>
                <div class="summary-value">{panel_count}</div>
            </div>
            <div class="summary-card">
                <div class="summary-label">Sensors</div>
                <div class="summary-value">{sensor_count}</div>
            </div>
            <div class="summary-card">
                <div class="summary-label">MQTT</div>
                <div class="summary-value">{mqtt_text}</div>
            </div>
            <div class="summary-card">
                <div class="summary-label">Mode</div>
                <div class="summary-value">{mode_text}</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_navigation(active_page: str):
    pages = ["Control", "Calibration", "Occupancy", "Auto Control"]

    html = '<div class="smart-nav">'

    for page in pages:
        active_class = "active" if page == active_page else ""
        html += (
            f'<a class="smart-nav-item {active_class}" '
            f'href="?page={page.replace(" ", "%20")}" '
            f'target="_self">{page}</a>'
        )

    html += "</div>"

    st.markdown(html, unsafe_allow_html=True)
    
    
def device_info_row(online: bool, items: list[str]):
    status_class = "online-pill" if online else "offline-pill"
    status_text = "Online" if online else "Offline"

    html = f'<div class="mini-info"><span class="mini-pill {status_class}">* {status_text}</span>'

    for item in items:
        html += f'<span class="mini-pill">{item}</span>'

    html += "</div>"

    st.markdown(html, unsafe_allow_html=True)


# =========================
# Calibration UI helpers
# =========================

def calibration_start_controls(is_running: bool = False, is_stopping: bool = False):
    st.markdown(
        """
        <div class="summary-card" style="margin-top:0.4rem; margin-bottom:1rem;">
            <div class="summary-label">Calibration</div>
            <div class="summary-value" style="font-size:1.15rem;">Ready to calibrate panels and sensors</div>
            <div style="color:#64748b; font-size:0.88rem; margin-top:0.35rem;">
                The system first measures uncontrolled daylight, then turns on each panel one by one and builds the gain matrix.
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    strict_mode = False
    col1, col2 = st.columns([1, 1])

    with col1:
        start_clicked = st.button(
            "Start Calibration",
            width="stretch",
            disabled=is_running or is_stopping,
        )

    with col2:
        stop_clicked = st.button(
            "Stop Calibration",
            width="stretch",
            disabled=not is_running or is_stopping,
        )

    return strict_mode, start_clicked, stop_clicked


def calibration_status_card(status: str, message: str, elapsed_seconds: float | None = None):
    colors = {
        "ready": ("#e0f2fe", "#075985", "Ready"),
        "running": ("#fef3c7", "#92400e", "Running"),
        "success": ("#dcfce7", "#166534", "Successful"),
        "partial": ("#fef3c7", "#92400e", "Partial"),
        "error": ("#fee2e2", "#991b1b", "Error"),
    }

    bg, color, label = colors.get(status, colors["ready"])

    time_html = ""

    if elapsed_seconds is not None:
        time_html = (
            f'<div style="font-size:0.88rem; color:#64748b; margin-top:0.35rem;">'
            f'Duration: {elapsed_seconds:.1f} seconds</div>'
        )

    st.markdown(
        f"""
        <div style="
            background:{bg};
            color:{color};
            border:1px solid rgba(148,163,184,0.35);
            border-radius:22px;
            padding:1rem 1.2rem;
            margin:0.8rem 0 1rem 0;
            box-shadow:0 10px 24px rgba(15,23,42,0.07);
        ">
            <div style="font-size:0.76rem; font-weight:850; text-transform:uppercase; letter-spacing:0.06em;">Status: {label}</div>
            <div style="font-size:1.25rem; font-weight:900; margin-top:0.2rem;">{message}</div>
            {time_html}
        </div>
        """,
        unsafe_allow_html=True,
    )


def calibration_step_list(steps: list[str]):
    with st.container(border=True):
        st.markdown("#### Calibration progress")

        if not steps:
            st.info("Waiting for the first calibration step...")
            return

        for step in steps[-12:]:
            st.success(f"Done: {step}")
def calibration_result_grid(done_time: str, duration_seconds: float, panel_count: int, sensor_count: int):
    st.markdown(
        f"""
        <div class="summary-grid">
            <div class="summary-card">
                <div class="summary-label">Completed at</div>
                <div class="summary-value">{done_time}</div>
            </div>
            <div class="summary-card">
                <div class="summary-label">Duration</div>
                <div class="summary-value">{duration_seconds:.1f}s</div>
            </div>
            <div class="summary-card">
                <div class="summary-label">Panels calibrated</div>
                <div class="summary-value">{panel_count}</div>
            </div>
            <div class="summary-card">
                <div class="summary-label">Sensors used</div>
                <div class="summary-value">{sensor_count}</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


# =========================
# Gain matrix color styling
# =========================

GAIN_YELLOW_SCALE = [
    "#facc15",
    "#fde047",
    "#fef08a",
    "#fef3c7",
    "#fef9c3",
    "#fff7d6",
    "#fffbe6",
    "#fffdf2",
    "#ffffff",
]


def style_gain_matrix_by_sensor(df, panel_columns: list[str]):
    def style_row(row):
        styles = []

        values = []

        for col in panel_columns:
            try:
                values.append((col, float(row[col])))
            except Exception:
                values.append((col, None))

        valid_values = [(col, val) for col, val in values if val is not None]

        ranked_cols = [
            col
            for col, val in sorted(
                valid_values,
                key=lambda item: item[1],
                reverse=True,
            )
        ]

        rank_map = {
            col: rank
            for rank, col in enumerate(ranked_cols)
        }

        for col in row.index:
            if col not in panel_columns:
                styles.append("")
                continue

            rank = rank_map.get(col)

            if rank is None:
                styles.append("")
                continue

            color_index = min(rank, len(GAIN_YELLOW_SCALE) - 1)
            bg = GAIN_YELLOW_SCALE[color_index]

            styles.append(
                f"background-color: {bg}; color: #0f172a; font-weight: 800;"
            )

        return styles

    return (
        df.style
        .apply(style_row, axis=1)
        .set_properties(
            subset=["Sensor"],
            **{
                "font-weight": "900",
                "font-size": "1.02rem",
                "color": "#0f172a",
            },
        )
        .set_table_styles(
            [
                {
                    "selector": "th",
                    "props": [
                        ("font-weight", "950 !important"),
                        ("font-size", "1.08rem !important"),
                        ("color", "#0f172a"),
                    ],
                },
                {
                    "selector": "thead th",
                    "props": [
                        ("font-weight", "950 !important"),
                        ("font-size", "1.08rem !important"),
                        ("color", "#0f172a"),
                    ],
                },
                {
                    "selector": "tbody th",
                    "props": [
                        ("font-weight", "950 !important"),
                        ("font-size", "1.08rem !important"),
                        ("color", "#0f172a"),
                    ],
                }
            ]
        )
    )


# =========================
# Calibration warning / fallback UI
# =========================

def calibration_problem_card(title: str, problems: list[str], fallback_used: bool = False):
    if fallback_used:
        bg = "#fef3c7"
        color = "#92400e"
        border = "#f59e0b"
        status = "Warning - History Used"
    else:
        bg = "#fee2e2"
        color = "#991b1b"
        border = "#ef4444"
        status = "Calibration Problem"

    items_html = ""

    for problem in problems:
        items_html += f'<li style="margin:0.28rem 0;">{problem}</li>'

    st.markdown(
        f"""
        <div style="
            background:{bg};
            color:{color};
            border:2px solid {border};
            border-radius:22px;
            padding:1rem 1.25rem;
            margin:0.8rem 0 1rem 0;
            box-shadow:0 14px 30px rgba(15,23,42,0.10);
        ">
            <div style="font-size:0.76rem; font-weight:900; text-transform:uppercase; letter-spacing:0.07em;">
                {status}
            </div>
            <div style="font-size:1.22rem; font-weight:950; margin-top:0.25rem;">
                {title}
            </div>
            <ul style="margin:0.6rem 0 0 1.1rem; padding:0; font-size:0.93rem; line-height:1.45;">
                {items_html}
            </ul>
        </div>
        """,
        unsafe_allow_html=True,
    )


def calibration_history_card(history_path: str, loaded: bool, message: str):
    if loaded:
        bg = "#dcfce7"
        color = "#166534"
        status = "Available"
    else:
        bg = "#fee2e2"
        color = "#991b1b"
        status = "Not available"

    st.markdown(
        f"""
        <div style="
            background:{bg};
            color:{color};
            border:1px solid rgba(148,163,184,0.35);
            border-radius:18px;
            padding:0.75rem 0.95rem;
            margin:0.45rem 0 0.85rem 0;
        ">
            <div style="font-size:0.72rem; font-weight:900; text-transform:uppercase; letter-spacing:0.06em;">
                Previous calibration: {status}
            </div>
            <div style="font-size:0.88rem; margin-top:0.25rem;">
                {message}
            </div>
            <div style="font-size:0.75rem; margin-top:0.25rem; opacity:0.80;">
                {history_path}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


# =========================
# Ambient / daylight table styling
# =========================

def style_ambient_lux_by_value(df, lux_column: str = "Uncontrolled Lux"):
    try:
        values = df[lux_column].astype(float).tolist()
    except Exception:
        return df.style

    sorted_values = sorted(values, reverse=True)

    rank_map = {}

    for value in sorted_values:
        if value not in rank_map:
            rank_map[value] = len(rank_map)

    def apply_style(row):
        styles = []

        for col in row.index:
            if col != lux_column:
                styles.append("")
                continue

            try:
                value = float(row[col])
                rank = rank_map.get(value, 0)
                color_index = min(rank, len(GAIN_YELLOW_SCALE) - 1)
                bg = GAIN_YELLOW_SCALE[color_index]

                styles.append(
                    f"background-color: {bg}; color: #0f172a; font-weight: 900;"
                )
            except Exception:
                styles.append("")

        return styles

    return (
        df.style
        .apply(apply_style, axis=1)
        .set_properties(
            subset=["Sensor"],
            **{
                "font-weight": "900",
                "font-size": "1.02rem",
                "color": "#0f172a",
            },
        )
        .set_table_styles(
            [
                {
                    "selector": "th",
                    "props": [
                        ("font-weight", "950 !important"),
                        ("font-size", "1.08rem !important"),
                        ("color", "#0f172a"),
                    ],
                },
                {
                    "selector": "thead th",
                    "props": [
                        ("font-weight", "950 !important"),
                        ("font-size", "1.08rem !important"),
                        ("color", "#0f172a"),
                    ],
                },
                {
                    "selector": "tbody th",
                    "props": [
                        ("font-weight", "950 !important"),
                        ("font-size", "1.08rem !important"),
                        ("color", "#0f172a"),
                    ],
                }
            ]
        )
    )


# =========================
# Auto-control UI helpers
# =========================

def target_lux_card(
    sensor_label: str,
    sensor_id: str,
    default_lux: int = 500,
    max_lux: int = 2000,
):
    target_key = f"target_lux_{sensor_id}"

    if target_key not in st.session_state:
        st.session_state[target_key] = int(default_lux)

    current_value = int(st.session_state[target_key])

    with st.container(border=True):
        st.markdown(f"**{sensor_label}**")
        st.metric("Target illuminance", f"{current_value} lx")

        value = st.slider(
            "Target Lux",
            min_value=0,
            max_value=max_lux,
            value=current_value,
            step=10,
            key=f"{target_key}_slider",
            label_visibility="collapsed",
        )

    st.session_state[target_key] = int(value)

    return int(value)


def auto_mode_panel(auto_enabled: bool):
    if auto_enabled:
        bg = "#dcfce7"
        color = "#166534"
        title = "Auto Mode is ON"
        subtitle = "The optimizer will periodically read sensors, solve duties, and update panels."
    else:
        bg = "#e0f2fe"
        color = "#075985"
        title = "Manual Mode"
        subtitle = "Automatic control is stopped. You can still run one control cycle manually."

    st.markdown(
        f"""
        <div style="
            background:{bg};
            color:{color};
            border:1px solid rgba(148,163,184,0.35);
            border-radius:22px;
            padding:1rem 1.2rem;
            margin:0.3rem 0 1rem 0;
            box-shadow:0 10px 24px rgba(15,23,42,0.07);
        ">
            <div style="font-size:1.22rem; font-weight:950;">{title}</div>
            <div style="font-size:0.9rem; margin-top:0.25rem;">{subtitle}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
