# Vibe Course Platform

Private deployment source for the Vibe Coding homework-submission and AI-assessment platform.

## Repository boundaries

- This repository contains the server, submission client, deployment scripts, tests, and design documentation.
- The public Codex Marketplace is maintained separately at `JasonLuo365/vibe-course-marketplace`.
- Never commit `.env`, `data/`, student tokens, uploaded submissions, or API keys.

## Deployment

Follow [DEPLOY.md](DEPLOY.md). Production uses Docker Compose with Caddy terminating HTTPS.
