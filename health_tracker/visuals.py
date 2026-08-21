from __future__ import annotations

import streamlit as st

ICONS = {
    "home": """
        <path d="M45 82 C55 62 68 62 80 78 C92 62 108 64 114 82
                 C119 99 101 116 80 132 C59 116 40 99 45 82Z"/>
        <path d="M28 101 H54 L64 86 L76 116 L89 94 L98 101 H132"/>
    """,
    "runner": """
        <circle cx="91" cy="35" r="10"/>
        <path d="M84 53 L66 76 L84 88 L103 68 L119 79"/>
        <path d="M83 55 L104 55 L119 42"/>
        <path d="M84 88 L67 119 L42 119 M84 88 L108 108 L126 108"/>
    """,
    "barbell": """
        <path d="M32 80 H128"/>
        <path d="M22 62 V98 M30 55 V105 M130 55 V105 M138 62 V98"/>
        <path d="M53 80 C58 59 69 49 80 49 C91 49 102 59 107 80"/>
    """,
    "cycling": """
        <circle cx="46" cy="108" r="25"/><circle cx="118" cy="108" r="25"/>
        <circle cx="88" cy="35" r="9"/>
        <path d="M55 108 L73 71 L96 108 H46 L67 88 H104 L118 108"/>
        <path d="M73 71 L89 55 L106 66 M89 55 L79 87"/>
    """,
    "swim": """
        <circle cx="105" cy="55" r="10"/>
        <path d="M30 83 C45 70 58 70 73 83 C88 96 101 96 130 76"/>
        <path d="M27 105 C43 93 58 93 73 105 C88 117 104 117 133 98"/>
        <path d="M72 82 L93 61 L119 79"/>
    """,
    "kettlebell": """
        <path d="M58 63 C58 36 102 36 102 63"/>
        <path d="M66 65 C46 75 42 119 59 132 C69 140 91 140 101 132 C118 119 114 75 94 65Z"/>
        <path d="M67 65 V55 C67 40 93 40 93 55 V65"/>
    """,
    "target": """
        <circle cx="76" cy="84" r="48"/><circle cx="76" cy="84" r="29"/>
        <circle cx="76" cy="84" r="9"/>
        <path d="M82 78 L128 32 M107 32 H128 V53"/>
    """,
    "stretch": """
        <circle cx="80" cy="34" r="10"/>
        <path d="M80 48 V88 M80 60 L45 76 M80 60 L117 75"/>
        <path d="M80 88 L49 125 M80 88 L111 125 M35 126 H125"/>
    """,
}


def page_watermark(icon: str, accent: str) -> None:
    paths = ICONS[icon]
    st.markdown(
        f"""
        <div class="sport-watermark" aria-hidden="true">
          <svg viewBox="0 0 160 160" role="presentation" style="color:{accent}">
            <g fill="none" stroke="currentColor" stroke-width="5"
               stroke-linecap="round" stroke-linejoin="round">{paths}</g>
          </svg>
        </div>
        """,
        unsafe_allow_html=True,
    )


def home_logo(accent: str) -> None:
    st.markdown(
        f"""
        <div class="journey-logo" aria-label="Health Journey">
          <svg viewBox="0 0 360 150" role="img">
            <circle cx="77" cy="75" r="59" fill="none" stroke="{accent}" stroke-width="6"/>
            <g fill="none" stroke="currentColor" stroke-width="5"
               stroke-linecap="round" stroke-linejoin="round">
              <path d="M37 78 H57 L66 61 L78 94 L91 70 L100 78 H119"/>
              <path d="M53 51 C61 39 70 42 77 52 C85 42 96 40 102 52"/>
              <path d="M49 108 C65 98 88 98 106 108"/>
            </g>
            <text x="158" y="66" fill="currentColor" font-size="30" font-weight="700">HEALTH</text>
            <text x="158" y="101" fill="{accent}" font-size="30" font-weight="700">JOURNEY</text>
          </svg>
        </div>
        """,
        unsafe_allow_html=True,
    )
