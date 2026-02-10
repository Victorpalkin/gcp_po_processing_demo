import streamlit as st

CUSTOM_CSS = """
<style>
/* Hide Streamlit chrome */
#MainMenu {visibility: hidden;}
footer {visibility: hidden;}
header[data-testid="stHeader"] {
    background-color: #1a73e8;
    padding: 0.5rem 1rem;
}

/* App header bar */
.app-header {
    background: linear-gradient(135deg, #1a73e8 0%, #1557b0 100%);
    color: white;
    padding: 1.2rem 1.5rem;
    border-radius: 0 0 12px 12px;
    margin: -1rem -1rem 1.5rem -1rem;
    box-shadow: 0 2px 8px rgba(0,0,0,0.15);
}
.app-header h1 {
    color: white !important;
    margin: 0;
    font-size: 1.5rem;
    font-weight: 600;
}
.app-header p {
    color: rgba(255,255,255,0.85);
    margin: 0.2rem 0 0 0;
    font-size: 0.9rem;
}

/* Card component */
.card {
    background: white;
    border: 1px solid #e0e0e0;
    border-radius: 10px;
    padding: 1.2rem;
    margin-bottom: 1rem;
    box-shadow: 0 1px 4px rgba(0,0,0,0.06);
    transition: box-shadow 0.2s ease;
}
.card:hover {
    box-shadow: 0 4px 12px rgba(0,0,0,0.1);
}
.card h3 {
    margin: 0 0 0.3rem 0;
    font-size: 1.05rem;
    color: #202124;
}
.card .card-subtitle {
    color: #5f6368;
    font-size: 0.85rem;
    margin-bottom: 0.5rem;
}

/* Status badges */
.badge {
    display: inline-block;
    padding: 0.2rem 0.7rem;
    border-radius: 12px;
    font-size: 0.78rem;
    font-weight: 600;
    letter-spacing: 0.02em;
}
.badge-active, .badge-sent {
    background-color: #e6f4ea;
    color: #1e8e3e;
}
.badge-processing {
    background-color: #e8f0fe;
    color: #1a73e8;
}
.badge-extracted, .badge-review {
    background-color: #fef7e0;
    color: #ea8600;
}
.badge-error, .badge-failed {
    background-color: #fce8e6;
    color: #d93025;
}
.badge-creating {
    background-color: #f3e8fd;
    color: #8430ce;
}

/* Confidence color coding */
.confidence-high {
    color: #1e8e3e;
    font-weight: 600;
}
.confidence-medium {
    color: #ea8600;
    font-weight: 600;
}
.confidence-low {
    color: #d93025;
    font-weight: 600;
}

/* Metric tiles */
div[data-testid="stMetric"] {
    background: white;
    border: 1px solid #e0e0e0;
    border-radius: 10px;
    padding: 1rem;
    box-shadow: 0 1px 4px rgba(0,0,0,0.06);
}
div[data-testid="stMetric"] label {
    color: #5f6368 !important;
    font-size: 0.85rem !important;
}
div[data-testid="stMetric"] div[data-testid="stMetricValue"] {
    color: #202124 !important;
    font-size: 1.8rem !important;
    font-weight: 600 !important;
}

/* Tighter spacing */
.block-container {
    padding-top: 1rem;
    padding-bottom: 1rem;
    max-width: 1100px;
}

/* Dataframe styling */
div[data-testid="stDataFrame"] {
    border-radius: 8px;
    overflow: hidden;
}

/* Button styling */
.stButton > button {
    border-radius: 8px;
    font-weight: 500;
    padding: 0.4rem 1.2rem;
    transition: all 0.2s ease;
}
.stButton > button:hover {
    box-shadow: 0 2px 8px rgba(0,0,0,0.15);
}
.stButton > button[kind="primary"] {
    background-color: #1a73e8;
    color: white;
}

/* File uploader */
div[data-testid="stFileUploader"] {
    border-radius: 10px;
}

/* Expander styling */
div[data-testid="stExpander"] {
    border: 1px solid #e0e0e0;
    border-radius: 10px;
    margin-bottom: 0.5rem;
}

/* Selectbox */
div[data-testid="stSelectbox"] > div {
    border-radius: 8px;
}

/* Divider */
hr {
    margin: 1.5rem 0;
    border-color: #e0e0e0;
}
</style>
"""


def apply_styles():
    """Inject custom CSS into the Streamlit page."""
    st.markdown(CUSTOM_CSS, unsafe_allow_html=True)


def render_header(title: str, subtitle: str = ""):
    """Render a custom app header bar."""
    subtitle_html = f"<p>{subtitle}</p>" if subtitle else ""
    st.markdown(
        f'<div class="app-header"><h1>{title}</h1>{subtitle_html}</div>',
        unsafe_allow_html=True,
    )


def status_badge(status: str) -> str:
    """Return HTML for a colored status badge."""
    status_upper = status.upper()
    css_class = {
        "ACTIVE": "badge-active",
        "ENABLED": "badge-active",
        "SENT": "badge-sent",
        "PROCESSING": "badge-processing",
        "EXTRACTED": "badge-extracted",
        "REVIEW": "badge-review",
        "REVIEWED": "badge-review",
        "ERROR": "badge-error",
        "FAILED": "badge-failed",
        "CREATING": "badge-creating",
        "DISABLED": "badge-error",
    }.get(status_upper, "badge-processing")
    return f'<span class="badge {css_class}">{status_upper}</span>'


def confidence_class(score: float) -> str:
    """Return CSS class name for a confidence score (0-1 scale)."""
    if score >= 0.9:
        return "confidence-high"
    elif score >= 0.7:
        return "confidence-medium"
    return "confidence-low"


def confidence_html(score: float) -> str:
    """Return HTML span for a confidence score."""
    pct = f"{score * 100:.0f}%"
    cls = confidence_class(score)
    return f'<span class="{cls}">{pct}</span>'
