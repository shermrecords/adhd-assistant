const SpeechManager = (function () {
  let queue = [];
  let isSpeaking = false;
  let selectedVoice = null;

  function setVoice(voice) {
    selectedVoice = voice;
  }

  function speak(text) {
    queue.push(text);
    processQueue();
  }

  const MAX_UTTERANCE_LENGTH = 200;  // Adjust this based on your needs

  function processQueue() {
    if (isSpeaking || queue.length === 0) return;
  
    const text = queue.shift();
    const chunks = splitTextIntoChunks(text, MAX_UTTERANCE_LENGTH);
  
    // Process each chunk
    chunks.forEach(chunk => {
      const utterance = new SpeechSynthesisUtterance(chunk);
      if (selectedVoice) utterance.voice = selectedVoice;
  
      isSpeaking = true;
  
      utterance.onend = () => {
        isSpeaking = false;
        processQueue();
      };
  
      utterance.onerror = (e) => {
        console.error('Speech error:', e.error);
        isSpeaking = false;
        processQueue();
      };
  
      speechSynthesis.speak(utterance);
    });
  }

  function splitTextIntoChunks(text, maxLength) {
    const chunks = [];
    let currentChunk = '';
  
    text.split(' ').forEach(word => {
      if ((currentChunk + ' ' + word).length <= maxLength) {
        currentChunk += ' ' + word;
      } else {
        chunks.push(currentChunk.trim());
        currentChunk = word;
      }
    });
  
    if (currentChunk) {
      chunks.push(currentChunk.trim());
    }
  
    return chunks;
  }

  function clearQueue() {
    queue = [];
    // Remove cancel unless needed
    // speechSynthesis.cancel();
    isSpeaking = false;
  }

  return {
    speak,
    setVoice,
    clearQueue
  };
})();

function autoSelectVoice() {
  const voices = speechSynthesis.getVoices();

  let bestVoice =
    voices.find(v => v.name === 'Google US English') ||
    voices.find(v => v.lang.startsWith('en')) ||
    voices[0];  // fallback to the first available voice

  if (bestVoice) {
    SpeechManager.setVoice(bestVoice);
    console.log("Selected voice:", bestVoice.name);
  } else {
    console.warn("No suitable voice found. Using default.");
  }
}

if (typeof speechSynthesis !== 'undefined') {
  // Handle voices being loaded or changed asynchronously
  speechSynthesis.onvoiceschanged = autoSelectVoice;
  
  // Call initially in case voices are already available
  if (speechSynthesis.getVoices().length) {
    autoSelectVoice();
  } else {
    setTimeout(autoSelectVoice, 1000);  // Retry after 1 second
  }
}

const userInput = document.getElementById("userInput");
if (userInput) {
  userInput.addEventListener("keydown", function(event) {
    if (event.key === "Enter") {
      event.preventDefault();
      sendText();
    }
  });
}

async function sendText() {
  const inputEl = document.getElementById('userInput');
  const input = inputEl.value.trim();
  if (!input) return;

  displayMessage('user', input);
  inputEl.value = '';

  // Display "Thinking..." while waiting for the response
  displayMessage('assistant', 'Thinking...');

  try {
    const response = await fetch('https://adhd-assistant.onrender.com', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ input })
    });

    const data = await response.json();
    const reply = data.responseText || "Sorry, I couldn't understand the response.";
    displayMessage('assistant', reply);
    SpeechManager.speak(reply);
  } catch (err) {
    displayMessage('assistant', 'Error: Could not reach the server.');
    console.error(err);
  }
}

function startListening() {
  const recognition = new (window.SpeechRecognition || window.webkitSpeechRecognition)();
  recognition.lang = 'en-US';
  recognition.start();

  displayMessage('assistant', '🎙 Listening...');

  recognition.onresult = async function(event) {
    const transcript = event.results[0][0].transcript;
    displayMessage('user', transcript);

    try {
      const response = await fetch('https://adhd-assistant.onrender.com', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ input: transcript })
      });

      const data = await response.json();
      const reply = data.responseText || "Sorry, I couldn't understand the response.";
      displayMessage('assistant', reply);
      SpeechManager.speak(reply);
    } catch (error) {
      displayMessage('assistant', 'Error: Could not reach the server.');
      console.error(error);
    }
  };

  recognition.onerror = function(event) {
    displayMessage('assistant', `Speech recognition error: ${event.error}. Please check your microphone settings.`);
  };
}

function displayMessage(sender, text) {
  const chatBox = document.getElementById('chatBox');
  const messageDiv = document.createElement('div');
  messageDiv.className = `message ${sender}`;
  messageDiv.textContent = text;

  chatBox.appendChild(messageDiv);
  chatBox.scrollTop = chatBox.scrollHeight; // Smooth scroll to the bottom
}
