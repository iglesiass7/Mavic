"""Paginación común a todos los listados.

    GET /cases?limit=20&offset=40   ->  {"items": [...], "total": 137, "limit": 20, "offset": 40}

`total` permite al frontend mostrar "página 3 de 7" sin pedir todo. El máximo
de 100 por página evita respuestas gigantes (en el original había un listado
de facturas con límite de 100.000).
"""

from typing import Annotated

from fastapi import Query
from pydantic import BaseModel

Limit = Annotated[int, Query(ge=1, le=100, description="Cantidad de resultados (máx. 100)")]
Offset = Annotated[int, Query(ge=0, description="Cuántos resultados saltear")]


class PageOut[T](BaseModel):
    items: list[T]
    total: int
    limit: int
    offset: int
