const API_BASE = 'http://127.0.0.1:9200';

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
const htmlOnlyMode = document.getElementById('htmlOnlyMode');

let currentGeneratedFiles = [];
let isGenerating = false;
let startTime = null;
let currentRunId = null;
let messageCursor = 0;
let messagesInterval = null;
let lastPreviewPath = null;

// Resizer functionality
let isResizing = false;
let currentResizer = null;

// Initialize
document.addEventListener('DOMContentLoaded', () => {
  chatInput.disabled = false;
  sendBtn.disabled = false;
  autoResizeChatInput();
  checkHealth();
  initResizers();
});

// Event Listeners
chatInput.addEventListener('input', autoResizeChatInput);

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
  if (lastPreviewPath) {
    loadFilePreview(lastPreviewPath, true);
  } else if (previewFrame.src) {
    previewFrame.src = previewFrame.src;
  }
});

fullscreenBtn.addEventListener('click', () => {
  if (previewFrame.requestFullscreen) {
    previewFrame.requestFullscreen();
  }
});

// Initialize resizers for draggable panels
function initResizers() {
  const fileExplorer = document.querySelector('.file-explorer');
  const chatPanel = document.querySelector('.chat-panel');
  const fileResizer = fileExplorer.querySelector('.resizer-right');
  const chatResizer = chatPanel.querySelector('.resizer-left');

  // File explorer resizer
  fileResizer.addEventListener('mousedown', (e) => {
    isResizing = true;
    currentResizer = 'file-explorer';
    fileResizer.classList.add('resizing');
    document.body.style.cursor = 'col-resize';
    document.body.style.userSelect = 'none';
  });

  // Chat panel resizer
  chatResizer.addEventListener('mousedown', (e) => {
    isResizing = true;
    currentResizer = 'chat-panel';
    chatResizer.classList.add('resizing');
    document.body.style.cursor = 'col-resize';
    document.body.style.userSelect = 'none';
  });

  document.addEventListener('mousemove', (e) => {
    if (!isResizing) return;

    if (currentResizer === 'file-explorer') {
      const newWidth = e.clientX;
      if (newWidth >= 150 && newWidth <= 500) {
        fileExplorer.style.width = `${newWidth}px`;
      }
    } else if (currentResizer === 'chat-panel') {
      const newWidth = window.innerWidth - e.clientX;
      if (newWidth >= 250 && newWidth <= 600) {
        chatPanel.style.width = `${newWidth}px`;
      }
    }
  });

  document.addEventListener('mouseup', () => {
    if (isResizing) {
      isResizing = false;
      currentResizer = null;
      document.body.style.cursor = '';
      document.body.style.userSelect = '';
      fileResizer.classList.remove('resizing');
      chatResizer.classList.remove('resizing');
    }
  });
}

// Check API Health
async function checkHealth() {
  try {
    const response = await fetch(`${API_BASE}/health`);
    if (!response.ok) throw new Error('Health check failed');
    addSystemMessage('Connected to API server');
    statusText.textContent = 'Connected';
  } catch (error) {
    addSystemMessage('Cannot connect to API server. Ensure it is running on port 9200.');
    statusText.textContent = 'Disconnected';
  }
}

// Send Message and Generate Website
async function sendMessage() {
  const prompt = chatInput.value.trim();
  if (!prompt || isGenerating) return;

  addUserMessage(prompt);
  chatInput.value = '';
  autoResizeChatInput();
  await generateWebsite(prompt);
}

// Generate Website via API
async function generateWebsite(prompt) {
  if (isGenerating) return;

  if (messagesInterval) {
    clearInterval(messagesInterval);
    messagesInterval = null;
  }

  isGenerating = true;
  startTime = Date.now();
  chatInput.disabled = true;
  sendBtn.disabled = true;
  statusText.textContent = 'Generating...';

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
        mode: htmlOnlyMode && htmlOnlyMode.checked ? 'html-only' : 'full',
      }),
    });

    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || 'Generation failed');
    }

    const result = await response.json();

    currentRunId = result.run_id || null;
    messageCursor = 0;

    if (result.message) {
      addAssistantMessage(result.message);
    }

    const elapsed = ((Date.now() - startTime) / 1000).toFixed(2);
    generationTime.textContent = `Generated in ${elapsed}s`;

    await loadMessages(true);
    messagesInterval = setInterval(() => loadMessages(), 2000);
    await loadFiles(result.files);

    if (result.files.length > 0) {
      const htmlFiles = result.files.filter((f) => f.endsWith('.html'));
      if (htmlFiles.length > 0) {
        loadPreview(htmlFiles[0]);
      }
    }

    statusText.textContent = 'Ready';
    addSystemMessage(`Website generated with ${result.files.length} files`);
  } catch (error) {
    console.error('Generation error:', error);
    statusText.textContent = 'Error';
    addSystemMessage(`Error: ${error.message}`);
  } finally {
    isGenerating = false;
    chatInput.disabled = false;
    sendBtn.disabled = false;
    autoResizeChatInput();
    modal.hide();
  }
}

// Load Files from API
async function loadFiles(files) {
  currentGeneratedFiles = files;

  if (files.length === 0) {
    fileList.innerHTML = '<div class="text-center py-5" style="color: var(--muted); font-size: 0.85rem;"><p>No files generated</p></div>';
    return;
  }

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
  Object.keys(tree)
    .sort()
    .forEach((key) => {
      const isDirectory = tree[key] !== null && typeof tree[key] === 'object';
      const fullPath = prefix ? `${prefix}/${key}` : key;

      if (isDirectory) {
        const folder = document.createElement('div');
        folder.className = 'file-item-folder';

        const header = document.createElement('div');
        header.className = 'file-item';
        header.innerHTML = `<i class="bi bi-folder"></i><span class="file-item-name">${key}</span>`;

        const children = document.createElement('div');
        children.style.paddingLeft = '12px';
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
        let icon = 'bi-file-earmark';
        if (['html', 'htm'].includes(ext)) icon = 'bi-file-earmark-code';
        else if (['css'].includes(ext)) icon = 'bi-filetype-css';
        else if (['js'].includes(ext)) icon = 'bi-filetype-js';
        else if (['json'].includes(ext)) icon = 'bi-filetype-json';

        file.innerHTML = `<i class="bi ${icon}"></i><span class="file-item-name">${key}</span>`;

        file.addEventListener('click', () => {
          document.querySelectorAll('.file-item.active').forEach((el) => el.classList.remove('active'));
          file.classList.add('active');
          loadFilePreview(fullPath);
        });

        container.appendChild(file);
      }
    });
}

// Load File Preview
async function loadFilePreview(filePath, forceReload = false) {
  lastPreviewPath = filePath;
  try {
    const ext = filePath.split('.').pop().toLowerCase();

    if (['html', 'htm'].includes(ext)) {
      const normalizedPath = filePath.startsWith('site/') ? filePath : `site/${filePath}`;
      const cacheBuster = forceReload ? `?t=${Date.now()}` : '';
      const previewSrc = `${API_BASE}/${normalizedPath}${cacheBuster}`;

      previewFrame.srcdoc = '';
      previewFrame.removeAttribute('srcdoc');
      previewFrame.src = previewSrc;
      previewUrl.value = `/${normalizedPath}`;
      return;
    }

    const response = await fetch(`${API_BASE}/files/${filePath}${forceReload ? `?t=${Date.now()}` : ''}`);
    if (!response.ok) throw new Error('Failed to load file');

    const content = await response.text();
    const encoded = content
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;');

    previewFrame.srcdoc = `
      <html>
        <head>
          <style>
            body { font-family: monospace; margin: 20px; white-space: pre-wrap; background: #1a1c21; color: #f7f7f7; }
            code { display: block; background: #16181c; padding: 15px; border-radius: 6px; border: 1px solid #2a2d33; }
          </style>
        </head>
        <body><code>${encoded}</code></body>
      </html>
    `;
    previewUrl.value = filePath;
  } catch (error) {
    console.error('Error loading file:', error);
    previewFrame.srcdoc = `<html><body style="padding: 20px; background: #1a1c21; color: #f7f7f7;"><p>Error loading file: ${error.message}</p></body></html>`;
  }
}

// Load Website Preview
function loadPreview(htmlFile) {
  loadFilePreview(htmlFile);
}

// Chat Functions
function addUserMessage(text) {
  const messageDiv = document.createElement('div');
  messageDiv.className = 'chat-message user';
  messageDiv.innerHTML = `<div class="message-content">${escapeHtml(text)}</div>`;
  chatMessages.appendChild(messageDiv);
  chatMessages.scrollTop = chatMessages.scrollHeight;
}

function addSystemMessage(text) {
  const messageDiv = document.createElement('div');
  messageDiv.className = 'chat-message system';
  messageDiv.innerHTML = `<div class="message-content"><strong>Assistant</strong><p>${escapeHtml(text)}</p></div>`;
  chatMessages.appendChild(messageDiv);
  chatMessages.scrollTop = chatMessages.scrollHeight;
}

function addAssistantMessage(text) {
  const messageDiv = document.createElement('div');
  messageDiv.className = 'chat-message system';
  messageDiv.innerHTML = `<div class="message-content"><strong>Assistant</strong><p>${escapeHtml(text)}</p></div>`;
  chatMessages.appendChild(messageDiv);
  chatMessages.scrollTop = chatMessages.scrollHeight;
}

// Message loading from API
async function loadMessages(reset = false) {
  if (!currentRunId) return;
  try {
    const response = await fetch(
      `${API_BASE}/messages?run_id=${encodeURIComponent(currentRunId)}&cursor=${messageCursor}`
    );
    if (!response.ok) return;

    const data = await response.json();
    if (reset) {
      chatMessages.innerHTML = '';
    }

    (data.messages || []).forEach((msg) => {
      if (msg.role === 'user') {
        addUserMessage(msg.content || '');
      } else if (msg.role === 'assistant') {
        addAssistantMessage(msg.content || '');
      }
    });
    messageCursor = data.next_cursor || messageCursor;
  } catch (err) {
    console.error('Failed to load messages', err);
  }
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

function autoResizeChatInput() {
  chatInput.style.height = 'auto';
  const newHeight = Math.min(chatInput.scrollHeight, 200);
  chatInput.style.height = `${newHeight}px`;
}
