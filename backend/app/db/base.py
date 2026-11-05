"""Declarative base for ORM models. Models are registered in app/models/__init__.py,
which Alembic imports so autogenerate can see them."""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass
