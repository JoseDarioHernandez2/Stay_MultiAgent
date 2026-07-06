"""Churn-mitigation recommendation engines (max 5 qualitative bullets).

Two implementations behind one protocol:

* :class:`RuleBasedRecommendationEngine` — deterministic, analyses the batch
  results and produces up to five prioritised, data-grounded recommendations.
  Always available, fully testable, no external dependencies.
* :class:`OllamaRecommendationEngine` — optional connector to a local Ollama
  server (e.g. ``qwen`` models). If the server is unreachable or returns an
  error, it degrades gracefully to the rule-based engine, so the dashboard
  never breaks.
"""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from collections import Counter
from typing import Protocol

from customer_retention.domain.contracts import WorkflowResult
from customer_retention.domain.enums import RiskLevel

_LOGGER = logging.getLogger(__name__)
_MAX_BULLETS = 5


class RecommendationEngine(Protocol):
    """Port for producing qualitative churn-mitigation recommendations."""

    name: str

    def recommend(self, results: list[WorkflowResult]) -> list[str]:
        """Return up to five recommendation bullets for the batch."""


class RuleBasedRecommendationEngine:
    """Deterministic insight engine grounded in the batch statistics."""

    name = "rule-based-insights-v1"

    # pylint: disable-next=too-many-locals
    def recommend(self, results: list[WorkflowResult]) -> list[str]:
        """Analyse the batch and produce prioritised recommendations.

        Args:
            results: The batch of workflow results.

        Returns:
            Up to five recommendation strings, most impactful first.
        """
        if not results:
            return ["Sin datos suficientes para generar recomendaciones."]

        candidates: list[tuple[float, str]] = []
        total = len(results)

        high_risk = [
            r
            for r in results
            if r.decision.behavior.risk_level in (RiskLevel.HIGH, RiskLevel.CRITICAL)
        ]
        if high_risk:
            share = 100.0 * len(high_risk) / total
            value_at_risk = sum(r.decision.value.cost_of_loss for r in high_risk)
            candidates.append(
                (
                    share,
                    f"El {share:.0f}% de la cartera ({len(high_risk)} clientes) "
                    f"está en riesgo alto o crítico, con "
                    f"${value_at_risk:,.0f} de valor en juego: priorizar "
                    "contacto proactivo en las próximas 72 horas.",
                )
            )

        signal_counter: Counter[str] = Counter()
        for result in results:
            for signal in result.decision.behavior.signals:
                signal_counter[signal.split(" recent")[0].split(" filed")[0]] += 1
        if signal_counter:
            top_signal, count = signal_counter.most_common(1)[0]
            if "support" in top_signal.lower() or "llamadas" in top_signal.lower():
                candidates.append(
                    (
                        90.0 * count / total,
                        f"La presión sobre soporte es la señal dominante "
                        f"({count} clientes): reforzar resolución en primer "
                        "contacto y abrir un canal preferente para cuentas "
                        "en riesgo.",
                    )
                )

        month_to_month = [
            r for r in results if any("month" in s for s in r.decision.behavior.signals)
        ]
        if month_to_month:
            share = 100.0 * len(month_to_month) / total
            candidates.append(
                (
                    share * 0.9,
                    f"El {share:.0f}% de los clientes en análisis tiene "
                    "contrato mes-a-mes: diseñar incentivos de migración a "
                    "planes anuales (descuento por permanencia, beneficios "
                    "escalonados).",
                )
            )

        inactive = [r for r in results if any("inactiv" in s for s in r.decision.behavior.signals)]
        if inactive:
            candidates.append(
                (
                    80.0 * len(inactive) / total + 10,
                    f"{len(inactive)} cuentas están inactivas con riesgo "
                    "elevado: lanzar campaña de reactivación antes de "
                    "ofrecer descuentos (menor costo, mayor señal de "
                    "intención).",
                )
            )

        complaints = [
            r
            for r in results
            if any("complaint" in s or "queja" in s for s in r.decision.behavior.signals)
        ]
        if complaints:
            candidates.append(
                (
                    75.0 * len(complaints) / total + 5,
                    f"{len(complaints)} clientes registran quejas formales: "
                    "cerrar el ciclo de cada queja con seguimiento "
                    "personalizado reduce el churn más que cualquier "
                    "descuento.",
                )
            )

        high_value_at_risk = [
            r for r in high_risk if r.decision.value.customer_lifetime_value >= 600
        ]
        if high_value_at_risk:
            candidates.append(
                (
                    70.0,
                    f"{len(high_value_at_risk)} clientes de alto valor están "
                    "en riesgo: asignar gestor dedicado; su retención "
                    "protege la mayor parte del CLV total en juego.",
                )
            )

        ranked = sorted(candidates, key=lambda c: c[0], reverse=True)
        return [text for _, text in ranked[:_MAX_BULLETS]]


class OllamaRecommendationEngine:
    """Optional LLM engine backed by a local Ollama server.

    Sends a compact batch summary to ``/api/generate`` and expects up to five
    bullet recommendations back. Any failure (server down, timeout, malformed
    response) falls back silently to :class:`RuleBasedRecommendationEngine`.
    """

    def __init__(
        self,
        model: str = "qwen2.5",
        base_url: str = "http://localhost:11434",
        timeout_s: float = 20.0,
    ) -> None:
        """Configure the Ollama connection.

        Args:
            model: Ollama model tag (e.g. ``qwen2.5``, ``llama3``).
            base_url: Base URL of the local Ollama server.
            timeout_s: Request timeout in seconds.
        """
        if not base_url.startswith(("http://", "https://")):
            raise ValueError("base_url must use http:// or https://")
        self._model = model
        self._url = f"{base_url.rstrip('/')}/api/generate"
        self._timeout = timeout_s
        self._fallback = RuleBasedRecommendationEngine()
        self.name = f"ollama:{model}"

    def recommend(self, results: list[WorkflowResult]) -> list[str]:
        """Ask the LLM for recommendations; fall back to rules on failure.

        Args:
            results: The batch of workflow results.

        Returns:
            Up to five recommendation strings.
        """
        prompt = self._build_prompt(results)
        try:
            payload = json.dumps({"model": self._model, "prompt": prompt, "stream": False}).encode(
                "utf-8"
            )
            request = urllib.request.Request(
                self._url,
                data=payload,
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(  # nosec B310 - scheme validated in __init__
                request, timeout=self._timeout
            ) as response:
                body = json.loads(response.read().decode("utf-8"))
            text = str(body.get("response", ""))
            bullets = [
                line.strip().lstrip("-•* ").strip()
                for line in text.splitlines()
                if line.strip().lstrip("-•* ").strip()
            ]
            if bullets:
                return bullets[:_MAX_BULLETS]
            _LOGGER.warning("ollama returned no bullets; using rule engine")
        except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
            _LOGGER.warning("ollama unavailable (%s); using rule engine", exc)
        return self._fallback.recommend(results)

    @staticmethod
    def _build_prompt(results: list[WorkflowResult]) -> str:
        """Compose a compact Spanish prompt from batch statistics."""
        total = len(results)
        high = sum(
            1
            for r in results
            if r.decision.behavior.risk_level in (RiskLevel.HIGH, RiskLevel.CRITICAL)
        )
        value_at_risk = sum(r.decision.value.cost_of_loss for r in results)
        return (
            "Eres un consultor de retención de clientes. Con base en este "
            f"resumen — {total} clientes analizados, {high} en riesgo "
            f"alto/crítico, ${value_at_risk:,.0f} de valor en riesgo — "
            "entrega MÁXIMO 5 recomendaciones accionables en español para "
            "mitigar el abandono. Responde solo con viñetas, una por línea."
        )


def build_recommendation_engine(
    use_ollama: bool = False, ollama_model: str = "qwen2.5"
) -> RecommendationEngine:
    """Factory returning the configured recommendation engine.

    Args:
        use_ollama: When ``True``, return the Ollama connector (with
            automatic rule-based fallback). Otherwise the rule engine.
        ollama_model: Ollama model tag to use when enabled.

    Returns:
        An object satisfying :class:`RecommendationEngine`.
    """
    if use_ollama:
        return OllamaRecommendationEngine(model=ollama_model)
    return RuleBasedRecommendationEngine()
