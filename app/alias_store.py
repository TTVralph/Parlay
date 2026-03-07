from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from .db.models import AliasOverrideORM


VALID_ALIAS_TYPES = {'player', 'team', 'market'}


def list_aliases(db: Session, alias_type: str | None = None) -> list[AliasOverrideORM]:
    stmt = select(AliasOverrideORM).order_by(AliasOverrideORM.alias_type, AliasOverrideORM.alias)
    if alias_type:
        stmt = stmt.where(AliasOverrideORM.alias_type == alias_type)
    return list(db.scalars(stmt).all())



def upsert_alias(db: Session, alias_type: str, alias: str, canonical_value: str, created_by: str | None = None) -> AliasOverrideORM:
    alias_type = alias_type.lower().strip()
    if alias_type not in VALID_ALIAS_TYPES:
        raise ValueError(f'Unsupported alias_type: {alias_type}')
    alias_key = alias.lower().strip()
    existing = db.scalar(select(AliasOverrideORM).where(
        AliasOverrideORM.alias_type == alias_type,
        AliasOverrideORM.alias == alias_key,
    ))
    if existing:
        existing.canonical_value = canonical_value
        if created_by:
            existing.created_by = created_by
        db.commit()
        db.refresh(existing)
        return existing

    row = AliasOverrideORM(
        alias_type=alias_type,
        alias=alias_key,
        canonical_value=canonical_value,
        created_by=created_by,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row
