const form = document.querySelector("#chat-form");
const input = document.querySelector("#assistant-message");
const log = document.querySelector("#chat-log");
const submitButton = document.querySelector("#send-message");
const status = document.querySelector("#assistant-status");

const appendMessage = (role, content, markdown = false) => {
  const row = document.createElement("div");
  row.className = `assistant-message${role === "user" ? " user" : ""}`;

  const bubble = document.createElement("div");
  bubble.className = "assistant-bubble";
  const author = document.createElement("strong");
  author.textContent = role === "user" ? "You" : "CareerPilot";
  const body = document.createElement("div");
  body.className = "mt-2";

  if (markdown && window.marked && window.DOMPurify) {
    body.innerHTML = window.DOMPurify.sanitize(window.marked.parse(content));
  } else {
    body.textContent = content;
    body.style.whiteSpace = "pre-wrap";
  }

  bubble.append(author, body);
  row.append(bubble);
  log.append(row);
  log.scrollTop = log.scrollHeight;
};

const setBusy = (busy) => {
  input.disabled = busy;
  submitButton.disabled = busy;
  submitButton.querySelector("span").textContent = busy ? "Sending…" : "Send";
  status.textContent = busy ? "CareerPilot is preparing a response." : "";
};

input.addEventListener("keydown", (event) => {
  if (event.key !== "Enter" || event.shiftKey) return;
  if (event.isComposing || event.keyCode === 229) return;
  event.preventDefault();
  form.requestSubmit();
});

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const message = input.value.trim();
  if (!message || submitButton.disabled) return;

  appendMessage("user", message);
  input.value = "";
  setBusy(true);

  const controller = new AbortController();
  const timeoutId = window.setTimeout(() => controller.abort(), 20000);
  try {
    const response = await fetch("/chatbot/ask", {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify({ message }),
      signal: controller.signal,
    });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.error || "The assistant could not answer just now.");
    appendMessage("assistant", payload.response || "No response received.", true);
  } catch (error) {
    appendMessage(
      "assistant",
      error.name === "AbortError" ? "The response took too long. Please try again with a shorter question." : error.message || "Unable to connect to the assistant. Please try again.",
    );
  } finally {
    window.clearTimeout(timeoutId);
    setBusy(false);
    input.focus();
  }
});
