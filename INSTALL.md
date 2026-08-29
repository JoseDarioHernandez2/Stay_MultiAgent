# Guía de instalación y ejecución

## Requisitos previos

| Requisito | Versión mínima | Cómo verificar |
|-----------|---------------|----------------|
| Python    | 3.11          | `python3 --version` |
| pip       | 23+           | `pip --version` |
| Git       | cualquiera    | `git --version` |

> **¿Poetry?** El proyecto usa **setuptools estándar**, **no Poetry**.  
> No necesitas instalar Poetry. Usa `pip` directamente.

---

## Instalación paso a paso

### 1 — Clona o descomprime el proyecto

```bash
# Opción A: desde el repositorio Git
git clone https://github.com/tu-usuario/customer-retention-workflow.git
cd customer-retention-workflow

# Opción B: desde el ZIP descargado
unzip customer-retention-workflow.zip
cd customer-retention-workflow
```

### 2 — Crea un entorno virtual (recomendado)

```bash
python3 -m venv .venv

# Activar en Mac/Linux:
source .venv/bin/activate

# Activar en Windows (PowerShell):
.venv\Scripts\Activate.ps1

# Activar en Windows (cmd):
.venv\Scripts\activate.bat
```

Sabrás que está activo cuando el prompt muestre `(.venv)`.

### 3 — Instala las dependencias

```bash
# Instalación mínima (núcleo + UI Streamlit):
pip install -e ".[ui]"

# Instalación completa (incluye herramientas de dev, tests, linters):
pip install -e ".[dev]"
```

El flag `-e` instala el paquete en modo editable: los cambios en `src/` se reflejan sin reinstalar.

---

## Ejecución

### Opción A — Interfaz visual (Streamlit) ← recomendada

```bash
# Con Make (más simple):
make ui

# Sin Make (equivalente exacto):
PYTHONPATH=src streamlit run app/streamlit_app.py

# En Windows PowerShell:
$env:PYTHONPATH="src"; streamlit run app/streamlit_app.py
```

Abre el navegador en **http://localhost:8501**

**Flujo en la UI:**
1. Pulsa **"Ejecutar workflow"** en el panel lateral (carga el dataset de ejemplo incluido).
2. O sube tu propio `customers.csv` / `customers.xlsx` antes de ejecutar.
3. El sistema muestra KPIs, distribuciones, decisiones por cliente y trazas.
4. Si hay ofertas que superan el umbral de costo, aparece el **panel de aprobación humana (HITL)** — aprueba o rechaza con botones.
5. Descarga el reporte JSON completo al final.

---

### Opción B — Línea de comandos (CLI)

```bash
# Con Make:
make run          # genera datos y ejecuta el workflow

# Manual (sobre el dataset sintético de 1 000 clientes):
PYTHONPATH=src python3 scripts/run_workflow.py \
  --csv  data/customers.csv \
  --policy src/customer_retention/resources/politica_retencion.md \
  --out  report.json

# Con tus datos reales del challenge:
PYTHONPATH=src python3 scripts/run_workflow.py \
  --csv  challenges/session7/churn/customers.csv \
  --policy challenges/session7/churn/politica_retencion.md \
  --model challenges/session7/model_base.py \
  --out  report.json

# Con aprobaciones interactivas (HITL en consola):
PYTHONPATH=src python3 scripts/run_workflow.py \
  --csv  data/customers.csv \
  --policy src/customer_retention/resources/politica_retencion.md \
  --interactive
```

---

### Opción C — Generar dataset sintético propio

```bash
make data
# o manualmente:
PYTHONPATH=src python3 scripts/generate_synthetic_dataset.py \
  --rows 1000 --seed 42 --out-dir data --formats csv xlsx
```

Produce `data/customers.csv` y `data/customers.xlsx` (27 % churn, 1 000 clientes, señales con solapamiento realista).

---

## Ejecutar las pruebas

```bash
make test
# o manualmente:
PYTHONPATH=src pytest tests -q --cov=customer_retention --cov-report=term-missing
```

Resultado esperado: **37 passed, 93% coverage** en < 2 s.

---

## Verificar calidad del código

```bash
make lint      # corre black, isort, flake8, pylint, mypy, bandit
make format    # auto-formatea con black + isort
```

---

## Docker (alternativa sin instalar Python local)

```bash
# Construir imagen:
docker compose build

# Lanzar la UI en http://localhost:8501:
docker compose up ui

# Ejecutar el pipeline CLI:
docker compose run --rm retention-workflow

# Correr los tests:
docker compose --profile ci run --rm tests
```

---

## Solución de problemas frecuentes

| Síntoma | Causa probable | Solución |
|---------|---------------|----------|
| `ModuleNotFoundError: customer_retention` | PYTHONPATH no apunta a `src/` | Usa `PYTHONPATH=src` como prefijo o activa el entorno virtual tras `pip install -e .` |
| `streamlit: command not found` | Streamlit no instalado | `pip install -e ".[ui]"` |
| `pip install -e .` da error en Windows | PowerShell sin permisos | Ejecuta PowerShell como Administrador, o usa `--user` |
| La UI no abre el navegador | Servidor en headless | Abre manualmente http://localhost:8501 |
| El modelo base no carga | Ruta incorrecta o API diferente | Deja `--model` vacío → usa el modelo heurístico incluido |
| `openpyxl` no instalado al leer xlsx | Dependencia faltante | `pip install openpyxl` |

---

## Estructura de archivos relevante

```
customer-retention-workflow/
├── app/streamlit_app.py              ← UI (este es el archivo que lanzas)
├── scripts/run_workflow.py           ← CLI
├── scripts/generate_synthetic_dataset.py  ← generador de datos
├── src/customer_retention/           ← núcleo del paquete
│   └── resources/
│       ├── sample_customers.csv      ← dataset pequeño incluido (5 clientes)
│       └── politica_retencion.md     ← política de retención por defecto
├── data/
│   ├── customers.csv                 ← dataset sintético 1 000 clientes
│   └── customers.xlsx                ← mismo dataset en Excel
├── tests/                            ← suite pytest
├── Makefile                          ← atajos de comandos
├── pyproject.toml                    ← dependencias (NO es Poetry)
└── INSTALL.md                        ← esta guía
```
