#============Code Setup====================
#!pip install streamlit fpdf transformers diffusers accelerate safetensors pyngrok

#!pip install streamlit -q

#!wget -q -O - ipv4.icanhazip.com

'''create a file name as app.py and save the following code and run the below like '''
#! streamlit run app.py & npx localtunnel --port 8501

'''write the ip address in the page to redirect to streamlit'''
#=========================================================================

import streamlit as st
import requests
import json
import re
import os
from PIL import Image
from io import BytesIO
from fpdf import FPDF
import torch
from transformers import pipeline
from diffusers import AutoPipelineForText2Image

# Set up directories
os.makedirs("story_images", exist_ok=True)

# ========== CONFIGURATION ==========
API_KEY = "YOUR_API_KEY"  # Replace with your actual API key
MODEL = "anthropic/claude-3-haiku"
IMG_MODEL = "stabilityai/sdxl-turbo"

# ========== HELPER FUNCTIONS ==========
@st.cache_data
def generate_story(user_prompt):
    response = requests.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {API_KEY}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://colab.research.google.com",
        },
        data=json.dumps({
            "model": MODEL,
            "messages": [{
                "role": "user",
                "content": f"Write a beautiful story based on this prompt:\n\n'{user_prompt}'\n\nInclude line breaks between paragraphs."
            }],
            "max_tokens": 1000
        })
    )
    return response.json()["choices"][0]["message"]["content"].strip()

@st.cache_data
def summarize_story(story):
    summarizer = pipeline("summarization", model="facebook/bart-large-cnn")
    paras = [p.strip() for p in story.split("\n\n") if p.strip()]
    combined_paras = [" ".join(paras[i:i+2]) for i in range(0, len(paras), 2)]
    
    prompts = []
    for para in combined_paras:
        input_length = len(para.split())
        summary = summarizer(para, max_length=100, min_length=30, do_sample=False)
        prompts.append(re.split(r'(?<=[.!?]) +', summary[0]['summary_text'])[0])
    return prompts, combined_paras

@st.cache_resource
def load_image_pipeline():
    return AutoPipelineForText2Image.from_pretrained(
        IMG_MODEL,
        torch_dtype=torch.float16,
        variant="fp16",
        use_safetensors=True
    ).to("cuda" if torch.cuda.is_available() else "cpu")

@st.cache_data
def generate_images(prompts):
    pipe = load_image_pipeline()
    image_paths = []
    for i, prompt in enumerate(prompts):
        image = pipe(prompt, guidance_scale=0.0, num_inference_steps=4).images[0]
        path = f"story_images/page_{i+1}.png"
        image.save(path)
        image_paths.append(path)
    return image_paths

# ========== PDF GENERATION ==========
class StoryPDF(FPDF):
    def __init__(self):
        super().__init__()
        self.set_auto_page_break(auto=True, margin=15)
        self.set_font("Helvetica", size=12)
    
    def header(self):
        if self.page == 1:
            self.set_font("Helvetica", 'B', 24)
            self.cell(0, 20, txt=st.session_state.title, ln=1, align='C')
            self.ln(20)

    def add_content_page(self, text, image_path):
        self.add_page()
        # Add story text
        self.set_font("Helvetica", size=14)
        self.multi_cell(0, 8, text)
        self.ln(10)
        
        # Add image
        if image_path and os.path.exists(image_path):
            try:
                img = Image.open(image_path)
                width = self.w - 30
                aspect = img.height / img.width
                self.image(image_path, x=15, y=self.get_y(), w=width, h=width*aspect)
            except Exception as e:
                self.cell(0, 10, f"Image Error: {str(e)}")

def create_pdf(story_chunks, image_paths):
    pdf = StoryPDF()
    pdf.set_title(st.session_state.title)
    pdf.add_page()  # Title page
    
    for i, (text, img_path) in enumerate(zip(story_chunks, image_paths)):
        pdf.add_content_page(text, img_path)
    
    # Return PDF as bytes directly
    return pdf.output(dest='S').encode('latin-1')

# ========== STREAMLIT UI ==========
st.set_page_config(page_title="📖 AI Storybook Generator", layout="wide")
st.title("📖 AI Storybook Generator")

user_input = st.text_input("Enter your story theme or prompt:")
st.session_state.title = user_input.strip() or "AI Generated Storybook"

if st.button("Generate Storybook"):
    if not user_input.strip():
        st.warning("Please enter a story prompt")
        st.stop()
    
    with st.spinner("📖 Writing your story..."):
        story = generate_story(user_input)
    
    with st.spinner("🔍 Preparing content..."):
        prompts, story_chunks = summarize_story(story)
    
    with st.spinner("🎨 Generating illustrations..."):
        image_paths = generate_images(prompts)
    
    # Display story content
    st.subheader("Your Generated Storybook")
    for i, (text, img_path) in enumerate(zip(story_chunks, image_paths)):
        col1, col2 = st.columns(2)
        with col1:
            st.markdown(f"<div style='font-size:16px; text-align:justify'>{text}</div>", 
                       unsafe_allow_html=True)
        with col2:
            st.image(img_path, use_column_width=True)
        st.markdown("---")
    
    # Generate and download PDF
    with st.spinner("📄 Creating PDF..."):
        pdf_bytes = create_pdf(story_chunks, image_paths)
    
    st.download_button(
        label="⬇️ Download Storybook PDF",
        data=pdf_bytes,
        file_name=f"{st.session_state.title.replace(' ', '_')}.pdf",
        mime="application/pdf"
    )
