---
name: omni-plan
description: Planificación estratégica con flujo opcional de entrevista
argument-hint: "[--direct|--consensus|--review] [--interactive] [--deliberate] <descripción de la tarea>"
pipeline: [deep-interview, omni-plan, autopilot]
next-skill: autopilot
handoff: .omni/plans/ralplan-*.md
level: 4
lang: es
---

<Purpose>
/plan crea planes de trabajo detallados y accionables mediante interacción
inteligente. Detecta automáticamente si debe entrevistar al usuario
(solicitudes amplias) o planificar directamente (solicitudes con detalle),
y soporta el modo consenso (bucle iterativo Planner / Architect / Critic con
deliberación estructurada RALPLAN-DR) y el modo revisión (evaluación del
Critic sobre un plan existente).
</Purpose>

<Cuándo_Usar>
- Quieres planificar antes de implementar
- Necesitas recogida estructurada de requisitos para una idea vaga
- Quieres revisión de un plan existente (`--review`)
- Quieres consenso multi-perspectiva sobre un plan (`--consensus`)
</Cuándo_Usar>

<Notas>
Este archivo es la traducción canónica al español (Phase-C C21). Cuando
OMNI_SKILL_LANG=es esté definido, `scripts/skill_i18n.py` resolverá la
descripción del skill desde aquí en lugar del `SKILL.md` base. El texto
inglés en el `SKILL.md` raíz sigue siendo la fuente de verdad para la
lógica ejecutable; las traducciones sólo cubren los campos orientados
al usuario: `description`, `argument-hint` y el cuerpo `<Purpose>`.
</Notas>
