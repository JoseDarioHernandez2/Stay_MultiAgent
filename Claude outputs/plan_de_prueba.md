# Plan de Prueba — Stay MultiAgent Workflow

**Proyecto:** customer-retention-workflow v1.0.0
**Equipo:** Equipo 2 — Abandono (MINE009, Universidad Externado de Colombia)
**Fecha:** 2026-09-16

---

## 1. Objetivo

Validar de extremo a extremo que el sistema multiagente de retención de clientes cumple con los 6 criterios de evaluación de la rúbrica del docente, produce resultados correctos, mantiene los contratos tipados y resiste escenarios adversos.

---

## 2. Entorno de Ejecución

| Componente | Versión / Config |
|---|---|
| Python | 3.11+ |
| pytest | ≥ 8.0 con plugins asyncio, cov |
| Docker | 24+ con docker-compose v2 |
| Streamlit | ≥ 1.33 (servicio `ui`) |
| SO | Linux (container) o macOS/Windows (local) |

Instrucciones de preparación:

```bash
# 1. Instalar dependencias
pip install -e ".[dev]"

# 2. Ejecutar suite completa
python -m pytest tests/ -v --cov=customer_retention --cov-report=term-missing

# 3. Verificar con Docker
docker compose --profile ci run --rm tests
```

---

## 3. Escenarios de Prueba

### 3.1 Pruebas Unitarias (tests/unit/)

| ID | Escenario | Comando | Resultado esperado |
|---|---|---|---|
| U-01 | Behavior Agent emite BehaviorReport con señales para cliente de alto riesgo | `pytest tests/unit/test_agents.py::test_behavior_agent_emits_report_with_signals -v` | risk_level ∈ {HIGH, CRITICAL}, signals no vacíos, trace registrada como "behavior-analyst" |
| U-02 | Value Agent asigna tier correcto | `pytest tests/unit/test_agents.py::test_value_agent_tiers_customer -v` | CLV ≥ 0, cost_of_loss ≥ 0, tier coherente con CLV |
| U-03 | Offer Agent marca oferta costosa como requires_approval | `pytest tests/unit/test_agents.py::test_offer_agent_flags_expensive_offer -v` | discount ≤ 40%, cost ≤ 500, requires_approval = (cost > 200) |
| U-04 | Reviewer aprueba artefactos consistentes | `pytest tests/unit/test_agents.py::test_reviewer_approves_consistent_artifacts -v` | status = APPROVE, todos los checks.passed = True |
| U-05 | Contratos Pydantic rechazan campos extra | `pytest tests/unit/test_contracts.py -v` | 8 tests pasan: validaciones de rangos, enums, inmutabilidad |
| U-06 | Reviewer rechaza violaciones duras | `pytest tests/unit/test_reviewer_reject.py -v` | status = REJECT para descuento > 40% o cost > 500 |

### 3.2 Pruebas de Contrato (tests/contract/)

| ID | Escenario | Comando | Resultado esperado |
|---|---|---|---|
| C-01 | Cada agente retorna su tipo declarado | `pytest tests/contract/test_artifact_contracts.py::test_agents_return_declared_types -v` | BehaviorReport, ValueReport, OfferProposal, ReviewResult son instancias correctas |
| C-02 | Artefactos son inmutables (frozen) | `pytest tests/contract/test_artifact_contracts.py::test_artifacts_are_immutable -v` | Asignar un campo lanza TypeError/AttributeError |

### 3.3 Pruebas de Integración (tests/integration/)

| ID | Escenario | Comando | Resultado esperado |
|---|---|---|---|
| I-01 | Workflow procesa todos los clientes del CSV de ejemplo | `pytest tests/integration/test_workflow.py::test_workflow_runs_all_agents_and_gates -v` | len(results) == len(records), 4 agentes en trazas, review.status válido |
| I-02 | Oferta costosa activa HITL y puede ser rechazada | `pytest tests/integration/test_workflow.py::test_expensive_offer_triggers_human_in_the_loop -v` | approval_status = REJECTED, action = MONITOR, offer.requires_approval = True |
| I-03 | Salida es serializable a JSON | `pytest tests/integration/test_workflow.py::test_workflow_output_is_json_serialisable -v` | as_dict() produce dict con "decision" y "traces" |

### 3.4 Prueba de CLI

| ID | Escenario | Comando | Resultado esperado |
|---|---|---|---|
| CLI-01 | Ejecutar workflow vía script | `python scripts/run_workflow.py --quiet` | JSON válido en stdout con "customers" y "results" |
| CLI-02 | Ejecutar workflow vía módulo CLI | `python -c "from customer_retention.cli import main; main(['--quiet'])"` | Salida JSON idéntica a CLI-01 |
| CLI-03 | Entry point genera reporte a archivo | `python scripts/run_workflow.py --out /tmp/report.json --quiet && cat /tmp/report.json \| python -m json.tool` | Archivo JSON bien formado |

### 3.5 Prueba de Docker

| ID | Escenario | Comando | Resultado esperado |
|---|---|---|---|
| D-01 | Build de imagen Docker | `docker build -t retention-workflow .` | Build exitoso, imagen < 500 MB |
| D-02 | Ejecutar CLI en Docker | `docker compose run --rm retention-workflow --quiet` | JSON con resultados en stdout |
| D-03 | Ejecutar tests en Docker | `docker compose --profile ci run --rm tests` | 19 tests pasan |
| D-04 | Levantar UI Streamlit | `docker compose up -d ui` + navegar a http://localhost:8501 | Dashboard carga sin errores |

### 3.6 Validación de Criterios de Rúbrica

| ID | Criterio (Peso) | Qué verificar | Cómo verificar |
|---|---|---|---|
| R-01 | Arquitectura multiagente real (25%) | Cada agente es una clase independiente con input/output tipado | Inspeccionar `agents/*.py`: 4 clases, cada una extiende `BaseAgent[TIn, TOut]` |
| R-02 | Supervisor, paralelismo, delegación (20%) | Supervisor no hace análisis; usa `asyncio.gather` | Leer `supervisor.py`: `_run_analyses_in_parallel` usa `asyncio.gather(behavior, clv)` |
| R-03 | Integración analítica (15%) | Modelo predictivo + CLV determinista + ofertas basadas en reglas | `model_adapter.py` (ChurnModelPort), `clv.py` (funciones puras), `offer_specialist.py` (catálogo) |
| R-04 | Quality gate, trazas, aprobación (15%) | Reviewer con 6 checks, TraceRecorder inyectado, HITL con 4 gateways | `reviewer.py` (checks), `tracing.py` (TraceSpan), `human_in_the_loop.py` (4 clases) |
| R-05 | Plugin, skill, instalación (15%) | manifest.json válido, SKILL.md presente, pyproject.toml con entry point callable | `manifest.json` (schema 1.0), `SKILL.md`, `pyproject.toml` → `cli:main` |
| R-06 | Docker, pruebas, demostración (10%) | Dockerfile multi-stage, compose con 3 servicios, 19 tests, cobertura ≥ 80% | `Dockerfile`, `compose.yml`, resultado de pytest |

---

## 4. Ejecución Rápida — Comando Único

```bash
# Ejecuta TODOS los tests con cobertura en un solo comando
python -m pytest tests/ -v --cov=customer_retention --cov-report=term-missing --tb=short
```

Resultado esperado: **19 passed**, cobertura ≥ 80%.

---

## 5. Ejecución del Workflow Completo (Demo)

```bash
# Paso 1: Ejecutar el workflow sobre el dataset de ejemplo
python scripts/run_workflow.py --out demo_report.json --quiet

# Paso 2: Verificar el reporte
python -c "
import json
with open('demo_report.json') as f:
    data = json.load(f)
print(f'Clientes procesados: {data[\"customers\"]}')
for r in data['results']:
    d = r['decision']
    print(f'  {d[\"customer_id\"]}: action={d[\"action\"]}, approval={d[\"approval_status\"]}')
    print(f'    traces: {[t[\"agent_name\"] for t in r[\"traces\"]]}')
"

# Paso 3: Verificar que cada cliente tiene 4+ trazas de agente
python -c "
import json
with open('demo_report.json') as f:
    data = json.load(f)
for r in data['results']:
    agents = {t['agent_name'] for t in r['traces']}
    required = {'behavior-analyst', 'value-analyst', 'offer-specialist', 'reviewer'}
    assert required <= agents, f'{r[\"decision\"][\"customer_id\"]}: missing {required - agents}'
print('PASS: todos los clientes tienen los 4 agentes en sus trazas')
"
```

---

## 6. Checklist Pre-Entrega

- [ ] `python -m pytest tests/ -v` → 19 passed
- [ ] `python scripts/run_workflow.py --quiet` → JSON válido
- [ ] `python -c "from customer_retention.cli import main"` → sin error
- [ ] `docker build -t retention-workflow .` → build OK
- [ ] `docker compose --profile ci run --rm tests` → 19 passed
- [ ] `.env.example` presente en raíz
- [ ] `.pre-commit-config.yaml` presente en raíz
- [ ] `manifest.json` schema 1.0 válido
- [ ] `SKILL.md` describe el plugin completo
- [ ] Cobertura ≥ 80%
