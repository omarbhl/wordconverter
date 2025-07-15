import os
import pypandoc
import google.generativeai as genai
import streamlit as st
import tempfile
import zipfile
import io
import base64
import mimetypes

# --- 1. CONFIGURATION & STYLING (Unchanged) ---

REMARK_KEYWORDS = ["Remark:", "Note:", "Important:", "Remarque:", "N.B.:", "Attention:"]
COURSE_CSS = """
<style>
    @import url('https://fonts.googleapis.com/css2?family=Lato:wght@400;700&family=Source+Code+Pro&display=swap');
    body { font-family: 'Lato', sans-serif; line-height: 1.7; background-color: #f8f9fa; color: #343a40; margin: 0; padding: 0; }
    .course-container { max-width: 850px; margin: 40px auto; padding: 2em 3em; background-color: #ffffff; border-radius: 10px; box-shadow: 0 5px 15px rgba(0, 0, 0, 0.08); }
    h1, h2, h3 { font-weight: 700; color: #2c3e50; margin-top: 2em; margin-bottom: 0.8em; }
    h1 { font-size: 2.5em; border-bottom: 3px solid #3498db; padding-bottom: 0.3em; }
    h2 { font-size: 2em; border-bottom: 1px solid #bdc3c7; padding-bottom: 0.2em; }
    h3 { font-size: 1.5em; color: #34495e; }
    img { max-width: 100%; height: auto; display: block; margin: 30px auto; border-radius: 5px; box-shadow: 0 4px 10px rgba(0, 0, 0, 0.1); }
    .remark { background-color: #eaf7ff; border-left: 5px solid #3498db; padding: 20px; margin: 25px 0; border-radius: 5px; font-size: 0.95em; }
    .remark::before { content: '💡'; font-size: 1.5em; margin-right: 15px; float: left; line-height: 1.2; }
    .remark p { margin: 0; overflow: hidden; }
    table { width: 100%; border-collapse: collapse; margin: 25px 0; font-size: 0.9em; box-shadow: 0 2px 5px rgba(0,0,0,0.1); }
    th, td { padding: 12px 15px; border: 1px solid #dddddd; text-align: left; }
    thead tr { background-color: #2c3e50; color: #ffffff; text-align: left; font-weight: bold; }
    tbody tr { border-bottom: 1px solid #dddddd; }
    tbody tr:nth-of-type(even) { background-color: #f3f3f3; }
    tbody tr:last-of-type { border-bottom: 2px solid #2c3e50; }
</style>
"""

# --- 2. HELPER FUNCTIONS ---

def preprocess_markdown(markdown_text):
    """Finds and wraps remarks in a styled div for special processing."""
    lines = markdown_text.split('\n')
    processed_lines = [
        f'<div class="remark"><p>{line}</p></div>' if any(line.lstrip().lower().startswith(kw.lower()) for kw in REMARK_KEYWORDS) else line
        for line in lines
    ]
    return '\n'.join(processed_lines)

def convert_to_html_with_gemini(api_key, processed_markdown):
    """Sends the final markdown to Gemini for HTML conversion."""
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel('gemini-2.5-pro', generation_config={"temperature": 0})
    prompt = f"""
You are an expert HTML developer. Your task is to convert a Markdown document into a single, styled, self-contained HTML file.

**CRITICAL INSTRUCTIONS (Follow these exactly):**
1.  **Output ONLY raw HTML code.** Do not add any commentary.
2.  Use the following CSS style sheet EXACTLY as provided. Place it inside a `<style>` tag in the `<head>` section.
3.  The main content from the Markdown must be placed inside a `<main class="course-container">` element within the `<body>`.
4.  If you see Markdown tables (using pipe syntax), convert them to proper HTML `<table>`, `<thead>`, `<tbody>`, `<tr>`, `<th>`, and `<td>` elements.
5.  If you see Markdown image links like `![alt text](imgs/image1.png)`, convert them to proper HTML `<img src="imgs/image1.png" alt="alt text">` tags.
6.  **Important:** The provided Markdown may already contain some HTML `<div class="remark">` elements. You MUST preserve these `div` wrappers and their content exactly as they appear.
7.  Produce a valid HTML5 document structure and set the `<title>` to "Course Notes".

--- START OF CSS TO USE ---
{COURSE_CSS}
--- END OF CSS TO USE ---

--- START OF MARKDOWN CONTENT TO CONVERT ---
{processed_markdown}
--- END OF MARKDOWN CONTENT TO CONVERT ---
"""
    response = model.generate_content(prompt)
    return response.text.strip().removeprefix("```html").removesuffix("```")

def create_html_preview(html_content, media_dir):
    """Creates a self-contained HTML for previewing by embedding images as Base64."""
    if not os.path.isdir(media_dir):
        return html_content

    preview_html = html_content
    for filename in os.listdir(media_dir):
        filepath = os.path.join(media_dir, filename)
        mime_type, _ = mimetypes.guess_type(filepath)
        if mime_type and mime_type.startswith('image'):
            with open(filepath, "rb") as f:
                content = base64.b64encode(f.read()).decode("utf-8")
            src_path = f"imgs/{filename}"
            base64_src = f"data:{mime_type};base64,{content}"
            preview_html = preview_html.replace(src_path, base64_src, 1) # Replace only the first instance
    return preview_html

def reset_state():
    """Clears the results from the session state when a new file is uploaded."""
    for key in ['conversion_done', 'preview_html', 'zip_buffer', 'download_filename']:
        if key in st.session_state:
            del st.session_state[key]

# --- 3. STREAMLIT APPLICATION UI AND LOGIC ---

st.set_page_config(layout="wide", page_title="AI Course Page Generator")

st.title("🎓 AI Course Page Generator")
st.markdown("Transform your `.docx` course notes into a beautiful, ready-to-use webpage with a single click.")

# --- Inputs in the Sidebar ---
with st.sidebar:
    st.header("⚙️ Configuration")
    
    gemini_api_key = st.text_input("Enter your Gemini API Key", type="password", help="Your key is not stored and is used only for this session.")
    
    # Add the on_change callback to the file uploader to reset state
    uploaded_file = st.file_uploader(
        "Upload your .docx file", 
        type=["docx"],
        on_change=reset_state
    )
    
    st.markdown("---")
    convert_button = st.button("✨ Generate Webpage", type="primary", use_container_width=True)

# --- Main App Logic ---
if convert_button:
    if not gemini_api_key:
        st.warning("Please enter your Gemini API key to proceed.")
    elif not uploaded_file:
        st.warning("Please upload a .docx file.")
    else:
        # Use a temporary directory for robust file handling
        with tempfile.TemporaryDirectory() as temp_dir:
            docx_path = os.path.join(temp_dir, uploaded_file.name)
            media_path = os.path.join(temp_dir, "imgs")

            with open(docx_path, "wb") as f:
                f.write(uploaded_file.getbuffer())

            # Use st.status with more user-friendly messages and emojis
            with st.status("Generating your webpage...", expanded=True) as status:
                try:
                    status.update(label="📝 Step 1: Extracting content and images...")
                    markdown_content = pypandoc.convert_file(docx_path, 'markdown', extra_args=[f'--extract-media={media_path}'])
                    
                    status.update(label="🎨 Step 2: Highlighting special 'Remark' sections...")
                    processed_markdown = preprocess_markdown(markdown_content)
                    
                    status.update(label="🤖 Step 3: Building your HTML page with AI...")
                    final_html_with_links = convert_to_html_with_gemini(gemini_api_key, processed_markdown)

                    status.update(label="🖼️ Step 4: Preparing the live preview...")
                    preview_html = create_html_preview(final_html_with_links, media_path)

                    status.update(label="📦 Step 5: Packaging files for download...")
                    zip_buffer = io.BytesIO()
                    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zipf:
                        zipf.writestr("course.html", final_html_with_links)
                        if os.path.isdir(media_path):
                            for root, _, files in os.walk(media_path):
                                for file in files:
                                    zipf.write(os.path.join(root, file), arcname=os.path.join("imgs", file))

                    # Store results in session_state instead of displaying them directly
                    st.session_state.conversion_done = True
                    st.session_state.preview_html = preview_html
                    st.session_state.zip_buffer = zip_buffer.getvalue()
                    st.session_state.download_filename = f"{os.path.splitext(uploaded_file.name)[0]}_webpage.zip"

                    status.update(label="Conversion Complete!", state="complete", expanded=False)

                except Exception as e:
                    st.error(f"An error occurred: {e}", icon="🔥")
                    st.error("Please check your API key and ensure Pandoc is installed correctly on the system where Streamlit is running.")
                    # Clear state on failure
                    reset_state()

# --- Display Area: This block now reads from session_state ---
if st.session_state.get('conversion_done', False):
    st.header("🚀 Your Results")
    st.success("Your course page is ready! You can preview it below or download the complete package.")
    
    st.download_button(
        label="📥 Download Webpage (.zip)",
        data=st.session_state.zip_buffer,
        file_name=st.session_state.download_filename,
        mime="application/zip",
        use_container_width=True
    )
    
    st.divider()

    st.subheader("📄 Live Preview")
    st.info("Note: This is a live preview. Use the download button above to get the complete package with separate image files.", icon="ℹ️")
    st.components.v1.html(st.session_state.preview_html, height=800, scrolling=True)
else:
    # This message shows on the initial run or after a reset
    st.info("Please provide your API key and upload a file in the sidebar to get started.")