# src/queries/query_logger.py
import json
import os
from datetime import datetime
from typing import Dict, Any, Optional, List
import logging
from pathlib import Path
import jsonlines
from collections import defaultdict

logger = logging.getLogger(__name__)

class QueryLogger:
    """
    Enhanced query logger that provides comprehensive logging capabilities for SymRAG.
    """

    def __init__(self,
                 log_dir: str = "logs",
                 main_log_file: str = "query_log.json",
                 performance_log_file: str = "performance_metrics.jsonl",
                 error_log_file: str = "error_log.json",
                 max_log_size: int = 10_000):
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.main_log_path = self.log_dir / main_log_file
        self.performance_log_path = self.log_dir / performance_log_file
        self.error_log_path = self.log_dir / error_log_file
        self.max_log_size = max_log_size
        self.performance_stats = defaultdict(list)
        self.logger = logger
        self.logger.setLevel(logging.INFO)
        self._initialize_log_files()
        self.logger.info("QueryLogger initialized successfully")

    def _initialize_log_files(self):
        if not self.main_log_path.exists():
            with open(self.main_log_path, 'w', encoding='utf-8') as f:
                json.dump([], f)
                f.flush()
        if not self.performance_log_path.exists():
            with jsonlines.open(self.performance_log_path, mode='w') as writer:
                writer.write({"timestamp": datetime.now().isoformat(), "log_initialized": True, "version": "2.0"})
        if not self.error_log_path.exists():
            with open(self.error_log_path, 'w', encoding='utf-8') as f:
                json.dump({"error_counts": {}, "error_logs": []}, f)
                f.flush()

    def log_query(self, query: str, result: Any, source: str, complexity: Optional[float] = None,
                  resource_usage: Optional[Dict] = None, reasoning_path: Optional[Dict] = None,
                  processing_time: Optional[float] = None, metadata: Optional[Dict] = None) -> None:
        timestamp = datetime.now().isoformat()
        log_entry = {"timestamp": timestamp, "query": query, "result": result, "source": source, "complexity": complexity,
                     "processing_time": processing_time, "success": self._determine_success(result)}  # Call _determine_success
        if resource_usage:
            log_entry["resource_usage"] = self._format_resource_usage(resource_usage)
        if reasoning_path:
            log_entry["reasoning_path"] = self._format_reasoning_path(reasoning_path)
        if metadata:
            log_entry["metadata"] = metadata
        log_entry["performance_metrics"] = self._calculate_performance_metrics(log_entry)
        self._write_to_main_log(log_entry)
        self._update_performance_stats(log_entry)
        self._log_performance_metrics(log_entry)

    def _determine_success(self, result: Any) -> bool:
        """
        Determine if the query was successful based on the result.
        Enhanced to handle explicit "error" strings and None results.
        """
        if result is None:  # Check for None result (explicit failure)
            return False
        if isinstance(result, list) and result and any("Error" in str(item) for item in result):
            return False  # Check for "Error" in list results
        if isinstance(result, str) and "Error" in result:
            return False  # Check for "Error" in string results
        if isinstance(result, tuple) and "Error" in str(result[0]):
            return False  # Check for "Error" in tuple results (e.g., hybrid output)
        return True  # Otherwise, assume success

    def _format_resource_usage(self, resource_usage: Dict) -> Dict:
        formatted = {k: round(v * 100, 2) if isinstance(v, float) else v for k, v in resource_usage.items()}
        formatted["efficiency_score"] = self._calculate_efficiency_score(resource_usage)
        return formatted

    def _format_reasoning_path(self, reasoning_path: Dict) -> Dict:
        formatted_path = {"path_type": reasoning_path.get("type", "unknown"),
                         "steps": reasoning_path.get("steps", []),
                         "confidence": reasoning_path.get("confidence", 0.0)}
        if "steps" in reasoning_path:
            formatted_path["hop_count"] = len(reasoning_path["steps"])
            formatted_path["hop_types"] = self._analyze_hop_types(reasoning_path["steps"])
        return formatted_path

    def _analyze_hop_types(self, steps: List[Dict]) -> Dict:
        hop_types = defaultdict(int)
        for step in steps:
            hop_type = step.get("type", "unknown")
            hop_types[hop_type] += 1
        return dict(hop_types)

    def _calculate_performance_metrics(self, entry: Dict) -> Dict:
        metrics = {"processing_time": entry.get("processing_time", 0), "success": entry.get("success", False)}
        if "resource_usage" in entry:
            metrics["resource_efficiency"] = self._calculate_efficiency_score(entry["resource_usage"])
        if "reasoning_path" in entry:
            metrics["reasoning_complexity"] = self._calculate_reasoning_complexity(entry["reasoning_path"])
        return metrics

    def _calculate_efficiency_score(self, resource_usage: Dict) -> float:
        weights = {"cpu": 0.3, "memory": 0.3, "gpu": 0.4}
        score = 0.0
        for resource, weight in weights.items():
            if resource in resource_usage:
                score += (1 - resource_usage[resource]) * weight
        return round(score, 4)

    def _calculate_reasoning_complexity(self, reasoning_path: Dict) -> float:
        base_complexity = 0.0
        hop_count = reasoning_path.get("hop_count", 1)
        base_complexity += min(hop_count * 0.2, 0.6)
        path_type_weights = {"symbolic": 0.2, "neural": 0.3, "hybrid": 0.4}
        path_type = reasoning_path.get("path_type", "unknown")
        base_complexity += path_type_weights.get(path_type, 0.1)
        return round(base_complexity, 4)

    def _write_to_main_log(self, log_entry: Dict):
        try:
            current_logs = []
            if self.main_log_path.exists():
                with open(self.main_log_path, 'r', encoding='utf-8') as f:
                    current_logs = json.load(f)
            if len(current_logs) >= self.max_log_size:
                current_logs = current_logs[-(self.max_log_size - 1):]
            current_logs.append(log_entry)
            with open(self.main_log_path, 'w', encoding='utf-8') as f:
                json.dump(current_logs, f, indent=4)
                f.flush()
        except Exception as e:
            self.logger.error(f"Error writing to main log: {str(e)}")
            self._log_error("main_log_write_error", str(e))

    def _update_performance_stats(self, log_entry: Dict):
        metrics = log_entry["performance_metrics"]
        self.performance_stats["processing_times"].append(metrics["processing_time"])
        self.performance_stats["success_rate"].append(int(metrics["success"]))
        if "resource_efficiency" in metrics:
            self.performance_stats["resource_efficiency"].append(metrics["resource_efficiency"])
        max_history = 1000
        for key in self.performance_stats:
            if len(self.performance_stats[key]) > max_history:
                self.performance_stats[key] = self.performance_stats[key][-max_history:]

    def _log_performance_metrics(self, log_entry: Dict):
        try:
            with jsonlines.open(self.performance_log_path, mode='a') as writer:
                writer.write({"timestamp": log_entry["timestamp"], "query_id": hash(log_entry["query"]),
                              "metrics": log_entry["performance_metrics"],
                              "resource_usage": log_entry.get("resource_usage", {}),
                              "reasoning_path": log_entry.get("reasoning_path", {})})
        except Exception as e:
            self.logger.error(f"Error writing performance metrics: {str(e)}")
            self._log_error("performance_log_write_error", str(e))

    def _log_error(self, error_type: str, error_message: str):
        try:
            with open(self.error_log_path, 'r+', encoding='utf-8') as f:
                error_log = json.load(f)
                error_log["error_counts"][error_type] = error_log["error_counts"].get(error_type, 0) + 1
                error_log["error_logs"].append({"timestamp": datetime.now().isoformat(), "type": error_type,
                                                "message": error_message})
                f.seek(0)
                json.dump(error_log, f, indent=4)
                f.truncate()
        except Exception as e:
            self.logger.error(f"Error logging error: {str(e)}")

    def get_performance_summary(self) -> Dict:
        summary = {}
        for metric, values in self.performance_stats.items():
            if values:
                summary[metric] = {"average": sum(values) / len(values), "min": min(values), "max": max(values),
                                  "latest": values[-1]}
        return summary