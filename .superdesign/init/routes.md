# Route map

| Route | Handler | Template / layout | Purpose |
| --- | --- | --- | --- |
| `/` | `server/app/web/pages.py:dashboard` | `dashboard.html` → `base.html` | Course dashboard |
| `/login` | `server/app/web/pages.py:login_page` | `login.html` → `base.html` | Teacher login |
| `/assignments/{aid}/board` | `server/app/web/pages.py:board_page` | `board.html` → `base.html` | Assignment progress and student matrix |
| `/submissions/{sid}` | `server/app/web/detail.py:submission_detail` | `submission.html` → `base.html` | Private teacher review and work detail |
| `/submissions/{sid}/code` | `server/app/web/detail.py:submission_code` | `code_view.html` → `base.html` | Read-only source viewer |
| `/assignments/{aid}/present` | `server/app/web/present.py:present_page` | `present.html` + `present.css` | Classroom presentation |

The UI is server-rendered with Jinja2; no SPA framework or component library is used.

