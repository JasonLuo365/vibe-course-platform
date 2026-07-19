---
name: "submit-homework"
description: "Preview and submit a Vibe Coding coursework package with the installed vibe-submit MCP tools."
---

# Submit Vibe Coding homework

1. Call `preview_submission` first. Summarize the files, sessions, screenshots,
   size, and excluded entries that would be uploaded.
2. Ask for explicit confirmation before any upload.
3. After confirmation, call `submit_homework` with `confirmed=true` and the
   assignment code supplied by the student.
4. Only use `force_confirmed=true` when the student explicitly confirms a
   resubmission after being told that it replaces their previous attempt.

Never ask the student to paste a server token into the chat, and never expose
tokens in responses. If the upload cannot reach the server, explain that the
submission has been queued locally and guide the student to retry later.

