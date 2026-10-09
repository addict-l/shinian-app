from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select

from app.db.database import SessionLocal
from app.models.memory import MemoryModel
from app.models.memory_person import MemoryPersonModel
from app.schemas.memory import Memory, MemoryCreate


class MemoryRepository:

    @staticmethod
    def _to_schema(
        model: MemoryModel,
    ) -> Memory:

        person_ids: list[UUID] = []
        for person in model.people:
            # person 是完整的 FamilyMemberModel，这里只取它的 id
            person_ids.append(UUID(str(person.id)))

        return Memory(
            primary_person_id=model.primary_person_id,
            version=model.version,
            information=model.information or {},
            media_urls=[asset.file_url for asset in sorted(model.media_assets, key=lambda a: (a.created_at, a.position, a.id))],
            id=model.id,
            family_id=model.family_id,
            person_ids=person_ids,
            source_session_id=(
                UUID(str(model.source_session_id))
                if model.source_session_id is not None
                else None
            ),
            title=model.title,
            raw_content=model.raw_content,
            summary=model.summary,
            memory_date=model.memory_date,
            location=model.location,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )

    def create(
        self,
        data: MemoryCreate,
        source_session_id: UUID | None = None,
    ) -> Memory:

        now = datetime.now(timezone.utc)

        # person_ids 不是 memories 表的列，这里不能写进 MemoryModel
        memory_model = MemoryModel(
            primary_person_id=str(data.primary_person_id) if data.primary_person_id else None,
            information=data.information.model_dump(mode='json'),
            family_id=str(data.family_id),
            source_session_id=str(source_session_id) if source_session_id is not None else None,
            title=data.title,
            raw_content=data.raw_content,
            summary=data.summary,
            memory_date=data.memory_date,
            location=data.location,
            created_at=now,
            updated_at=now,
        )

        with SessionLocal() as session:

            # 1) 先加入 session
            session.add(memory_model)

            # 2) flush：确保有 memory_model.id，事务尚未提交
            session.flush()

            # 3) 再写中间表 memory_persons
            for person_id in data.person_ids:
                link = MemoryPersonModel(
                    memory_id=memory_model.id,
                    family_member_id=str(person_id),
                )
                session.add(link)

            # 4) 一次提交：回忆 + 所有关联一起成功
            session.commit()

            session.refresh(memory_model)

            return self._to_schema(memory_model)

    def get(
        self,
        memory_id: UUID,
    ) -> Memory | None:

        with SessionLocal() as session:

            model = session.get(
                MemoryModel,
                str(memory_id),
            )

            if model is None:
                return None

            return self._to_schema(model)

    def list(
        self,
        family_id: UUID | None = None,
    ) -> list[Memory]:

        with SessionLocal() as session:

            statement = select(MemoryModel)

            if family_id is not None:
                statement = statement.where(
                    MemoryModel.family_id == str(family_id)
                )

            statement = statement.order_by(
                MemoryModel.created_at.desc()
            )

            models = session.scalars(statement).all()

            result: list[Memory] = []
            for model in models:
                result.append(self._to_schema(model))

            return result

    def get_by_source_session(
    self,
    session_id: UUID,
) -> Memory | None:

        with SessionLocal() as session:

            statement = select(MemoryModel).where(
                MemoryModel.source_session_id
                == str(session_id)
            )

            model = session.scalar(statement)

            if model is None:
                return None

            return self._to_schema(model)
