"""
BC Drive Mapper — navigation hub.

Defines the two pages and their sidebar labels via st.navigation().
All page content lives in drive_time.py and pages/2_Waitlist_Audit.py.
"""
import streamlit as st

st.set_page_config(
    page_title="BC Drive Mapper",
    page_icon="🏥",
    layout="wide",
)

pg = st.navigation([
    st.Page("drive_time.py", title="Drive Time Analysis", icon="🏥", default=True),
    st.Page("pages/2_Waitlist_Audit.py", title="Waitlist FIFO Audit", icon="🔍"),
])
pg.run()
