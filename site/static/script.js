const API_BASE = 'http://127.0.0.1:8000';

// DOM Elements
const chatInput = document.getElementById('chatInput');
const sendBtn = document.getElementById('sendBtn');
const chatMessages = document.getElementById('chatMessages');
const fileList = document.getElementById('fileList');
const previewFrame = document.getElementById('previewFrame');
const previewUrl = document.getElementById('previewUrl');
const refreshPreviewBtn = document.getElementById('refreshPreviewBtn');
const fullscreenBtn = document.getElementById('fullscreenBtn');
const debugMode = document.getElementById('debugMode');
const loadingModal = document.getElementById('loadingModal');
const generatingMessage = document.getElementById('generatingMessage');
const generationTime = document.getElementById('generationTime');
const statusText = document.querySelector('.status-text');

let currentGeneratedFiles = [];
let isGenerating = false;
let startTime = null;

// Initialize
document.addEventListener('DOMContentLoaded', () => {
  chatInput.disabled = false;
  sendBtn.disabled = false;
  checkHealth();
});

// Event Listeners
sendBtn.addEventListener('click', () => {
  if (chatInput.value.trim()) {
    sendMessage();
  }
});

chatInput.addEventListener('keypress', (e) => {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    if (chatInput.value.trim()) {
      sendMessage();
    }
  }
});

refreshPreviewBtn.addEventListener('click', () => {
  previewFrame.src = previewFrame.src;
});

fullscreenBtn.addEventListener('click', () => {
  if (previewFrame.requestFullscreen) {
    previewFrame.requestFullscreen();
  }
});

// Check API Health
async function checkHealth() {
  try {
    const response = await fetch(`${API_BASE}/health`);
    if (!response.ok) throw new Error('Health check failed');
    addSystemMessage('Connected to API server');
    statusText.textContent = 'Connected';
  } catch (error) {
    addSystemMessage('Error: Cannot connect to API server. Make sure it is running on port 8000.');
    statusText.textContent = 'Disconnected';
    chatInput.disabled = true;
    sendBtn.disabled = true;
  }
}

// Send Message and Generate Website
async function sendMessage() {
  const prompt = chatInput.value.trim();
  if (!prompt || isGenerating) return;

  // Add user message to chat
  addUserMessage(prompt);
  chatInput.value = '';

  // Generate website
  await generateWebsite(prompt);
}

// Generate Website via API
async function generateWebsite(prompt) {
  if (isGenerating) return;

  isGenerating = true;
  startTime = Date.now();
  chatInput.disabled = true;
  sendBtn.disabled = true;
  statusText.textContent = 'Generating...';

  // Show loading modal
  const modal = new bootstrap.Modal(loadingModal);
  modal.show();

  try {
    generatingMessage.textContent = 'Sending request to AI...';

    const response = await fetch(`${API_BASE}/generate`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        prompt: prompt,
        debug: debugMode.checked,
      }),
    });

    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || 'Generation failed');
    }

    const result = await response.json();

    // Add agent response to chat
    addSystemMessage(result.message);

    // Update generation time
    const elapsed = ((Date.now() - startTime) / 1000).toFixed(2);
    generationTime.textContent = `Generated in ${elapsed}s`;

    // Load files
    await loadFiles(result.files);

    // Load preview
    if (result.files.length > 0) {
      const htmlFiles = result.files.filter(f => f.endsWith('.html'));
      if (htmlFiles.length > 0) {
        loadPreview(htmlFiles[0]);
      }
    }

    statusText.textContent = 'Ready';
    addSystemMessage(`✅ Website generated successfully with ${result.files.length} files!`);
  } catch (error) {
    console.error('Generation error:', error);
    statusText.textContent = 'Error';
    addSystemMessage(`❌ Error: ${error.message}`);
  } finally {
    isGenerating = false;
    chatInput.disabled = false;
    sendBtn.disabled = false;
    modal.hide();
  }
}

// Load Files from API
async function loadFiles(files) {
  currentGeneratedFiles = files;

  if (files.length === 0) {
    fileList.innerHTML =
      '<div class="text-muted text-center py-5"><p class="small">No files generated</p></div>';
    return;
  }

  // Organize files by directory
  const fileTree = {};
  files.forEach((file) => {
    const parts = file.split('/');
    let current = fileTree;
    for (let i = 0; i < parts.length - 1; i++) {
      if (!current[parts[i]]) {
        current[parts[i]] = {};
      }
      current = current[parts[i]];
    }
    current[parts[parts.length - 1]] = null;
  });

  fileList.innerHTML = '';
  renderFileTree(fileTree, fileList, '');
}

// Render File Tree
function renderFileTree(tree, container, prefix) {
  Object.keys(tree).sort().forEach((key) => {
    const isDirectory = tree[key] !== null && typeof tree[key] === 'object';
    const fullPath = prefix ? `${prefix}/${key}` : key;

    if (isDirectory) {
      const folder = document.createElement('div');
      folder.className = 'file-item-folder';

      const header = document.createElement('div');
      header.className = 'file-item';
      header.innerHTML = `
        <i class="bi bi-folder"></i>
        <span class="file-item-name">${key}</span>
      `;

      const children = document.createElement('div');
      children.style.paddingLeft = '16px';
      children.className = 'file-children';

      folder.appendChild(header);
      folder.appendChild(children);
      container.appendChild(folder);

      renderFileTree(tree[key], children, fullPath);
    } else {
      const file = document.createElement('div');
      file.className = 'file-item';
      file.style.cursor = 'pointer';

      const ext = key.split('.').pop().toLowerCase();
      let icon = 'bi-file';
      if (['html', 'htm'].includes(ext)) icon = 'bi-file-earmark-code';
      else if (['css'].includes(ext)) icon = 'bi-file-earmark-css';
      else if (['js'].includes(ext)) icon = 'bi-file-earmark-js';
      else if (['json'].includes(ext)) icon = 'bi-file-earmark-code';
      else if (['md'].includes(ext)) icon = 'bi-file-earmark-text';

      file.innerHTML = `
        <i class="bi ${icon}"></i>
        <span class="file-item-name">${key}</span>
      `;

      file.addEventListener('click', () => {
        document.querySelectorAll('.file-item.active').forEach(el => el.classList.remove('active'));
        file.classList.add('active');
        loadFilePreview(fullPath);
      });

      container.appendChild(file);
    }
  });
}

// Load File Preview
async function loadFilePreview(filePath) {
  try {
    const response = await fetch(`${API_BASE}/files/${filePath}`);
    if (!response.ok) throw new Error('Failed to load file');

    const content = await response.text();
    const ext = filePath.split('.').pop().toLowerCase();

    if (['html', 'htm'].includes(ext)) {
      previewFrame.srcdoc = content;
      previewUrl.value = filePath;
    } else {
      // Show text content in preview
      const encoded = content
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#039;');

      previewFrame.srcdoc = `
        <html>
          <head>
            <style>
              body { font-family: monospace; margin: 20px; white-space: pre-wrap; word-wrap: break-word; }
              code { display: block; background: #f5f5f5; padding: 10px; border-radius: 4px; }
            </style>
          </head>
          <body>
            <code>${encoded}</code>
          </body>
        </html>
      `;
      previewUrl.value = filePath;
    }
  } catch (error) {
    console.error('Error loading file:', error);
    previewFrame.srcdoc = `<html><body><p>Error loading file: ${error.message}</p></body></html>`;
  }
}

// Load Website Preview
function loadPreview(htmlFile) {
  previewUrl.value = htmlFile;
  loadFilePreview(htmlFile);
}

// Chat Functions
function addUserMessage(text) {
  const messageDiv = document.createElement('div');
  messageDiv.className = 'chat-message user';
  messageDiv.innerHTML = `
    <div class="message-content">
      ${escapeHtml(text)}
    </div>
  `;
  chatMessages.appendChild(messageDiv);
  chatMessages.scrollTop = chatMessages.scrollHeight;
}

function addSystemMessage(text) {
  const messageDiv = document.createElement('div');
  messageDiv.className = 'chat-message system';
  messageDiv.innerHTML = `
    <div class="message-content">
      <strong>Locable Assistant:</strong>
      <p>${escapeHtml(text)}</p>
    </div>
  `;
  chatMessages.appendChild(messageDiv);
  chatMessages.scrollTop = chatMessages.scrollHeight;
}

// Utility Functions
function escapeHtml(text) {
  const map = {
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    '"': '&quot;',
    "'": '&#039;',
  };
  return text.replace(/[&<>"']/g, (m) => map[m]);
}