from typing import Dict, List

import asyncpg

from database.repositories.material_repository import MaterialRepository


class MaterialService:
    def __init__(self, pool: asyncpg.Pool):
        self.repo = MaterialRepository(pool)

    async def get_material_options(
        self, cable_type: str, fiber_count: int, repair_span_type_id: int
    ) -> Dict[str, List[dict]]:
        config_materials = await self.repo.get_config_materials(
            cable_type, fiber_count, repair_span_type_id
        )
        exclude_ids = [m["material_id"] for m in config_materials]
        additional_materials = await self.repo.get_additional_materials(exclude_ids)
        return {
            "config": [dict(m) for m in config_materials],
            "additional": [dict(m) for m in additional_materials],
        }

    async def get_material(self, material_id: int):
        return await self.repo.get_by_id(material_id)
