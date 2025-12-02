const API_BASE = "http://127.0.0.1:9200";

// DOM Elements
const apiStatus = document.getElementById("apiStatus");
const businessName = document.getElementById("businessName");
const mainContent = document.getElementById("mainContent");
const additionalSections = document.getElementById("additionalSections");
const templatesGrid = document.getElementById("templatesGrid");
const selectedTemplateText = document.getElementById("selectedTemplate");
const generateBtn = document.getElementById("generateBtn");
const downloadBtn = document.getElementById("downloadBtn");
const copyCodeBtn = document.getElementById("copyCodeBtn");
const refreshPreviewBtn = document.getElementById("refreshPreviewBtn");
const fullscreenBtn = document.getElementById("fullscreenBtn");
const previewPlaceholder = document.getElementById("previewPlaceholder");
const htmlPreview = document.getElementById("htmlPreview");
const loadingModal = document.getElementById("loadingModal");
const generatingMessage = document.getElementById("generatingMessage");

let currentHtml = null;
let selectedTemplate = null;
let isGenerating = false;

// Bootstrap Template Definitions
const templates = [
  {
    id: "modern-business",
    name: "Modern Business",
    description: "Clean and professional design perfect for corporate websites and startups",
    tags: ["Professional", "Corporate", "Multi-page"],
    image: "https://images.unsplash.com/photo-1460925895917-afdab827c52f?w=400&h=300&fit=crop"
  },
  {
    id: "landing-page",
    name: "Product Landing",
    description: "Conversion-focused single page with hero, features, and strong CTAs",
    tags: ["Marketing", "SaaS", "Single-page"],
    image: "https://images.unsplash.com/photo-1551650975-87deedd944c3?w=400&h=300&fit=crop"
  },
  {
    id: "portfolio",
    name: "Creative Portfolio",
    description: "Showcase your work with an elegant grid layout and project details",
    tags: ["Creative", "Gallery", "Projects"],
    image: "https://images.unsplash.com/photo-1507238691740-187a5b1d37b8?w=400&h=300&fit=crop"
  },
  {
    id: "restaurant",
    name: "Restaurant & Cafe",
    description: "Appetizing design with menu sections, hours, and reservation form",
    tags: ["Food", "Local", "Booking"],
    image: "https://images.unsplash.com/photo-1517248135467-4c7edcad34c4?w=400&h=300&fit=crop"
  },
  {
    id: "agency",
    name: "Digital Agency",
    description: "Bold and dynamic layout for agencies and service providers",
    tags: ["Services", "Team", "Case Studies"],
    image: "https://images.unsplash.com/photo-1552664730-d307ca884978?w=400&h=300&fit=crop"
  },
  {
    id: "ecommerce",
    name: "E-commerce Store",
    description: "Product showcase with categories, filters, and shopping cart",
    tags: ["Shop", "Products", "Commerce"],
    image: "https://images.unsplash.com/photo-1472851294608-062f824d29cc?w=400&h=300&fit=crop"
  },
  {
    id: "blog",
    name: "Blog & Magazine",
    description: "Content-focused layout with article grid and sidebar",
    tags: ["Content", "Articles", "News"],
    image: "https://images.unsplash.com/photo-1499750310107-5fef28a66643?w=400&h=300&fit=crop"
  },
  {
    id: "minimal",
    name: "Minimal Elegant",
    description: "Simple and sophisticated design with plenty of whitespace",
    tags: ["Minimal", "Elegant", "Simple"],
    image: "https://images.unsplash.com/photo-1618005198919-d3d4b5a92ead?w=400&h=300&fit=crop"
  },
  {
    id: "fitness",
    name: "Fitness & Gym",
    description: "Energetic design for fitness centers, trainers, and wellness",
    tags: ["Fitness", "Health", "Classes"],
    image: "https://images.unsplash.com/photo-1534438327276-14e5300c3a48?w=400&h=300&fit=crop"
  },
  {
    id: "education",
    name: "Education & Courses",
    description: "Clean layout for schools, courses, and educational content",
    tags: ["Learning", "Courses", "Academic"],
    image: "https://images.unsplash.com/photo-1523240795612-9a054b0db644?w=400&h=300&fit=crop"
  }
];

// Initialize
document.addEventListener("DOMContentLoaded", () => {
  renderTemplates();
  attachListeners();
  checkHealth();
});

function renderTemplates() {
  templatesGrid.innerHTML = "";
  
  templates.forEach((template) => {
    const card = document.createElement("div");
    card.className = "template-card";
    card.dataset.templateId = template.id;
    
    card.innerHTML = `
      <div class="template-preview">
        <img src="${template.image}" alt="${template.name}" onerror="this.parentElement.innerHTML='<i class=\\'bi bi-image template-preview-placeholder\\'></i>'">
      </div>
      <div class="template-info">
        <div class="template-name">${template.name}</div>
        <div class="template-description">${template.description}</div>
        <div class="template-tags">
          ${template.tags.map(tag => `<span class="template-tag">${tag}</span>`).join("")}
        </div>
      </div>
    `;
    
    card.addEventListener("click", () => selectTemplate(template));
    templatesGrid.appendChild(card);
  });
}

function selectTemplate(template) {
  selectedTemplate = template;
  
  // Update UI
  document.querySelectorAll(".template-card").forEach((card) => {
    card.classList.remove("selected");
  });
  
  const selectedCard = document.querySelector(`[data-template-id="${template.id}"]`);
  if (selectedCard) {
    selectedCard.classList.add("selected");
  }
  
  selectedTemplateText.innerHTML = `<strong>${template.name}</strong> template selected`;
  
  // Enable generate button if content is filled
  updateGenerateButton();
}

function attachListeners() {
  generateBtn.addEventListener("click", generateWebsite);
  downloadBtn.addEventListener("click", downloadHtml);
  copyCodeBtn.addEventListener("click", copyCode);
  refreshPreviewBtn.addEventListener("click", refreshPreview);
  fullscreenBtn.addEventListener("click", toggleFullscreen);
  
  // Update generate button state on content change
  mainContent.addEventListener("input", updateGenerateButton);
}

function updateGenerateButton() {
  const hasContent = mainContent.value.trim().length > 0;
  const hasTemplate = selectedTemplate !== null;
  generateBtn.disabled = !(hasContent && hasTemplate);
}

async function checkHealth() {
  try {
    const resp = await fetch(`${API_BASE}/health`);
    if (!resp.ok) throw new Error();
    setApiStatus("connected", "API connected");
  } catch (err) {
    setApiStatus("error", "API unavailable");
    generateBtn.disabled = true;
  }
}

function setApiStatus(state, label) {
  apiStatus.textContent = label;
  apiStatus.classList.remove("ok", "warn", "error");
  apiStatus.classList.add(state === "connected" ? "ok" : state);
}

function buildPrompt() {
  const business = businessName.value.trim();
  const content = mainContent.value.trim();
  const additional = additionalSections.value.trim();
  
  let prompt = `Create a complete, self-contained HTML website using Bootstrap 5 based on the "${selectedTemplate.name}" template style.\n\n`;
  
  if (business) {
    prompt += `Business/Project Name: ${business}\n\n`;
  }
  
  prompt += `CONTENT TO INCLUDE:\n${content}\n\n`;
  
  if (additional) {
    prompt += `ADDITIONAL SECTIONS:\n${additional}\n\n`;
  }
  
  prompt += `TEMPLATE STYLE: ${selectedTemplate.name}\n`;
  prompt += `Description: ${selectedTemplate.description}\n`;
  prompt += `Style characteristics: ${selectedTemplate.tags.join(", ")}\n\n`;
  
  prompt += `REQUIREMENTS:\n`;
  prompt += `- Use Bootstrap 5 from CDN\n`;
  prompt += `- Include all CSS inline in a <style> tag\n`;
  prompt += `- Include all JavaScript inline in a <script> tag if needed\n`;
  prompt += `- Make it a single, complete HTML file\n`;
  prompt += `- Follow the design style of the ${selectedTemplate.name} template\n`;
  prompt += `- Make it fully responsive and mobile-friendly\n`;
  prompt += `- Use the provided content naturally throughout the page\n`;
  prompt += `- Ensure good accessibility and semantic HTML\n`;
  
  return prompt;
}

async function generateWebsite() {
  if (isGenerating) return;
  
  const prompt = buildPrompt();
  
  isGenerating = true;
  generateBtn.disabled = true;
  generatingMessage.textContent = `Applying your content to ${selectedTemplate.name}...`;
  
  const modal = new bootstrap.Modal(loadingModal);
  modal.show();
  
  const startTime = Date.now();
  
  try {
    const response = await fetch(`${API_BASE}/generate`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        prompt: prompt,
        debug: false,
        mode: "html-only",
      }),
    });
    
    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || "Generation failed");
    }
    
    const result = await response.json();
    
    // Find the HTML file
    const htmlFiles = result.files.filter(f => f.endsWith('.html'));
    if (htmlFiles.length === 0) {
      throw new Error("No HTML file was generated");
    }
    
    // Load the generated HTML
    await loadGeneratedHtml(htmlFiles[0]);
    
    const elapsed = ((Date.now() - startTime) / 1000).toFixed(2);
    setApiStatus("connected", `Generated in ${elapsed}s`);
    
  } catch (error) {
    console.error("Generation error:", error);
    alert(`Error: ${error.message}`);
    setApiStatus("error", "Generation failed");
  } finally {
    isGenerating = false;
    updateGenerateButton();
    modal.hide();
  }
}

async function loadGeneratedHtml(filePath) {
  try {
    const response = await fetch(`${API_BASE}/files/${filePath}`);
    if (!response.ok) throw new Error("Failed to load generated HTML");
    
    currentHtml = await response.text();
    
    // Show preview
    previewPlaceholder.hidden = true;
    htmlPreview.hidden = false;
    htmlPreview.srcdoc = currentHtml;
    
    // Enable action buttons
    downloadBtn.disabled = false;
    copyCodeBtn.disabled = false;
    
  } catch (error) {
    console.error("Error loading HTML:", error);
    alert(`Error loading HTML: ${error.message}`);
  }
}

function downloadHtml() {
  if (!currentHtml) return;
  
  const filename = businessName.value.trim() 
    ? `${businessName.value.trim().toLowerCase().replace(/\s+/g, '-')}.html`
    : "website.html";
  
  const blob = new Blob([currentHtml], { type: "text/html" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

async function copyCode() {
  if (!currentHtml) return;
  
  try {
    await navigator.clipboard.writeText(currentHtml);
    const originalHtml = copyCodeBtn.innerHTML;
    copyCodeBtn.innerHTML = '<i class="bi bi-check2 me-1"></i> Copied!';
    copyCodeBtn.classList.add("btn-success");
    copyCodeBtn.classList.remove("btn-outline-light");
    
    setTimeout(() => {
      copyCodeBtn.innerHTML = originalHtml;
      copyCodeBtn.classList.remove("btn-success");
      copyCodeBtn.classList.add("btn-outline-light");
    }, 2000);
  } catch (err) {
    alert("Failed to copy to clipboard");
  }
}

function refreshPreview() {
  if (currentHtml) {
    htmlPreview.srcdoc = currentHtml;
  }
}

function toggleFullscreen() {
  if (htmlPreview.requestFullscreen) {
    htmlPreview.requestFullscreen();
  }
}