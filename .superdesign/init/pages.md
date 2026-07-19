# Key page dependency trees

## `/` — Course dashboard

Entry: `server/app/templates/dashboard.html`

Dependencies:

- `server/app/templates/dashboard.html`
  - `server/app/templates/base.html`
  - `server/app/static/app.css`

## `/assignments/{aid}/board` — Assignment board

Entry: `server/app/templates/board.html`

Dependencies:

- `server/app/templates/board.html`
  - `server/app/templates/base.html`
  - `server/app/static/app.css`

## `/submissions/{sid}` — Teacher review detail

Entry: `server/app/templates/submission.html`

Dependencies:

- `server/app/templates/submission.html`
  - `server/app/templates/base.html`
  - `server/app/static/app.css`

## `/assignments/{aid}/present` — Classroom presentation

Entry: `server/app/templates/present.html`

Dependencies:

- `server/app/templates/present.html`
  - `server/app/static/present.css`

