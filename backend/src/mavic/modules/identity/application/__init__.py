"""Casos de uso de identidad.

Convenciones de esta capa:
- Cada función pública es un caso de uso: recibe la sesión de base de datos, el
  actor (quién lo pide) y los datos; devuelve "vistas" (dataclasses), nunca
  objetos del ORM.
- La autorización se valida acá (`actor.require(...)`), no en los endpoints.
- El caso de uso hace `session.commit()` una sola vez, al final.
"""
