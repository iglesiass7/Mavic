"""Módulos de negocio. Cada uno se organiza en capas:

    api/             rutas HTTP y esquemas de entrada/salida
    application/     casos de uso (orquestan, manejan la transacción)
    domain/          reglas del negocio, sin dependencias externas
    infrastructure/  base de datos y proveedores externos

Las dependencias apuntan hacia el dominio: api -> application -> domain,
e infrastructure implementa lo que application necesita.
"""
