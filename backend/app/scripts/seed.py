"""Development seed data: one user per role (+ a second STAFF) and a few resources.

Run after migrations:  python -m app.scripts.seed
Safe to run twice: existing emails / resource names are skipped.
Never run against production.
"""

from datetime import time

from sqlalchemy import func, select

from app.core.config import get_settings
from app.core.security import hash_password
from app.db.models import Resource, Role, User
from app.db.session import SessionLocal

DEV_PASSWORD = "Campus123!"

USERS = [
    ("Demo Student", "student@campus.test", Role.STUDENT),
    ("Demo Student 2", "student2@campus.test", Role.STUDENT),
    # Two STAFF accounts: STAFF cannot verify their own reservation (R5),
    # so the demo needs a second staff member to verify the first one's QR.
    ("Demo Staff", "staff@campus.test", Role.STAFF),
    ("Demo Staff 2", "staff2@campus.test", Role.STAFF),
    ("Demo Admin", "admin@campus.test", Role.ADMIN),
]

RESOURCES = [
    dict(name="Study Room A", type="STUDY_ROOM", location="Library, Floor 1", capacity=6,
         description="Quiet study room", opens_at=time(8, 0), closes_at=time(22, 0)),
    dict(name="Study Room B", type="STUDY_ROOM", location="Library, Floor 2", capacity=4,
         description="Small group room with whiteboard", opens_at=time(8, 0), closes_at=time(22, 0)),
    dict(name="Computer Lab 204", type="LAB", location="Engineering Building, 2nd Floor", capacity=30,
         description="30 PCs, projector", opens_at=time(9, 0), closes_at=time(18, 0)),
    dict(name="Meeting Room M1", type="MEETING_ROOM", location="Main Building", capacity=10,
         description="Screen and video conferencing", opens_at=time(8, 30), closes_at=time(20, 0)),
    dict(name="Projector P-01", type="EQUIPMENT", location="IT Desk", capacity=None,
         description="Portable projector with HDMI cable", opens_at=time(9, 0), closes_at=time(17, 0)),
]


def main() -> None:
    if get_settings().is_production:
        raise SystemExit("Refusing to seed a production database.")

    with SessionLocal() as db, db.begin():
        password_hash = hash_password(DEV_PASSWORD)
        for full_name, email, role in USERS:
            exists = db.scalar(select(User.id).where(func.lower(User.email) == email.lower()))
            if not exists:
                db.add(User(full_name=full_name, email=email, password_hash=password_hash, role=role.value))

        for data in RESOURCES:
            exists = db.scalar(select(Resource.id).where(Resource.name == data["name"]))
            if not exists:
                db.add(Resource(**data))

    print(f"Seed complete. All demo users use password: {DEV_PASSWORD}")
    for _, email, role in USERS:
        print(f"  {role.value:<8} {email}")


if __name__ == "__main__":
    main()
