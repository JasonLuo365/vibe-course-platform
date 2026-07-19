# Extractable UI components

## TeacherTopNav

- Source: `server/app/templates/base.html`
- Category: layout
- Description: Shared teacher top navigation with product label and signed-in teacher identity.
- Extractable props: `teacherName` (string, default: `教师`)
- Hardcoded: Vibe teacher product label, layout, type, and navigation styling.

## StudentStatusCard

- Source: `server/app/templates/board.html`
- Category: basic
- Description: Student card showing identity, submission state, AI grade, and final grade.
- Extractable props: `status` (string, default: `已提交`), `aiGrade` (string, default: `B`), `finalGrade` (string, default: `B`)
- Hardcoded: student-card layout and badge treatment.

