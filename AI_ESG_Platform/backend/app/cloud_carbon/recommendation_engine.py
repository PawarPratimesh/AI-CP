"""AI-Powered and Rule-Based Infrastructure Optimization Recommendation Engine.

Provides:
1. AI-powered infrastructure anomaly explanations using Gemini (with technical attribution).
2. Practical, evidence-based optimization recommendations (Rightsizing, Scaling, Memory, Storage, Decarbonization).
3. Robust rule-based fallback when Gemini API is unavailable or returns invalid output.
4. Strict metrics immutability: underlying measurements and calculations are never mutated by AI outputs.
"""

from __future__ import annotations

import json
import logging
import os
import re
import uuid
from typing import Any, Optional

from app.cloud_carbon.schemas import (
    AnomalyExplanationItem,
    CloudCarbonRecommendationsResponse,
    OptimizationRecommendationItem,
)

logger = logging.getLogger(__name__)


def _safe_float(val: Any) -> float | None:
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return float(val)
    if isinstance(val, str):
        cleaned = re.sub(r"[^\d.-]", "", val)
        try:
            return float(cleaned)
        except Exception:
            return None
    return None


def _trim_to_sentences(text: str, max_sentences: int = 2, max_words: int = 30) -> str:
    """Trim text to at most max_sentences and max_words without cutting decimals or abbreviations."""
    if not text:
        return ""
    text = re.sub(r"\s+", " ", text).strip()
    # Split only on sentence-ending punctuation preceded by letters, closing quotes/parens, or percent signs,
    # followed by whitespace + capital letter or end of string. This preserves decimals like 3.8% and 0.379 kg CO₂e/kWh.
    tokens = re.split(r"(?<=[a-zA-Z%)\'\"])([.!?])(?=\s+[A-Z]|\s*$)", text)
    sentences = []
    current = ""
    for t in tokens:
        if t in (".", "!", "?"):
            current += t
            sentences.append(current.strip())
            current = ""
        else:
            current += t
    if current.strip():
        sentences.append(current.strip())

    clean_sentences = [s for s in sentences if s]
    selected = " ".join(clean_sentences[:max_sentences]).strip()
    if not selected:
        selected = text

    words = selected.split()
    if len(words) > max_words:
        truncated = " ".join(words[:max_words]).rstrip(",;:-")
        if not truncated.endswith((".", "!", "?")):
            truncated += "."
        return truncated
    if selected and not selected.endswith((".", "!", "?")):
        selected += "."
    return selected


def _trim_title(title: str, max_words: int = 8) -> str:
    """Trim title to at most max_words."""
    if not title:
        return "Infrastructure Recommendation"
    words = title.strip().split()
    if len(words) > max_words:
        return " ".join(words[:max_words])
    return title.strip()


def sanitize_and_validate_recommendation(r: OptimizationRecommendationItem) -> OptimizationRecommendationItem:
    """Validate and sanitize every field of a recommendation for factual accuracy and conciseness."""
    # 1. Title validation
    r.title = _trim_title(r.title, max_words=8)

    # 2. Target resource validation
    if not r.target_resource or r.target_resource.lower() in ("null", "none", "unknown"):
        r.target_resource = "Fleet-wide"

    # 3. Issue (observation) validation
    obs = r.observation or ""
    # Fix incomplete fragments such as standalone "8%" or text lacking metric context
    if re.match(r"^\s*\(?\d+(\.\d+)?%\)?\.?\s*$", obs) or len(obs.split()) < 4:
        obs = f"Resource {r.target_resource} consistently operates at very low average CPU utilization."

    # Remove contradictory statements claiming low/zero CPU contributes significant carbon
    if re.search(r"\b0%\b.*\bsignificant carbon\b", obs, re.IGNORECASE) or re.search(r"\bcontributing significant carbon\b", obs, re.IGNORECASE):
        obs = re.sub(r",?\s*contributing significant carbon[^\.]*", "", obs, flags=re.IGNORECASE).strip()
        if not obs.endswith("."):
            obs += "."

    # Preserve correct carbon intensity notation (e.g. 379 kg/kWh -> 0.379 kg CO₂e/kWh)
    obs = re.sub(r"\b(\d{3})\s*kg(?:CO2e?)?/(?:kwh|kWh)\b", r"0.\1 kg CO₂e/kWh", obs)
    obs = re.sub(r"\b(0\.\d+)\s*kg\s*/\s*kWh\b", r"\1 kg CO₂e/kWh", obs)
    obs = re.sub(r"kgCO2e", "kg CO₂e", obs)

    r.observation = _trim_to_sentences(obs, max_sentences=2, max_words=25)

    # 4. Action validation
    act = r.action or ""
    # For underutilized instance downsizing, ensure standby/failover/peak-demand is advised
    is_underutil = any(k in r.title.lower() or k in r.category.lower() for k in ["underutil", "downsize", "rightsize"])
    if is_underutil and not any(k in act.lower() for k in ["standby", "failover", "peak"]):
        act = "Verify standby, failover and peak-demand requirements before rightsizing this resource or consolidating idle workloads."

    # Remove unsupported specific savings claims (e.g. "Save 48%", "Save 32 kg")
    act = re.sub(r"\(Save\s+[^)]+\)", "", act).strip()
    act = re.sub(r"\bup to \d+%\s*(?:carbon|energy)?\s*reduction\b", "potential carbon reduction", act, flags=re.IGNORECASE)

    r.action = _trim_to_sentences(act, max_sentences=2, max_words=30)

    # 5. Expected benefit normalization
    benefit = str(r.expected_benefit or "Medium").capitalize()
    if benefit not in ("High", "Medium", "Low"):
        benefit = "Medium"
    r.expected_benefit = benefit

    return r


def prepare_infrastructure_summary(
    records: list[Any],
    anomaly_detection: dict[str, Any],
    emissions_estimation: dict[str, Any],
) -> dict[str, Any]:
    """Compile a compact, high-signal statistical summary suitable for Gemini context."""
    # Normalize records to dictionaries
    dict_records = []
    for r in records:
        if hasattr(r, "model_dump"):
            dict_records.append(r.model_dump())
        elif isinstance(r, dict):
            dict_records.append(r)
        else:
            dict_records.append(dict(r))

    total_records = len(dict_records)
    resources_map: dict[str, list[dict[str, Any]]] = {}

    for r in dict_records:
        rid = r.get("resource_id", "unknown")
        resources_map.setdefault(rid, []).append(r)

    resource_stats: list[dict[str, Any]] = []
    for rid, r_recs in resources_map.items():
        cpus = [float(x["cpu_utilization_pct"]) for x in r_recs if x.get("cpu_utilization_pct") is not None]
        mems = [float(x["memory_utilization_pct"]) for x in r_recs if x.get("memory_utilization_pct") is not None]
        net_ins = [float(x["network_in"]) for x in r_recs if x.get("network_in") is not None]
        net_outs = [float(x["network_out"]) for x in r_recs if x.get("network_out") is not None]
        stor_used = [float(x["storage_used"]) for x in r_recs if x.get("storage_used") is not None]
        stor_caps = [float(x["storage_capacity"]) for x in r_recs if x.get("storage_capacity") is not None]

        # Match resource emission info from breakdown if available
        breakdowns = emissions_estimation.get("resources_breakdown", [])
        rb = next((b for b in breakdowns if b.get("resource_id") == rid), {})

        resource_stats.append({
            "resource_id": rid,
            "provider": r_recs[0].get("provider") or rb.get("provider", "Unknown"),
            "region": r_recs[0].get("region") or rb.get("region", "Unknown"),
            "observation_count": len(r_recs),
            "avg_cpu_pct": round(sum(cpus) / len(cpus), 2) if cpus else None,
            "min_cpu_pct": round(min(cpus), 2) if cpus else None,
            "max_cpu_pct": round(max(cpus), 2) if cpus else None,
            "avg_memory_pct": round(sum(mems) / len(mems), 2) if mems else None,
            "max_memory_pct": round(max(mems), 2) if mems else None,
            "avg_network_in": round(sum(net_ins) / len(net_ins), 1) if net_ins else None,
            "avg_network_out": round(sum(net_outs) / len(net_outs), 1) if net_outs else None,
            "storage_used": round(sum(stor_used) / len(stor_used), 2) if stor_used else None,
            "storage_capacity": round(sum(stor_caps) / len(stor_caps), 2) if stor_caps else None,
            "estimated_energy_kwh": rb.get("estimated_energy_kwh"),
            "estimated_carbon_kg": rb.get("estimated_carbon_kg"),
            "grid_intensity_factor_kg_per_kwh": rb.get("grid_intensity_factor_kg_per_kwh"),
            "carbon_status": rb.get("carbon_status"),
        })

    # Summary of detected anomalies
    anomalies_list = anomaly_detection.get("anomalies", [])
    anomaly_summary = []
    for a in anomalies_list[:12]:  # Send at most top 12 anomalies to stay concise
        anomaly_summary.append({
            "resource_id": a.get("resource_id"),
            "timestamp": a.get("timestamp"),
            "anomaly_score": a.get("anomaly_score"),
            "contributing_metrics": a.get("contributing_metrics", []),
            "raw_metrics": a.get("raw_metrics", {}),
        })

    all_cpus = [float(r["cpu_utilization_pct"]) for r in dict_records if r.get("cpu_utilization_pct") is not None]
    fleet_avg_cpu = round(sum(all_cpus) / len(all_cpus), 2) if all_cpus else None

    return {
        "fleet_overview": {
            "total_records": total_records,
            "distinct_resources": len(resources_map),
            "fleet_avg_cpu_pct": fleet_avg_cpu,
            "total_energy_kwh": emissions_estimation.get("total_energy_kwh"),
            "total_carbon_kgco2e": emissions_estimation.get("total_carbon_kgco2e"),
            "regions_detected": emissions_estimation.get("regions_detected", []),
            "anomalies_detected": anomaly_detection.get("anomalies_detected", 0),
            "anomaly_percentage": anomaly_detection.get("anomaly_percentage", 0.0),
        },
        "anomalies": anomaly_summary,
        "resources": resource_stats,
    }


def generate_rule_based_insights(
    upload_id: str,
    summary_data: dict[str, Any],
    warning_or_limitation: Optional[str] = None,
) -> CloudCarbonRecommendationsResponse:
    """Generate deterministic, rule-based anomaly explanations and practical recommendations."""
    fleet = summary_data.get("fleet_overview", {})
    anomalies_input = summary_data.get("anomalies", [])
    resources = summary_data.get("resources", [])

    # 1. Anomaly Explanations
    explanations: list[AnomalyExplanationItem] = []
    for a in anomalies_input:
        rid = a.get("resource_id", "unknown")
        ts = a.get("timestamp", "unknown")
        raw = a.get("raw_metrics", {})
        contrib = a.get("contributing_metrics", [])

        # Find resource specific baselines
        r_stat = next((r for r in resources if r["resource_id"] == rid), {})
        baseline_cpu = r_stat.get("avg_cpu_pct")
        baseline_mem = r_stat.get("avg_memory_pct")
        baseline_net = r_stat.get("avg_network_out") or r_stat.get("avg_network_in")
        baseline_storage = r_stat.get("storage_capacity")

        # Determine primary unusual dimension and set matching baseline context
        if any("cpu" in c.lower() for c in contrib) or (raw.get("cpu_utilization_pct") is not None and baseline_cpu and raw["cpu_utilization_pct"] > baseline_cpu * 1.5):
            metric_name = "CPU Utilization"
            obs_val = raw.get("cpu_utilization_pct")
            base_ctx = f"Resource average CPU baseline is {baseline_cpu}%." if baseline_cpu is not None else "Historical CPU baseline range."
            explanation = (
                f"Observed CPU utilization on {rid} spiked to {obs_val}%, "
                f"which is elevated compared to its historical baseline ({baseline_cpu}%)."
            )
            causes = (
                "Potential hypotheses to investigate: unoptimized compute-intensive queries, rogue background daemon threads, "
                "or sudden traffic surges without auto-scale headroom."
            )
            impact = "Elevated risk of service response latency spikes, request timeouts, and potential CPU throttling."
            steps = "Inspect running operating system processes (top/htop), thread dumps, and application request logs around the observation timestamp."

        elif any("memory" in c.lower() for c in contrib) or (raw.get("memory_utilization_pct") is not None and baseline_mem and raw["memory_utilization_pct"] > baseline_mem * 1.3):
            metric_name = "Memory Utilization"
            obs_val = raw.get("memory_utilization_pct")
            base_ctx = f"Resource average memory baseline is {baseline_mem}%." if baseline_mem is not None else "Standard memory allocation baseline."
            explanation = (
                f"Memory allocation on {rid} reached {obs_val}%, elevated relative to historical average ({baseline_mem}%)."
            )
            causes = (
                "Potential hypotheses to investigate: uncollected garbage collection backlog, application memory leak, "
                "or oversized in-memory caching structures."
            )
            impact = "Risk of kernel Out-Of-Memory (OOM) process termination, swap paging churn, or system crash."
            steps = "Profile application heap allocations, check JVM/container memory caps, and verify cache eviction policies."

        elif any("network" in c.lower() for c in contrib) or raw.get("network_out") is not None:
            metric_name = "Network I/O Throughput"
            obs_val = raw.get("network_out") or raw.get("network_in")
            base_ctx = f"Resource average network throughput baseline is {baseline_net:,.0f} bytes." if baseline_net is not None else "Typical network throughput baseline."
            explanation = (
                f"Network throughput on {rid} exhibited an abnormal transfer surge ({obs_val:,.0f} bytes)."
            )
            causes = (
                "Potential hypotheses to investigate: uncompressed database exports, bulk data migrations, "
                "or unexpected external API scraping."
            )
            impact = "Potential bandwidth saturation on network interfaces and unexpected egress bandwidth cost."
            steps = "Inspect active TCP socket connections, verify scheduled data pipelines, and audit outbound API calls."

        else:
            metric_name = "Multi-Metric Interaction"
            obs_val = a.get("anomaly_score")
            base_ctx = "Multi-dimensional statistical baseline established by Isolation Forest model."
            explanation = (
                f"Isolation Forest identified a statistical outlier on {rid} (anomaly score {obs_val:.2f}) "
                "across combined telemetry dimensions."
            )
            causes = "Potential hypotheses to investigate: simultaneous deviation in multiple operational parameters inconsistent with standard fleet behavior."
            impact = "Unpredictable service behavior or impending resource exhaustion."
            steps = "Review system health metrics, hardware event logs, and concurrent workload schedules."

        explanations.append(
            AnomalyExplanationItem(
                resource_id=rid,
                timestamp=ts,
                metric=metric_name,
                observed_value=obs_val,
                baseline_context=base_ctx,
                explanation=explanation,
                possible_causes=causes,
                operational_impact=impact,
                investigation_steps=steps,
            )
        )

    # 2. Recommendations (3–5 practical opportunities, strictly concise)
    recommendations: list[OptimizationRecommendationItem] = []

    # Check A: Underutilized resources (< 15% avg CPU)
    underutilized = [r for r in resources if r.get("avg_cpu_pct") is not None and r["avg_cpu_pct"] < 15.0]
    if underutilized:
        top_u = min(underutilized, key=lambda x: x["avg_cpu_pct"])
        recommendations.append(
            OptimizationRecommendationItem(
                title=_trim_title(f"Review Underutilized Instance ({top_u['resource_id']})", 8),
                category="Compute Rightsizing",
                target_resource=top_u["resource_id"],
                observation=_trim_to_sentences(
                    f"Resource {top_u['resource_id']} consistently operates at very low average CPU utilization of {top_u['avg_cpu_pct']}%.",
                    max_sentences=2, max_words=25
                ),
                action=_trim_to_sentences(
                    "Verify standby, failover and peak-demand requirements before rightsizing this resource or consolidating idle workloads.",
                    max_sentences=2, max_words=30
                ),
                reason="Over-provisioned idle instances consume baseline power without proportional workload throughput.",
                expected_benefit="High" if top_u["avg_cpu_pct"] < 8.0 else "Medium",
                evidence=f"Average CPU utilization: {top_u['avg_cpu_pct']}% across {top_u['observation_count']} recorded periods.",
                estimated_impact="Reduces idle electricity consumption and Scope 2 compute allocation overhead.",
            )
        )

    # Check B: Network Traffic Spikes / Surge
    net_candidates = [
        r for r in resources
        if (r.get("avg_network_in") and r["avg_network_in"] > 50000000)
        or (r.get("avg_network_out") and r["avg_network_out"] > 50000000)
        or any(a.get("resource_id") == r["resource_id"] and any("network" in c.lower() for c in a.get("contributing_metrics", [])) for a in anomalies_input)
    ]
    if net_candidates:
        top_net = max(net_candidates, key=lambda x: max(x.get("avg_network_in") or 0, x.get("avg_network_out") or 0))
        recommendations.append(
            OptimizationRecommendationItem(
                title=_trim_title(f"Investigate Network Traffic Spikes ({top_net['resource_id']})", 8),
                category="Workload Optimization",
                target_resource=top_net["resource_id"],
                observation=_trim_to_sentences(
                    f"Unusually high network traffic was detected across recorded observation intervals for {top_net['resource_id']}.",
                    max_sentences=2, max_words=25
                ),
                action=_trim_to_sentences(
                    "Inspect network access logs and application activity to identify the traffic source and determine whether the increase is legitimate.",
                    max_sentences=2, max_words=30
                ),
                reason="Surge in network transfer risks interface bandwidth saturation and elevated egress footprints.",
                expected_benefit="High",
                evidence=f"Observed elevated network throughput on {top_net['resource_id']}.",
                estimated_impact="Stabilizes network bandwidth consumption and prevents unexpected data egress overhead.",
            )
        )

    # Check C: High CPU utilization (> 70% avg or peak > 85%)
    high_cpu = [r for r in resources if (r.get("avg_cpu_pct") is not None and r["avg_cpu_pct"] > 70.0) or (r.get("max_cpu_pct") is not None and r["max_cpu_pct"] > 85.0)]
    if high_cpu:
        top_h = max(high_cpu, key=lambda x: x.get("max_cpu_pct") or 0.0)
        recommendations.append(
            OptimizationRecommendationItem(
                title=_trim_title(f"Mitigate Peak Compute Saturation ({top_h['resource_id']})", 8),
                category="Workload Optimization",
                target_resource=top_h["resource_id"],
                observation=_trim_to_sentences(
                    f"Resource {top_h['resource_id']} reached peak CPU utilization of {top_h['max_cpu_pct']}%, risking performance saturation.",
                    max_sentences=2, max_words=25
                ),
                action=_trim_to_sentences(
                    "Implement autoscaling policies and profile CPU-bound routines to alleviate performance bottlenecks during peak demand.",
                    max_sentences=2, max_words=30
                ),
                reason="Operating near compute saturation increases request latency and prevents thermal energy efficiency.",
                expected_benefit="High",
                evidence=f"Peak CPU: {top_h['max_cpu_pct']}%, Average: {top_h['avg_cpu_pct']}%.",
                estimated_impact="Improves system resilience, prevents SLA breaches, and avoids compute throttling.",
            )
        )

    # Check D: Memory Pressure (> 75% memory)
    high_mem = [r for r in resources if r.get("avg_memory_pct") is not None and r["avg_memory_pct"] > 75.0]
    if high_mem:
        top_m = max(high_mem, key=lambda x: x["avg_memory_pct"])
        recommendations.append(
            OptimizationRecommendationItem(
                title=_trim_title(f"Tune Memory Allocation ({top_m['resource_id']})", 8),
                category="Memory Tuning",
                target_resource=top_m["resource_id"],
                observation=_trim_to_sentences(
                    f"The instance operates under sustained memory pressure with average allocation at {top_m['avg_memory_pct']}%.",
                    max_sentences=2, max_words=25
                ),
                action=_trim_to_sentences(
                    "Audit process heap limits, configure cache TTLs, and evaluate memory-optimized instance types if allocations are legitimate.",
                    max_sentences=2, max_words=30
                ),
                reason="High memory pressure increases garbage collection overhead and risks kernel out-of-memory process termination.",
                expected_benefit="Medium",
                evidence=f"Average memory: {top_m['avg_memory_pct']}%, peak: {top_m['max_memory_pct']}%.",
                estimated_impact="Stabilizes application latency and prevents unexpected container restarts.",
            )
        )

    # Check E: Storage lifecycle (> 70% storage used or large storage)
    storage_candidates = [r for r in resources if r.get("storage_used") is not None and r.get("storage_capacity") is not None and r["storage_capacity"] > 0]
    high_storage = [r for r in storage_candidates if (r["storage_used"] / r["storage_capacity"]) > 0.70]
    if high_storage:
        top_s = max(high_storage, key=lambda x: (x["storage_used"] / x["storage_capacity"]))
        pct_used = round((top_s["storage_used"] / top_s["storage_capacity"]) * 100, 1)
        recommendations.append(
            OptimizationRecommendationItem(
                title=_trim_title(f"Configure Storage Lifecycle Archival ({top_s['resource_id']})", 8),
                category="Storage Lifecycle",
                target_resource=top_s["resource_id"],
                observation=_trim_to_sentences(
                    f"Storage volume has reached {pct_used}% capacity across active disk allocations.",
                    max_sentences=2, max_words=25
                ),
                action=_trim_to_sentences(
                    "Configure automated lifecycle policies to transition inactive files and snapshots older than 30 days to archive storage.",
                    max_sentences=2, max_words=30
                ),
                reason="Retaining uncompressed cold data on primary storage increases active disk power and capacity overhead.",
                expected_benefit="Medium",
                evidence=f"Storage at {pct_used}% capacity ({top_s['storage_used']} of {top_s['storage_capacity']} units).",
                estimated_impact="Reduces primary storage capacity strain and lowers operational storage footprints.",
            )
        )

    # Check F: Regional Grid Carbon Intensity (Decarbonization)
    high_carbon_regions = [r for r in resources if r.get("grid_intensity_factor_kg_per_kwh") is not None and r["grid_intensity_factor_kg_per_kwh"] > 0.35]
    if high_carbon_regions:
        top_c = max(high_carbon_regions, key=lambda x: x["grid_intensity_factor_kg_per_kwh"])
        grid_val = top_c["grid_intensity_factor_kg_per_kwh"]
        grid_str = f"{grid_val:.3f} kg CO₂e/kWh"
        recommendations.append(
            OptimizationRecommendationItem(
                title="Evaluate Regional Decarbonization",
                category="Decarbonization",
                target_resource="Fleet-wide",
                observation=_trim_to_sentences(
                    f"Resources operate in region '{top_c['region']}' with an elevated grid carbon intensity of {grid_str}.",
                    max_sentences=2, max_words=25
                ),
                action=_trim_to_sentences(
                    "Evaluate lower-carbon deployment locations while considering latency, data residency and compliance requirements.",
                    max_sentences=2, max_words=30
                ),
                reason="Shifting non-critical workloads to cleaner regional grids reduces Scope 2 location-based operational emissions.",
                expected_benefit="Medium",
                evidence=f"Host region: {top_c['region']} ({grid_str}).",
                estimated_impact="Potential Scope 2 carbon reduction subject to latency, GDPR, and data residency validation.",
            )
        )

    # Fallback to ensure at least 3 recommendations if fleet was completely balanced
    if len(recommendations) < 3:
        recommendations.append(
            OptimizationRecommendationItem(
                title="Automate Off-Hours Power Schedules",
                category="Decarbonization",
                target_resource="Fleet-wide",
                observation=_trim_to_sentences(
                    "Non-production resources maintain continuous power allocation during idle off-hours.",
                    max_sentences=2, max_words=25
                ),
                action=_trim_to_sentences(
                    "Deploy automated shutdown schedules for staging and test environments outside core business hours.",
                    max_sentences=2, max_words=30
                ),
                reason="Idle off-hours power consumption generates Scope 2 emissions without business utility.",
                expected_benefit="Medium",
                evidence=f"Fleet total modeled energy: {fleet.get('total_energy_kwh', 0.0)} kWh.",
                estimated_impact="Eliminates idle off-hours electricity consumption and associated Scope 2 emissions.",
            )
        )
    if len(recommendations) < 3:
        recommendations.append(
            OptimizationRecommendationItem(
                title="Optimize Network Transmission Payloads",
                category="Workload Optimization",
                target_resource="Fleet-wide",
                observation=_trim_to_sentences(
                    "Inter-service communication generates continuous uncompressed telemetry and network transfer overhead.",
                    max_sentences=2, max_words=25
                ),
                action=_trim_to_sentences(
                    "Enable transport compression and evaluate binary protocols like gRPC to reduce transfer energy.",
                    max_sentences=2, max_words=30
                ),
                reason="Lower transfer payload reduces CPU serialization cycles and transit network energy.",
                expected_benefit="Low",
                evidence=f"Fleet observation count: {fleet.get('total_records', 0)} metric events.",
                estimated_impact="Reduces network transmission overhead and CPU serialization cycles.",
            )
        )
    if len(recommendations) < 3:
        recommendations.append(
            OptimizationRecommendationItem(
                title="Implement Carbon-Aware Task Scheduling",
                category="Decarbonization",
                target_resource="Fleet-wide",
                observation=_trim_to_sentences(
                    "Workloads currently execute without alignment to regional low-carbon energy windows.",
                    max_sentences=2, max_words=25
                ),
                action=_trim_to_sentences(
                    "Shift non-urgent batch computations to operational windows with higher clean energy availability.",
                    max_sentences=2, max_words=30
                ),
                reason="Aligning compute demand with renewable energy availability reduces operational carbon intensity.",
                expected_benefit="Low",
                evidence=f"Fleet total records: {fleet.get('total_records', 0)} observations.",
                estimated_impact="Reduces marginal grid emissions during peak fossil generation periods.",
            )
        )

    # Sanitize and validate every recommendation
    recommendations = [sanitize_and_validate_recommendation(r) for r in recommendations][:5]

    # Executive summary
    anomaly_count = len(explanations)
    summary_text = (
        f"Analyzed {fleet.get('total_records', 0)} telemetry records across {fleet.get('distinct_resources', 0)} resources. "
        f"Identified {anomaly_count} operational {'anomaly' if anomaly_count == 1 else 'anomalies'} and synthesized "
        f"{len(recommendations)} prioritized optimization recommendations focused on compute efficiency and decarbonization."
    )

    return CloudCarbonRecommendationsResponse(
        upload_id=upload_id,
        status="SUCCESS" if recommendations else "NO_OPPORTUNITIES",
        generation_method="RULE_BASED",
        summary=summary_text,
        anomaly_explanations=explanations,
        recommendations=recommendations,
        warning_or_limitation=warning_or_limitation,
    )


def generate_cloud_carbon_insights(
    upload_id: str,
    session: dict[str, Any],
    anomaly_detection: dict[str, Any],
    emissions_estimation: dict[str, Any],
    force_rule_based: bool = False,
) -> CloudCarbonRecommendationsResponse:
    """Orchestrate AI-driven recommendation generation with automatic rule-based fallback."""
    records = session.get("preprocessed_result", {}).get("accepted", [])
    if not records:
        return CloudCarbonRecommendationsResponse(
            upload_id=upload_id,
            status="NO_OPPORTUNITIES",
            generation_method="RULE_BASED",
            summary="No accepted infrastructure records found in this upload session.",
            anomaly_explanations=[],
            recommendations=[],
            warning_or_limitation="Session contains zero preprocessed records.",
        )

    summary_data = prepare_infrastructure_summary(records, anomaly_detection, emissions_estimation)

    # Check if rule-based analysis is forced or Gemini is disabled / in testing without API key
    is_testing = os.getenv("TESTING") == "1"
    has_api_key = bool(os.getenv("GEMINI_API_KEY"))

    if force_rule_based or (is_testing and not has_api_key):
        return generate_rule_based_insights(
            upload_id=upload_id,
            summary_data=summary_data,
            warning_or_limitation="Generated using rule-based analysis (testing mode / rule-based forced).",
        )

    # Attempt Gemini generation
    try:
        from app.services.llm import generate_infrastructure_recommendations

        summary_json = json.dumps(summary_data, indent=2, default=str)
        response_text = generate_infrastructure_recommendations(summary_json)

        # Strip markdown fences if present
        text = response_text.strip()
        if text.startswith("```json"):
            text = text[7:]
        if text.startswith("```"):
            text = text[3:]
        if text.endswith("```"):
            text = text[:-3]

        parsed = json.loads(text.strip())
        if not isinstance(parsed, dict):
            raise ValueError("Gemini response is not a JSON object.")

        # Parse anomaly explanations
        raw_exps = parsed.get("anomaly_explanations", [])
        anomalies_input = summary_data.get("anomalies", [])

        # Constraint check: if no anomalies in input, explanations must be empty
        explanations: list[AnomalyExplanationItem] = []
        if anomalies_input and isinstance(raw_exps, list):
            for e in raw_exps:
                if isinstance(e, dict) and e.get("resource_id"):
                    explanations.append(
                        AnomalyExplanationItem(
                            resource_id=str(e.get("resource_id")),
                            timestamp=str(e.get("timestamp", "")),
                            metric=str(e.get("metric", "General")),
                            observed_value=_safe_float(e.get("observed_value")),
                            baseline_context=_trim_to_sentences(str(e.get("baseline_context") or "Standard baseline"), max_sentences=1, max_words=15),
                            explanation=_trim_to_sentences(str(e.get("explanation", "")), max_sentences=2, max_words=25),
                            possible_causes=_trim_to_sentences(str(e.get("possible_causes", "")), max_sentences=1, max_words=20),
                            operational_impact=_trim_to_sentences(str(e.get("operational_impact", "")), max_sentences=1, max_words=20),
                            investigation_steps=_trim_to_sentences(str(e.get("investigation_steps", "")), max_sentences=1, max_words=20),
                        )
                    )

        # Parse recommendations (strictly concise format: Title <= 8 words, Issue <= 25 words, Action <= 30 words)
        raw_recs = parsed.get("recommendations", [])
        recommendations: list[OptimizationRecommendationItem] = []
        if isinstance(raw_recs, list):
            for r in raw_recs:
                if isinstance(r, dict) and r.get("title") and r.get("action"):
                    benefit = str(r.get("expected_benefit", "Medium")).capitalize()
                    if benefit not in ("High", "Medium", "Low"):
                        benefit = "Medium"
                    recommendations.append(
                        OptimizationRecommendationItem(
                            id=str(uuid.uuid4())[:8],
                            title=_trim_title(str(r.get("title")), max_words=8),
                            category=str(r.get("category", "Workload Optimization")),
                            target_resource=str(r.get("target_resource", "Fleet-wide")),
                            observation=_trim_to_sentences(str(r.get("observation", "")), max_sentences=2, max_words=25),
                            action=_trim_to_sentences(str(r.get("action", "")), max_sentences=2, max_words=30),
                            reason=_trim_to_sentences(str(r.get("reason", "")), max_sentences=1, max_words=20),
                            expected_benefit=benefit,
                            evidence=_trim_to_sentences(str(r.get("evidence", "")), max_sentences=1, max_words=15),
                            estimated_impact=str(r.get("estimated_impact")) if r.get("estimated_impact") else None,
                        )
                    )

        # Validate minimum recommendations
        if len(recommendations) < 2:
            raise ValueError("Gemini returned insufficient recommendations; triggering fallback.")

        # Enforce 3 to 5 recommendation limit and validate all fields
        recommendations = [sanitize_and_validate_recommendation(r) for r in recommendations][:5]

        summary_text = str(parsed.get("summary") or (
            f"Gemini analyzed {summary_data['fleet_overview']['total_records']} telemetry observations across "
            f"{summary_data['fleet_overview']['distinct_resources']} resources."
        ))

        return CloudCarbonRecommendationsResponse(
            upload_id=upload_id,
            status="SUCCESS",
            generation_method="GEMINI",
            summary=summary_text,
            anomaly_explanations=explanations,
            recommendations=recommendations,
            warning_or_limitation=None,
        )

    except Exception as exc:
        logger.warning("Gemini recommendation generation failed (%s); reverting to rule-based analysis.", exc)
        return generate_rule_based_insights(
            upload_id=upload_id,
            summary_data=summary_data,
            warning_or_limitation=f"Gemini AI processing unavailable or timed out ({type(exc).__name__}); generated using rule-based analysis.",
        )
