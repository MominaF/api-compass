"""Declarative base for ORM models. Models are added in later phases and imported here
so Alembic autogenerate can see them."""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass
