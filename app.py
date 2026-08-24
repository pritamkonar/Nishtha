import streamlit as st
import pandas as pd
from pypdf import PdfReader
from fpdf import FPDF
import re
import os
import requests
import io

# ---------------------------------------------------------
# 1. Font Manager (Ensures Hindi & Unicode Characters Work)
# ---------------------------------------------------------
FONT_PATH = "NotoSansDevanagari-Regular.ttf"
FONT_URL = "https://github.com/googlefonts/noto-fonts/raw/main/hinted/ttf/NotoSansDevanagari/NotoSansDevanagari-Regular.ttf"

def ensure_font():
    """Downloads Devanagari/Unicode font if not already present."""
    if not os.path.exists(FONT_PATH):
        with st.spinner("Downloading Unicode/Hindi font support..."):
            response = requests.get(FONT_URL, timeout=15)
            with open(FONT_PATH, "wb") as f:
                f.write(response.content)

# ---------------------------------------------------------
# 2. PDF Extraction Logic
# ---------------------------------------------------------
def extract_certificate_data(pdf_file):
    reader = PdfReader(pdf_file)
    extracted_records = []

    for idx, page in enumerate(reader.pages):
        text = page.extract_text() or ""
        
        # 1. Extract Duration (e.g., 'of 8 hours', 'of 15 hours')
        hours_match = re.search(r'of\s+(\d+)\s+hours?', text, re.IGNORECASE)
        hours = int(hours_match.group(1)) if hours_match else 0

        # 2. Extract Course Name
        course_name = ""
        # Search text between completion phrase and duration / offering organization
        pattern = r"successfully completed the course(?:\s+on)?\s*\n*(.*?)(?=\s*(?:of\s+\d+\s+hours|offered by|on\s+\d|\n\s*on\s*\n))"
        name_match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
        
        if name_match:
            raw_name = name_match.group(1).strip()
            # Clean up multi-line spaces/returns
            course_name = " ".join(raw_name.split())
        else:
            # Fallback if pattern doesn't match directly
            lines = [line.strip() for line in text.splitlines() if line.strip()]
            for i, line in enumerate(lines):
                if "completed the course" in line.lower() and i + 1 < len(lines):
                    course_name = lines[i + 1]
                    if course_name.lower() == "on" and i + 2 < len(lines):
                        course_name = lines[i + 2]
                    break

        if not course_name:
            course_name = f"Course #{idx + 1}"

        extracted_records.append({
            "Sl No": idx + 1,
            "Name of Courses": course_name,
            "Duration (Hours)": hours
        })

    return extracted_records

# ---------------------------------------------------------
# 3. PDF Generator (Formatted according to handwritten memo)
# ---------------------------------------------------------
class MemoPDF(FPDF):
    def __init__(self, memo_title, memo_subtext):
        super().__init__()
        self.memo_title = memo_title
        self.memo_subtext = memo_subtext
        ensure_font()
        self.add_font("NotoDevanagari", "", FONT_PATH)

    def header(self):
        # Heading
        self.set_font("NotoDevanagari", size=14)
        self.cell(0, 8, txt=self.memo_title, align="C", new_x="LMARGIN", new_y="NEXT")
        
        # Subtitle / Memo Details
        self.set_font("NotoDevanagari", size=10)
        self.multi_cell(0, 6, txt=self.memo_subtext, align="L")
        self.ln(4)

def generate_memo_pdf(df, memo_title, memo_subtext):
    pdf = MemoPDF(memo_title, memo_subtext)
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    
    # Table Column Dimensions
    col_w_sl = 18
    col_w_name = 135
    col_w_dur = 37
    
    # Table Header
    pdf.set_font("NotoDevanagari", size=11)
    pdf.cell(col_w_sl, 9, "Sl No", border=1, align="C")
    pdf.cell(col_w_name, 9, "Name of Courses", border=1, align="C")
    pdf.cell(col_w_dur, 9, "Duration of Course", border=1, align="C")
    pdf.ln()

    # Table Body
    pdf.set_font("NotoDevanagari", size=10)
    total_hours = 0

    for _, row in df.iterrows():
        sl_no = str(row["Sl No"])
        name = str(row["Name of Courses"])
        hours = int(row["Duration (Hours)"])
        total_hours += hours
        
        dur_text = f"{hours} hours" if hours > 0 else "-"
        
        # Handle long course names gracefully
        x_start = pdf.get_x()
        y_start = pdf.get_y()
        
        # Calculate height required
        pdf.set_xy(x_start + col_w_sl, y_start)
        pdf.multi_cell(col_w_name, 7, f" {name}", border=0, align="L")
        y_end = pdf.get_y()
        row_height = max(8, y_end - y_start)
        
        # Draw cells with fixed height
        pdf.set_xy(x_start, y_start)
        pdf.cell(col_w_sl, row_height, sl_no, border=1, align="C")
        
        pdf.set_xy(x_start + col_w_sl, y_start)
        pdf.multi_cell(col_w_name, 7, f" {name}", border=1, align="L")
        
        pdf.set_xy(x_start + col_w_sl + col_w_name, y_start)
        pdf.cell(col_w_dur, row_height, dur_text, border=1, align="C")
        
        pdf.set_xy(x_start, max(y_start + row_height, y_end))

    # Total Row Footer
    pdf.set_font("NotoDevanagari", size=11)
    pdf.cell(col_w_sl + col_w_name, 10, "Total = ", border="T", align="R")
    pdf.cell(col_w_dur, 10, f"{total_hours} Hours", border=1, align="C")

    return bytes(pdf.output())

# ---------------------------------------------------------
# 4. Streamlit User Interface
# ---------------------------------------------------------
st.set_page_config(page_title="Certificate Summary Generator", page_icon="📄", layout="centered")

st.title("📄 Certificate Duration Summary")
st.write("Upload your merged certificates PDF to automatically extract course names and duration.")

# Editable Header Metadata
with st.expander("⚙️ Customize Memo Details", expanded=False):
    memo_title = st.text_input(
        "Memo Title", 
        value="Nishtha Courses (Normal) FLN/ECCE/NCERT ETC"
    )
    memo_subtext = st.text_area(
        "Memo Sub-Header / Order Details", 
        value="As per order issued by SPD, PBSSM vide memo no: 91/Ped/PBSSM , dated : 19-05-2026."
    )

uploaded_file = st.file_uploader("Upload Merged PDF (e.g. ilovepdf_merged.pdf)", type=["pdf"])

if uploaded_file is not None:
    if "extracted_df" not in st.session_state or st.session_state.get("last_uploaded") != uploaded_file.name:
        with st.spinner("Analyzing certificates..."):
            data = extract_certificate_data(uploaded_file)
            st.session_state.extracted_df = pd.DataFrame(data)
            st.session_state.last_uploaded = uploaded_file.name

    st.subheader("Extracted Courses (Review & Edit)")
    st.info("💡 You can edit course names or add missing durations directly in the table below before generating the PDF.")

    edited_df = st.data_editor(
        st.session_state.extracted_df,
        num_rows="dynamic",
        use_container_width=True,
        column_config={
            "Sl No": st.column_config.NumberColumn(width="small"),
            "Name of Courses": st.column_config.TextColumn(width="large"),
            "Duration (Hours)": st.column_config.NumberColumn(width="small")
        }
    )

    total_duration = edited_df["Duration (Hours)"].sum()
    st.markdown(f"**Total Hours Calculated:** `{total_duration} Hours`")

    if st.button("🚀 Generate & Download PDF", type="primary"):
        pdf_bytes = generate_memo_pdf(edited_df, memo_title, memo_subtext)
        
        st.download_button(
            label="📥 Click here to Download PDF",
            data=pdf_bytes,
            file_name="Certificate_Duration_Summary.pdf",
            mime="application/pdf"
        )
 
