document.addEventListener('DOMContentLoaded', () => {
    const form = document.getElementById('analyze-form');
    if (!form) return;

    const analyzeBtn = document.getElementById('analyze-btn');
    const loadingState = document.getElementById('loading-state');
    const resultsArea = document.getElementById('results-area');
    
    form.addEventListener('submit', async (e) => {
        e.preventDefault();
        
        const topic = document.getElementById('topic').value;
        const urlsRaw = document.getElementById('urls').value;
        const urls = urlsRaw.split('\n').filter(u => u.trim() !== '');
        
        if (!topic || urls.length === 0) {
            alert("Please enter a topic and at least one URL.");
            return;
        }

        // Update UI
        analyzeBtn.disabled = true;
        form.style.opacity = '0.5';
        loadingState.classList.remove('hidden');
        resultsArea.classList.add('hidden');
        
        try {
            const response = await fetch('/api/analyze', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ topic, urls })
            });
            
            const data = await response.json();
            
            if (response.ok && data.summary) {
                renderResults(topic, data.summary, data.new_papers);
            } else if (response.ok && !data.summary) {
                alert("No new papers were successfully analyzed.");
            } else {
                alert("Error: " + (data.error || "Failed to analyze."));
            }
            
        } catch (error) {
            console.error(error);
            alert("Network error occurred.");
        } finally {
            // Restore UI
            analyzeBtn.disabled = false;
            form.style.opacity = '1';
            loadingState.classList.add('hidden');
        }
    });

    function renderResults(topic, summary, newPapers) {
        document.getElementById('result-topic').textContent = topic;
        
        // Main Summary
        document.getElementById('res-summary').innerHTML = `<p>${summary.summary}</p>`;
        
        // Novel Contributions
        const novelHtml = summary.novel_contributions.map(c => 
            `<div class="finding-pill"><span class="pill-icon">&rarr;</span><div>${c}</div></div>`
        ).join('');
        document.getElementById('res-novel').innerHTML = novelHtml;
        
        // Open Questions
        const qHtml = summary.open_questions.map(q => 
            `<div class="finding-pill"><span class="pill-icon question">?</span><div>${q}</div></div>`
        ).join('');
        document.getElementById('res-questions').innerHTML = qHtml;
        
        // Comparison
        document.getElementById('res-comparison').innerHTML = `<p>${summary.conflicts_or_agreements}</p>`;
        
        // Trajectory
        document.getElementById('res-trajectory').innerHTML = `<p>${summary.field_trajectory}</p>`;
        
        // Key Insights from individual papers (combining core findings)
        let insightsHtml = '';
        newPapers.forEach(paper => {
            if (paper.insights && paper.insights.core_findings) {
                paper.insights.core_findings.forEach(finding => {
                    insightsHtml += `<div class="finding-pill"><span class="pill-icon">&rarr;</span><div>${finding} <br><small class="card-meta" style="margin-bottom:0;opacity:0.7;">— ${paper.title}</small></div></div>`;
                });
            }
        });
        document.getElementById('res-insights').innerHTML = insightsHtml;
        
        // Show results
        resultsArea.classList.remove('hidden');
        resultsArea.scrollIntoView({ behavior: 'smooth' });
        
        // Update metric counter if present
        const metricEl = document.querySelector('.metric-value');
        if (metricEl) {
            // A bit of a hack: just increment by the number of new papers for immediate visual feedback
            const current = parseInt(metricEl.textContent);
            metricEl.textContent = current + newPapers.length;
        }
    }
});
