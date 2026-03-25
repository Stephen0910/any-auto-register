from __future__ import annotations

from datetime import datetime, timezone

from sqlmodel import Session, select

from core.db import ProviderDefinitionModel, ProviderSettingModel, engine
from core.provider_drivers import get_driver_template, list_builtin_provider_definitions, list_driver_templates


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ProviderDefinitionsRepository:
    def ensure_seeded(self) -> None:
        with Session(engine) as session:
            existing = {
                (item.provider_type, item.provider_key): item
                for item in session.exec(select(ProviderDefinitionModel)).all()
            }
            changed = False
            for definition in list_builtin_provider_definitions():
                key = (str(definition.get("provider_type") or ""), str(definition.get("provider_key") or ""))
                if key in existing:
                    item = existing[key]
                    if item.is_builtin:
                        item.label = str(definition.get("label") or item.label)
                        item.description = str(definition.get("description") or item.description)
                        item.driver_type = str(definition.get("driver_type") or item.driver_type)
                        item.default_auth_mode = str(definition.get("default_auth_mode") or item.default_auth_mode)
                        item.enabled = bool(definition.get("enabled", True))
                        item.set_auth_modes(list(definition.get("auth_modes") or []))
                        item.set_fields(list(definition.get("fields") or []))
                        item.set_metadata(dict(definition.get("metadata") or {}))
                        item.updated_at = _utcnow()
                        session.add(item)
                        changed = True
                    continue
                item = ProviderDefinitionModel(
                    provider_type=key[0],
                    provider_key=key[1],
                    label=str(definition.get("label") or key[1]),
                    description=str(definition.get("description") or ""),
                    driver_type=str(definition.get("driver_type") or ""),
                    default_auth_mode=str(definition.get("default_auth_mode") or ""),
                    enabled=bool(definition.get("enabled", True)),
                    is_builtin=bool(definition.get("is_builtin", False)),
                )
                item.set_auth_modes(list(definition.get("auth_modes") or []))
                item.set_fields(list(definition.get("fields") or []))
                item.set_metadata(dict(definition.get("metadata") or {}))
                item.created_at = _utcnow()
                item.updated_at = _utcnow()
                session.add(item)
                changed = True
            if changed:
                session.commit()

    def list_by_type(self, provider_type: str, *, enabled_only: bool = False) -> list[ProviderDefinitionModel]:
        self.ensure_seeded()
        with Session(engine) as session:
            query = select(ProviderDefinitionModel).where(ProviderDefinitionModel.provider_type == provider_type)
            if enabled_only:
                query = query.where(ProviderDefinitionModel.enabled == True)  # noqa: E712
            return session.exec(query.order_by(ProviderDefinitionModel.id)).all()

    def get_by_key(self, provider_type: str, provider_key: str) -> ProviderDefinitionModel | None:
        self.ensure_seeded()
        with Session(engine) as session:
            return session.exec(
                select(ProviderDefinitionModel)
                .where(ProviderDefinitionModel.provider_type == provider_type)
                .where(ProviderDefinitionModel.provider_key == provider_key)
            ).first()

    def save(
        self,
        *,
        definition_id: int | None,
        provider_type: str,
        provider_key: str,
        label: str,
        description: str,
        driver_type: str,
        enabled: bool,
        default_auth_mode: str = "",
        metadata: dict | None = None,
    ) -> ProviderDefinitionModel:
        template = get_driver_template(provider_type, driver_type)
        if not template:
            raise ValueError(f"未知 provider driver: {provider_type}/{driver_type}")

        with Session(engine) as session:
            if definition_id:
                item = session.get(ProviderDefinitionModel, definition_id)
                if not item:
                    raise ValueError("provider definition 不存在")
            else:
                item = session.exec(
                    select(ProviderDefinitionModel)
                    .where(ProviderDefinitionModel.provider_type == provider_type)
                    .where(ProviderDefinitionModel.provider_key == provider_key)
                ).first()
                if not item:
                    item = ProviderDefinitionModel(
                        provider_type=provider_type,
                        provider_key=provider_key,
                    )
                    item.created_at = _utcnow()

            item.provider_type = provider_type
            item.provider_key = provider_key
            item.label = label or provider_key
            item.description = description or ""
            item.driver_type = driver_type
            item.default_auth_mode = default_auth_mode or str(template.get("default_auth_mode") or "")
            item.enabled = bool(enabled)
            item.set_auth_modes(list(template.get("auth_modes") or []))
            item.set_fields(list(template.get("fields") or []))
            item.set_metadata(dict(metadata or {}))
            item.updated_at = _utcnow()
            session.add(item)
            session.commit()
            session.refresh(item)
            return item

    def delete(self, definition_id: int) -> bool:
        with Session(engine) as session:
            item = session.get(ProviderDefinitionModel, definition_id)
            if not item:
                return False
            if item.is_builtin:
                raise ValueError("内置 provider definition 不允许删除")
            has_settings = session.exec(
                select(ProviderSettingModel)
                .where(ProviderSettingModel.provider_type == item.provider_type)
                .where(ProviderSettingModel.provider_key == item.provider_key)
            ).first()
            if has_settings:
                raise ValueError("请先删除对应 provider 配置，再删除 definition")
            session.delete(item)
            session.commit()
            return True

    def list_driver_templates(self, provider_type: str) -> list[dict]:
        return list_driver_templates(provider_type)
