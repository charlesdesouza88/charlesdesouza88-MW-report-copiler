"""Role-based authentication and data scoping for Mister Wiz."""

import json
import logging
from pathlib import Path

from werkzeug.security import check_password_hash, generate_password_hash

from report_names import class_diagnostic_filename, student_report_filename

logger = logging.getLogger(__name__)

ROLE_SUPERADMIN = 'superadmin'
ROLE_ADMIN = 'admin'
ROLE_TEACHER = 'teacher'

MANAGEMENT_ROLES = frozenset({ROLE_SUPERADMIN, ROLE_ADMIN})
FULL_ACCESS_ROLES = frozenset({ROLE_SUPERADMIN, ROLE_ADMIN})

ROLE_LABELS = {
    ROLE_SUPERADMIN: 'Superadmin',
    ROLE_ADMIN: 'Admin',
    ROLE_TEACHER: 'Professor',
}


def normalize_email(email):
    return (email or '').strip().lower()


def normalize_teacher_name(name):
    return (name or '').strip()


def can_manage_teachers(role):
    return role in MANAGEMENT_ROLES


def has_full_data_access(role):
    return role in FULL_ACCESS_ROLES


def user_public_dict(user):
    return {
        'id': user['id'],
        'email': user['email'],
        'role': user['role'],
        'teacher_name': user.get('teacher_name') or '',
        'active': user.get('active', True),
    }


def teacher_turmas(students, teacher_name):
    """Turma codes owned by a teacher (from student rows)."""
    key = normalize_teacher_name(teacher_name).casefold()
    if not key:
        return set()
    return {
        s.get('turma', '').strip()
        for s in students
        if normalize_teacher_name(s.get('teacher', '')).casefold() == key
        and s.get('turma', '').strip()
    }


def filter_students_for_user(students, user):
    if has_full_data_access(user['role']):
        return list(students)
    key = normalize_teacher_name(user.get('teacher_name', '')).casefold()
    if not key:
        return []
    return [
        s for s in students
        if normalize_teacher_name(s.get('teacher', '')).casefold() == key
    ]


def filter_lessons_for_user(lessons, students, user):
    if has_full_data_access(user['role']):
        return list(lessons)
    turmas = teacher_turmas(students, user.get('teacher_name', ''))
    return [lesson for lesson in lessons if lesson.get('turma', '').strip() in turmas]


def filter_extra_sessions_for_user(sessions, user):
    if has_full_data_access(user['role']):
        return list(sessions)
    key = normalize_teacher_name(user.get('teacher_name', '')).casefold()
    if not key:
        return []
    return [
        row for row in sessions
        if normalize_teacher_name(row.get('teacher', '')).casefold() == key
    ]


def find_extra_session_global_index(all_sessions, filtered_sessions, filtered_idx):
    if filtered_idx < 0 or filtered_idx >= len(filtered_sessions):
        return None
    target = filtered_sessions[filtered_idx]
    for i, row in enumerate(all_sessions):
        if row is target:
            return i
    for i, row in enumerate(all_sessions):
        if (
            row.get('student_name') == target.get('student_name')
            and row.get('date') == target.get('date')
            and row.get('horario') == target.get('horario')
            and row.get('teacher') == target.get('teacher')
        ):
            return i
    return None


def report_belongs_to_turmas(filename, turmas):
    if not turmas:
        return False
    name = Path(filename).name
    for turma in turmas:
        if not turma:
            continue
        if name == class_diagnostic_filename(turma):
            return True
        from report_periods import report_month_from_filename

        file_month = report_month_from_filename(name)
        if file_month and name == class_diagnostic_filename(turma, file_month):
            return True
    return False


def report_belongs_to_teacher(filename, students, teacher_name):
    """Teachers see their students' reports and class diagnostics for their turmas only."""
    name = Path(filename).name
    if 'class_diagnostic' in name:
        return report_belongs_to_turmas(name, teacher_turmas(students, teacher_name))

    key = normalize_teacher_name(teacher_name).casefold()
    if not key:
        return False
    for student in students:
        if normalize_teacher_name(student.get('teacher', '')).casefold() != key:
            continue
        turma = student.get('turma', '').strip()
        student_name = student.get('student_name', '').strip()
        if not turma or not student_name:
            continue
        if student_report_filename(turma, student_name) == name:
            return True
        from report_periods import report_month_from_filename

        file_month = report_month_from_filename(name)
        if file_month and student_report_filename(turma, student_name, file_month) == name:
            return True
    return False


def filter_reports_for_user(files, students, user):
    if has_full_data_access(user['role']):
        return list(files)
    teacher_name = user.get('teacher_name', '')
    return [f for f in files if report_belongs_to_teacher(f.name, students, teacher_name)]


def find_lesson_global_index(all_lessons, filtered_lessons, filtered_idx):
    if filtered_idx < 0 or filtered_idx >= len(filtered_lessons):
        return None
    target = filtered_lessons[filtered_idx]
    for i, row in enumerate(all_lessons):
        if row is target:
            return i
    for i, row in enumerate(all_lessons):
        if (
            row.get('turma') == target.get('turma')
            and row.get('aula_num') == target.get('aula_num')
            and row.get('date') == target.get('date')
        ):
            return i
    return None


def find_student_global_index(all_students, filtered_students, filtered_idx):
    if filtered_idx < 0 or filtered_idx >= len(filtered_students):
        return None
    target = filtered_students[filtered_idx]
    for i, row in enumerate(all_students):
        if row is target:
            return i
    for i, row in enumerate(all_students):
        if (
            row.get('turma') == target.get('turma')
            and row.get('student_name') == target.get('student_name')
            and row.get('teacher') == target.get('teacher')
        ):
            return i
    return None


class UserStore:
    """Persist platform users (PostgreSQL or JSON file)."""

    def __init__(self, db_store=None, json_path=None):
        self.db_store = db_store
        self.json_path = Path(json_path) if json_path else None

    def initialize(self):
        if self.db_store:
            self.db_store.initialize_users()
            return
        if self.json_path:
            self.json_path.parent.mkdir(parents=True, exist_ok=True)
            if not self.json_path.exists():
                self.json_path.write_text('[]', encoding='utf-8')

    def list_users(self):
        if self.db_store:
            return self.db_store.load_users()
        return json.loads(self.json_path.read_text(encoding='utf-8'))

    def _save_all(self, users):
        if self.db_store:
            self.db_store.save_users(users)
            return
        self.json_path.write_text(
            json.dumps(users, ensure_ascii=False, indent=2),
            encoding='utf-8',
        )

    def get_by_email(self, email):
        key = normalize_email(email)
        for user in self.list_users():
            if normalize_email(user.get('email')) == key:
                return dict(user)
        return None

    def get_by_id(self, user_id):
        for user in self.list_users():
            if user.get('id') == user_id:
                return dict(user)
        return None

    def authenticate(self, email, password):
        user = self.get_by_email(email)
        if not user or not user.get('active', True):
            return None
        if not check_password_hash(user.get('password_hash', ''), password):
            return None
        return user_public_dict(user)

    def _has_superadmin(self, users):
        return any(
            u.get('role') == ROLE_SUPERADMIN and u.get('active', True)
            for u in users
        )

    def ensure_bootstrap_superadmin(self, email, password):
        """Create the initial superadmin when none exists."""
        if not email or not password:
            users = self.list_users()
            if not users:
                logger.warning(
                    'No users and bootstrap credentials missing — set SUPERADMIN_EMAIL and SUPERADMIN_PASSWORD.',
                )
            return False

        users = self.list_users()
        if self._has_superadmin(users):
            return False

        next_id = max((u.get('id', 0) for u in users), default=0) + 1
        users.append({
            'id': next_id,
            'email': normalize_email(email),
            'password_hash': generate_password_hash(password),
            'role': ROLE_SUPERADMIN,
            'teacher_name': '',
            'active': True,
        })
        self._save_all(users)
        logger.info('Bootstrap superadmin created for %s', normalize_email(email))
        return True

    def sync_superadmin_password(self, email, password):
        """Update superadmin password from env (recovery). Set SUPERADMIN_SYNC_PASSWORD=1."""
        if not email or not password:
            return False
        users = self.list_users()
        key = normalize_email(email)
        updated = False
        for user in users:
            if user.get('role') == ROLE_SUPERADMIN and normalize_email(user.get('email')) == key:
                user['password_hash'] = generate_password_hash(password)
                user['active'] = True
                updated = True
        if updated:
            self._save_all(users)
            logger.info('Superadmin password synced for %s', key)
        return updated

    def apply_env_superadmin(self, email, password):
        """
        Ensure SUPERADMIN_EMAIL exists as an active superadmin with SUPERADMIN_PASSWORD.
        Runs on every deploy so Railway env vars stay the source of truth.
        """
        if not email or not password:
            return False

        users = self.list_users()
        key = normalize_email(email)
        password_hash = generate_password_hash(password)

        for user in users:
            if normalize_email(user.get('email')) == key:
                user['role'] = ROLE_SUPERADMIN
                user['password_hash'] = password_hash
                user['active'] = True
                user['teacher_name'] = user.get('teacher_name') or ''
                self._save_all(users)
                logger.info('Superadmin reconciled for existing account %s', key)
                return True

        supers = [
            u for u in users
            if u.get('role') == ROLE_SUPERADMIN and u.get('active', True)
        ]
        if len(supers) == 1:
            supers[0]['email'] = key
            supers[0]['password_hash'] = password_hash
            supers[0]['active'] = True
            self._save_all(users)
            logger.info('Superadmin email migrated to %s', key)
            return True

        if not self._has_superadmin(users):
            return self.ensure_bootstrap_superadmin(email, password)

        logger.warning(
            'Multiple superadmins in database; could not apply SUPERADMIN_EMAIL=%s',
            key,
        )
        return False

    def auth_status(self, bootstrap_email=''):
        """Diagnostics for /health/auth (no secrets)."""
        users = self.list_users()
        key = normalize_email(bootstrap_email) if bootstrap_email else ''
        return {
            'user_count': len(users),
            'superadmin_count': sum(
                1 for u in users if u.get('role') == ROLE_SUPERADMIN and u.get('active', True)
            ),
            'bootstrap_email_configured': bool(key),
            'bootstrap_email_registered': bool(
                key and any(normalize_email(u.get('email')) == key for u in users)
            ),
            'accounts': [
                {
                    'email': u.get('email', ''),
                    'role': u.get('role', ''),
                    'active': bool(u.get('active', True)),
                }
                for u in users
            ],
        }

    def create_teacher(self, email, password, teacher_name):
        users = self.list_users()
        if self.get_by_email(email):
            raise ValueError('Este e-mail já está cadastrado.')
        next_id = max((u.get('id', 0) for u in users), default=0) + 1
        users.append({
            'id': next_id,
            'email': normalize_email(email),
            'password_hash': generate_password_hash(password),
            'role': ROLE_TEACHER,
            'teacher_name': normalize_teacher_name(teacher_name),
            'active': True,
        })
        self._save_all(users)
        return next_id

    def create_admin(self, email, password, role=ROLE_ADMIN):
        if role not in MANAGEMENT_ROLES:
            raise ValueError('Papel inválido.')
        users = self.list_users()
        if self.get_by_email(email):
            raise ValueError('Este e-mail já está cadastrado.')
        next_id = max((u.get('id', 0) for u in users), default=0) + 1
        users.append({
            'id': next_id,
            'email': normalize_email(email),
            'password_hash': generate_password_hash(password),
            'role': role,
            'teacher_name': '',
            'active': True,
        })
        self._save_all(users)
        return next_id

    def update_user(self, user_id, *, email=None, password=None, teacher_name=None, active=None):
        users = self.list_users()
        found = False
        for user in users:
            if user.get('id') != user_id:
                continue
            found = True
            if email is not None:
                other = self.get_by_email(email)
                if other and other.get('id') != user_id:
                    raise ValueError('Este e-mail já está em uso.')
                user['email'] = normalize_email(email)
            if password:
                user['password_hash'] = generate_password_hash(password)
            if teacher_name is not None:
                user['teacher_name'] = normalize_teacher_name(teacher_name)
            if active is not None:
                user['active'] = bool(active)
            break
        if not found:
            raise ValueError('Usuário não encontrado.')
        self._save_all(users)

    def delete_user(self, user_id, *, actor_id=None):
        users = self.list_users()
        target = next((u for u in users if u.get('id') == user_id), None)
        if not target:
            raise ValueError('Usuário não encontrado.')
        if target.get('role') == ROLE_SUPERADMIN:
            superadmins = [u for u in users if u.get('role') == ROLE_SUPERADMIN and u.get('active', True)]
            if len(superadmins) <= 1:
                raise ValueError('Não é possível remover o único superadmin ativo.')
        if actor_id is not None and user_id == actor_id:
            raise ValueError('Você não pode remover sua própria conta.')
        users = [u for u in users if u.get('id') != user_id]
        self._save_all(users)
