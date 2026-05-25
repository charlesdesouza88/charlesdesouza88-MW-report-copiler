# Authentication & roles

## Roles

| Role | Access |
|------|--------|
| **superadmin** | All students, lessons, reports; manage admins and teachers |
| **admin** | Same data access as superadmin; create/edit teacher accounts |
| **teacher** (subadmin) | Only rows where CSV `teacher` matches their account `teacher_name`, plus lessons/reports for those turmas |

## Login

- Email + password (hashed with Werkzeug).
- Users stored in PostgreSQL table `users` when `DATABASE_URL` is set, otherwise `data/users.json`.
- On first run with no users, a **superadmin** is created from `SUPERADMIN_EMAIL` and `SUPERADMIN_PASSWORD`.

## Teacher scoping

1. Admin uploads student CSV (column `teacher` = display name, e.g. `Chuck`).
2. Admin creates teacher account at **Usuários** with the same `teacher_name`.
3. Teacher logs in and sees only matching students, turmas, lessons, and generated reports (`{turma}_*.html`).

## Admin workflows

- **Upload CSV** — superadmin/admin only (full replace).
- **Usuários** (`/admin/teachers`) — create professors (email + password + teacher name); superadmin can also create admin/superadmin accounts.

## Session

Flask session stores: `user_id`, `email`, `role`, `teacher_name`.
