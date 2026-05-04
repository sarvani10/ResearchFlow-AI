import os
from flask import Flask, render_template, request, jsonify

# Load environment
from dotenv import load_dotenv
load_dotenv()

from modules.crawler import WebCrawler
from modules.extractor import InsightExtractor
from modules.memento import MementoDB
from modules.synthesizer import KnowledgeSynthesizer
import google.generativeai as genai

app = Flask(__name__)

# Initialize singletons (for simplicity in this example)
# In production, you might want to handle this differently.
crawler = WebCrawler()
extractor = InsightExtractor()
memento = MementoDB()
synthesizer = KnowledgeSynthesizer()

# Initialize Gemini AI for chatbot using same model selection as extractor
gemini_api_key = os.getenv("GEMINI_API_KEY")
if gemini_api_key:
    genai.configure(api_key=gemini_api_key)
    
    # Use the same model selection logic as the extractor
    GEMINI_MODEL_CANDIDATES = [
        "gemini-2.5-flash-lite",
        "gemini-2.5-flash", 
        "gemini-2.0-flash",
        "gemini-2.0-flash-lite",
        "gemini-1.5-flash",
        "gemini-1.5-flash-latest",
        "gemini-1.5-pro",
        "gemini-1.0-pro",
        "gemini-pro",
    ]
    
    def find_working_gemini_model() -> str:
        """Find an available model from genai.list_models() without pinging to avoid masking quota errors."""
        try:
            available_models = [m.name.replace("models/", "") for m in genai.list_models()]
            target_priorities = [
                "gemini-2.5-flash-lite",
                "gemini-2.5-flash",
                "gemini-2.0-flash",
                "gemini-1.5-flash",
                "gemini-flash-latest"
            ]
            for target in target_priorities:
                if target in available_models:
                    return target
        except Exception:
            pass
        return "gemini-2.5-flash-lite"
    
    model_name = find_working_gemini_model()
    chat_model = genai.GenerativeModel(model_name)
    print(f"Chatbot using model: {model_name}")
else:
    chat_model = None
    print("Warning: GEMINI_API_KEY not found. Chatbot functionality will be disabled.")

@app.context_processor
def inject_memento_count():
    # Makes memento_count available to all templates
    return dict(memento_count=memento.count())

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/memento')
def memento_view():
    papers = memento.get_all_papers()
    return render_template('memento.html', papers=papers)

@app.route('/paper/<paper_id>')
def view_paper(paper_id):
    paper = memento.get_paper_by_id(paper_id)
    if not paper:
        return "Paper not found", 404
    return render_template('paper.html', paper=paper)

@app.route('/chat')
def chat_page():
    return render_template('chat.html')

@app.route('/summaries')
def summaries_view():
    summaries = memento.get_all_summaries()
    return render_template('summaries.html', summaries=summaries)

@app.route('/summary/<summary_id>')
def view_summary(summary_id):
    summary = memento.get_summary_by_id(summary_id)
    if not summary:
        return "Summary not found", 404
    return render_template('summary_detail.html', summary=summary)

@app.route('/api/chat', methods=['POST'])
def chat():
    if not chat_model:
        return jsonify({"error": "Chatbot not available - GEMINI_API_KEY not configured"}), 503
    
    data = request.json
    user_message = data.get('message', '').strip()
    
    if not user_message:
        return jsonify({"error": "Message is required"}), 400
    
    try:
        # Get relevant context from Memento database based on the user's query
        context = memento.retrieve_context_for_topic(user_message, n_results=3)
        
        # Create a system prompt that includes context about the research papers
        system_prompt = f"""You are ResearchFlow AI Assistant, a helpful AI assistant for academic research. 
You have access to a database of research papers through the Memento system.

Current context from the research database:
{context}

Please provide helpful, accurate responses related to academic research, paper analysis, and the specific papers in the database. 
If the user asks about specific papers or topics covered in the database, reference that information.
Be concise but thorough in your responses."""

        # Generate response using Gemini
        full_prompt = f"{system_prompt}\n\nUser: {user_message}\n\nAssistant:"
        response = chat_model.generate_content(full_prompt)
        
        return jsonify({
            "success": True,
            "response": response.text,
            "context_used": bool(context and context != "No prior knowledge exists in the Memento database yet.")
        })
        
    except Exception as e:
        return jsonify({"error": f"An error occurred: {str(e)}"}), 500

@app.route('/api/analyze', methods=['POST'])
def analyze():
    data = request.json
    topic = data.get('topic')
    urls = data.get('urls', [])

    if not topic or not urls:
        return jsonify({"error": "Topic and URLs are required"}), 400

    new_papers = []
    
    for url in urls:
        url = url.strip()
        if not url:
            continue
            
        if memento.paper_exists(url):
            # Skip if already analyzed, or fetch it if needed for synthesis
            continue
            
        # 1. Scrape
        markdown_content = crawler.scrape_article(url)
        
        # 2. Extract
        paper = extractor.extract_paper_details(url, markdown_content)
        
        # 3. Store
        if not paper.title.startswith("[ERROR]"):
            memento.save_paper(paper)
            new_papers.append(paper)

    # 4. Context Retrieval & Synthesis
    if new_papers:
        past_context = memento.retrieve_context_for_topic(topic)
        evolving_summary = synthesizer.generate_evolving_summary(
            topic, past_context, new_papers
        )
        
        # Save it to the database automatically
        memento.save_summary(topic, evolving_summary, len(new_papers))
        
        # Convert to dictionary for JSON response
        summary_dict = {
            "summary": evolving_summary.summary,
            "novel_contributions": evolving_summary.novel_contributions,
            "conflicts_or_agreements": evolving_summary.conflicts_or_agreements,
            "open_questions": evolving_summary.open_questions,
            "field_trajectory": evolving_summary.field_trajectory,
        }
    else:
        summary_dict = None

    # Return results
    return jsonify({
        "success": True,
        "new_papers": [p.dict() for p in new_papers],
        "summary": summary_dict
    })

if __name__ == '__main__':
    app.run(debug=True, port=5000)
