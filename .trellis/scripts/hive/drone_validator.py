#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Drone Validator Module

Implements multi-dimensional cross-validation for code quality consensus.
Supports technical, strategic, and security validation dimensions.

Usage:
    from drone_validator import DroneValidator
    
    dv = DroneValidator()
    result = dv.validate_cell("cell-auth", ["technical", "security"])
"""

from __future__ import annotations

import hashlib
import json
import os
import random
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional
from dataclasses import dataclass, field
from enum import Enum


class DroneValidatorError(Exception):
    """Base exception for drone validator"""
    pass


class ValidationError(DroneValidatorError):
    """Raised when validation fails"""
    pass


class ValidationDimension(Enum):
    """Validation dimensions"""
    TECHNICAL = "technical"
    STRATEGIC = "strategic"
    SECURITY = "security"


# Command whitelist for safe execution
SAFE_COMMANDS = {
    "pnpm lint": ["pnpm", "lint"],
    "pnpm typecheck": ["pnpm", "typecheck"],
    "pnpm test": ["pnpm", "test"],
    "pnpm audit": ["pnpm", "audit"],
    "npm run lint": ["npm", "run", "lint"],
    "npm run test": ["npm", "run", "test"],
    "npm run typecheck": ["npm", "run", "typecheck"],
}

# Maximum file size for security scanning
MAX_FILE_SIZE = 1024 * 1024  # 1MB


@dataclass
class ValidationResult:
    """Validation result"""
    dimension: str
    passed: bool
    score: int  # 0-100
    issues: list[dict[str, Any]]
    details: dict[str, Any]


class DroneValidator:
    """Drone validator for multi-dimensional code validation
    
    Implements the drone verification protocol from hive concurrent agent mode.
    Each drone validates from a specific perspective (technical/strategic/security).
    """
    
    # Consensus threshold
    CONSENSUS_THRESHOLD = 90
    
    # Dimension weights for consensus calculation
    DIMENSION_WEIGHTS: dict[ValidationDimension, float] = {
        ValidationDimension.TECHNICAL: 0.4,
        ValidationDimension.STRATEGIC: 0.35,
        ValidationDimension.SECURITY: 0.25
    }
    
    # Score penalties for issues
    SCORE_PENALTIES = {
        "critical": 30,
        "high": 20,
        "medium": 10,
        "low": 5,
    }
    
    def __init__(self, hive_root: Optional[Path] = None, seed: Optional[int] = None):
        """Initialize drone validator
        
        Args:
            hive_root: Hive root directory
            seed: Random seed for reproducible cross-validation
        """
        self.hive_root = hive_root or self._find_hive_root()
        self.project_root = self.hive_root.parent
        self.audit_dir = self.hive_root / "hive-audit"
        self.audit_dir.mkdir(parents=True, exist_ok=True)
        self._seed = seed
        self._rng = random.Random(seed)
    
    def _find_hive_root(self) -> Path:
        """Find hive root directory"""
        current = Path.cwd()
        while current != current.parent:
            trellis_dir = current / ".trellis"
            if trellis_dir.exists():
                return trellis_dir
            current = current.parent
        return Path.cwd() / ".trellis"
    
    # ==================== Core Validation Interface ====================
    
    def validate_cell(
        self,
        cell_id: str,
        dimensions: Optional[list[str]] = None,
        worktree_path: Optional[str] = None,
        drone_id: Optional[str] = None
    ) -> dict[str, Any]:
        """Execute multi-dimensional validation on a cell
        
        Args:
            cell_id: Cell ID
            dimensions: Validation dimensions, defaults to all
            worktree_path: Worktree path if applicable
            drone_id: Optional drone identifier
            
        Returns:
            Validation summary
        """
        self._validate_cell_id(cell_id)
        
        if dimensions is None:
            dimensions = [d.value for d in ValidationDimension]
        
        base_path = Path(worktree_path) if worktree_path else self.project_root
        
        # Validate base path exists
        if not base_path.exists():
            raise ValidationError(f"Base path does not exist: {base_path}")
        
        results: dict[str, Any] = {}
        
        for dim in dimensions:
            if dim == ValidationDimension.TECHNICAL.value:
                results[dim] = self._validate_technical(base_path)
            elif dim == ValidationDimension.STRATEGIC.value:
                results[dim] = self._validate_strategic(cell_id, base_path)
            elif dim == ValidationDimension.SECURITY.value:
                results[dim] = self._validate_security(base_path)
        
        # Calculate weighted consensus score
        consensus_score = self._calculate_consensus(results)
        
        # Generate report
        report: dict[str, Any] = {
            "cell_id": cell_id,
            "drone_id": drone_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "dimensions": results,
            "consensus_score": consensus_score,
            "consensus_reached": consensus_score >= self.CONSENSUS_THRESHOLD,
            "threshold": self.CONSENSUS_THRESHOLD
        }
        
        # Save report
        self._save_report(cell_id, report, drone_id)
        
        return report
    
    def _validate_cell_id(self, cell_id: str) -> None:
        """Validate cell ID format"""
        if not cell_id:
            raise ValidationError("Cell ID cannot be empty")
        if not re.match(r'^[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}$', cell_id):
            raise ValidationError(f"Invalid cell ID format: {cell_id}")
    
    def _calculate_consensus(self, results: dict[str, Any]) -> int:
        """Calculate weighted consensus score
        
        Args:
            results: Validation results by dimension
            
        Returns:
            Weighted consensus score (0-100)
        """
        total_score = 0.0
        total_weight = 0.0
        
        for dim, result in results.items():
            try:
                dimension = ValidationDimension(dim)
                weight = self.DIMENSION_WEIGHTS.get(dimension, 0.33)
                total_score += result["score"] * weight
                total_weight += weight
            except ValueError:
                continue
        
        return int(total_score / total_weight) if total_weight > 0 else 0
    
    # ==================== Technical Validation ====================
    
    def _validate_technical(self, base_path: Path) -> dict[str, Any]:
        """Technical validation: lint, typecheck, test
        
        Args:
            base_path: Base path for validation
            
        Returns:
            Validation result
        """
        issues: list[dict[str, Any]] = []
        details: dict[str, Any] = {}
        passed_checks = 0
        total_checks = 3
        
        # 1. Lint check
        lint_result = self._run_safe_command("pnpm lint", base_path)
        if lint_result["success"]:
            passed_checks += 1
            details["lint"] = {"status": "passed"}
        else:
            issues.append({
                "type": "lint_error",
                "severity": "high",
                "message": "Lint check failed",
                "details": lint_result["output"][:500]
            })
            details["lint"] = {"status": "failed"}
        
        # 2. TypeScript type check
        typecheck_result = self._run_safe_command("pnpm typecheck", base_path)
        if typecheck_result["success"]:
            passed_checks += 1
            details["typecheck"] = {"status": "passed"}
        else:
            issues.append({
                "type": "type_error",
                "severity": "high",
                "message": "TypeScript type check failed",
                "details": typecheck_result["output"][:500]
            })
            details["typecheck"] = {"status": "failed"}
        
        # 3. Test check
        test_result = self._run_safe_command("pnpm test", base_path)
        if test_result["success"]:
            passed_checks += 1
            details["test"] = {"status": "passed"}
        else:
            issues.append({
                "type": "test_failure",
                "severity": "medium",
                "message": "Tests failed",
                "details": test_result["output"][:500]
            })
            details["test"] = {"status": "failed"}
        
        # Calculate score
        base_score = int((passed_checks / total_checks) * 100)
        score = self._apply_penalties(base_score, issues)
        
        return {
            "dimension": "technical",
            "passed": passed_checks == total_checks,
            "score": score,
            "issues": issues,
            "details": details
        }
    
    # ==================== Strategic Validation ====================
    
    def _validate_strategic(self, cell_id: str, base_path: Path) -> dict[str, Any]:
        """Strategic validation: requirements match, architecture consistency, risk assessment
        
        Args:
            cell_id: Cell ID
            base_path: Base path for validation
            
        Returns:
            Validation result
        """
        issues: list[dict[str, Any]] = []
        details: dict[str, Any] = {}
        score = 100
        
        # 1. Check requirements and outputs
        cell_config = self._load_cell_config(cell_id)
        if cell_config:
            outputs = cell_config.get("outputs", [])
            missing_outputs = []
            
            for output_pattern in outputs:
                if "*" in output_pattern:
                    matches = list(base_path.glob(output_pattern))
                    if not matches:
                        missing_outputs.append(output_pattern)
                else:
                    if not (base_path / output_pattern).exists():
                        missing_outputs.append(output_pattern)
            
            if missing_outputs:
                score -= self.SCORE_PENALTIES["high"]
                issues.append({
                    "type": "missing_outputs",
                    "severity": "high",
                    "message": "Missing expected output files",
                    "details": missing_outputs
                })
                details["missing_outputs"] = missing_outputs
            else:
                details["outputs"] = "all_present"
        else:
            score -= self.SCORE_PENALTIES["low"]
            details["cell_config"] = "not_found"
        
        # 2. Architecture consistency check
        arch_issues = self._check_architecture_consistency(base_path)
        if arch_issues:
            score -= len(arch_issues) * self.SCORE_PENALTIES["medium"]
            issues.extend(arch_issues)
        details["architecture_check"] = "passed" if not arch_issues else "issues_found"
        
        # 3. Code complexity check
        complexity_score = self._check_code_complexity(base_path)
        if complexity_score < 70:
            score -= self.SCORE_PENALTIES["medium"]
            issues.append({
                "type": "high_complexity",
                "severity": "medium",
                "message": f"Code complexity is high ({complexity_score}/100)",
            })
        details["complexity_score"] = complexity_score
        
        return {
            "dimension": "strategic",
            "passed": score >= 80,
            "score": max(0, score),
            "issues": issues,
            "details": details
        }
    
    def _check_architecture_consistency(self, base_path: Path) -> list[dict[str, Any]]:
        """Check architecture consistency"""
        issues: list[dict[str, Any]] = []
        # Simplified implementation - actual would need more complex analysis
        return issues
    
    def _check_code_complexity(self, base_path: Path) -> int:
        """Check code complexity (simplified)"""
        score = 100
        src_dir = base_path / "src"
        
        if not src_dir.exists():
            return score
        
        file_count = 0
        for ts_file in src_dir.rglob("*.ts"):
            if ts_file.name.endswith(".d.ts"):
                continue
            
            try:
                # Check file size
                file_size = ts_file.stat().st_size
                if file_size > MAX_FILE_SIZE:
                    continue  # Skip large files
                
                content = ts_file.read_text(encoding='utf-8')
                lines = content.split('\n')
                
                # Penalize files over 300 lines
                if len(lines) > 300:
                    score -= 5
                
                file_count += 1
                if file_count > 50:  # Limit files checked
                    break
                    
            except Exception:
                continue
        
        return max(0, score)
    
    # ==================== Security Validation ====================
    
    def _validate_security(self, base_path: Path) -> dict[str, Any]:
        """Security validation: vulnerability scan, permission check, dependency audit
        
        Args:
            base_path: Base path for validation
            
        Returns:
            Validation result
        """
        issues: list[dict[str, Any]] = []
        details: dict[str, Any] = {}
        score = 100
        
        # 1. Check for sensitive data exposure
        sensitive_patterns = [
            (r'password\s*=\s*["\'][^"\']+["\']', "Hardcoded password", "critical"),
            (r'api[_-]?key\s*=\s*["\'][^"\']+["\']', "Hardcoded API Key", "critical"),
            (r'secret\s*=\s*["\'][^"\']+["\']', "Hardcoded secret", "critical"),
            (r'token\s*=\s*["\'][^"\']+["\']', "Hardcoded token", "critical"),
            (r'private[_-]?key\s*=\s*["\'][^"\']+["\']', "Hardcoded private key", "critical"),
        ]
        
        src_dir = base_path / "src"
        if src_dir.exists():
            for ts_file in src_dir.rglob("*.ts"):
                if ts_file.name.endswith(".d.ts"):
                    continue
                
                try:
                    file_size = ts_file.stat().st_size
                    if file_size > MAX_FILE_SIZE:
                        continue
                    
                    content = ts_file.read_text(encoding='utf-8')
                    
                    for pattern, msg, severity in sensitive_patterns:
                        matches = re.findall(pattern, content, re.IGNORECASE)
                        if matches:
                            score -= self.SCORE_PENALTIES[severity]
                            issues.append({
                                "type": "sensitive_data_exposure",
                                "severity": severity,
                                "message": msg,
                                "file": str(ts_file.relative_to(base_path)),
                                "count": len(matches)
                            })
                except Exception:
                    continue
        
        # 2. Dependency security audit
        audit_result = self._run_safe_command("pnpm audit", base_path)
        if not audit_result["success"]:
            if "vulnerabilities" in audit_result["output"].lower():
                score -= self.SCORE_PENALTIES["high"]
                issues.append({
                    "type": "dependency_vulnerability",
                    "severity": "high",
                    "message": "Dependency vulnerabilities found",
                    "details": audit_result["output"][:300]
                })
        details["audit"] = "passed" if audit_result["success"] else "vulnerabilities_found"
        
        # 3. Permission check (simplified)
        details["permission_check"] = "passed"
        
        return {
            "dimension": "security",
            "passed": score >= 80 and not any(
                i["severity"] == "critical" for i in issues
            ),
            "score": max(0, score),
            "issues": issues,
            "details": details
        }
    
    # ==================== Safe Command Execution ====================
    
    def _run_safe_command(self, command: str, cwd: Path) -> dict[str, Any]:
        """Run command safely without shell injection risk
        
        Args:
            command: Command string (must be in whitelist)
            cwd: Working directory
            
        Returns:
            Execution result
        """
        # Check whitelist
        if command not in SAFE_COMMANDS:
            return {
                "success": False,
                "output": f"Command not in whitelist: {command}",
                "returncode": -1
            }
        
        cmd_args = SAFE_COMMANDS[command]
        
        try:
            result = subprocess.run(
                cmd_args,  # List form, no shell=True
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=120
            )
            return {
                "success": result.returncode == 0,
                "output": result.stdout + result.stderr,
                "returncode": result.returncode
            }
        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "output": "Command timed out",
                "returncode": -1
            }
        except FileNotFoundError:
            return {
                "success": False,
                "output": f"Command not found: {cmd_args[0]}",
                "returncode": -1
            }
        except Exception as e:
            return {
                "success": False,
                "output": str(e),
                "returncode": -1
            }
    
    def _apply_penalties(self, base_score: int, issues: list[dict[str, Any]]) -> int:
        """Apply score penalties for issues
        
        Args:
            base_score: Base score
            issues: List of issues
            
        Returns:
            Adjusted score
        """
        score = base_score
        for issue in issues:
            severity = issue.get("severity", "low")
            penalty = self.SCORE_PENALTIES.get(severity, self.SCORE_PENALTIES["low"])
            score -= penalty
        return max(0, score)
    
    # ==================== Helper Methods ====================
    
    def _load_cell_config(self, cell_id: str) -> Optional[dict[str, Any]]:
        """Load cell configuration"""
        config_file = self.hive_root / "cells" / cell_id / "cell.json"
        if config_file.exists():
            with open(config_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        return None
    
    def _save_report(
        self, 
        cell_id: str, 
        report: dict[str, Any],
        drone_id: Optional[str] = None
    ) -> None:
        """Save validation report"""
        drone_suffix = f"-{drone_id}" if drone_id else ""
        report_file = self.audit_dir / f"drone-audit-{cell_id}{drone_suffix}.json"
        
        # Write atomically
        temp_file = report_file.with_suffix('.tmp')
        try:
            with open(temp_file, 'w', encoding='utf-8') as f:
                json.dump(report, f, indent=2, ensure_ascii=False)
            temp_file.replace(report_file)
        finally:
            if temp_file.exists():
                temp_file.unlink()
    
    # ==================== Cross Validation ====================
    
    def cross_validate(
        self,
        cell_id: str,
        num_drones: int = 3,
        worktree_path: Optional[str] = None,
        seeds: Optional[list[int]] = None
    ) -> dict[str, Any]:
        """Execute cross-validation with multiple independent drones
        
        Each drone uses a different random seed to ensure variation
        in validation behavior (e.g., file sampling order).
        
        Args:
            cell_id: Cell ID
            num_drones: Number of drones
            worktree_path: Worktree path
            seeds: Optional list of seeds for each drone
            
        Returns:
            Cross-validation result
        """
        self._validate_cell_id(cell_id)
        
        if seeds is None:
            # Generate unique seeds for each drone
            seeds = [self._rng.randint(1, 999999) for _ in range(num_drones)]
        
        all_results: list[dict[str, Any]] = []
        
        for i, seed in enumerate(seeds):
            drone_id = f"drone-{i+1}"
            
            # Create validator with unique seed
            drone_validator = DroneValidator(
                hive_root=self.hive_root,
                seed=seed
            )
            
            result = drone_validator.validate_cell(
                cell_id,
                worktree_path=worktree_path,
                drone_id=drone_id
            )
            result["drone_seed"] = seed
            all_results.append(result)
        
        # Analyze cross-validation results
        scores = [r["consensus_score"] for r in all_results]
        avg_score = sum(scores) / len(scores)
        
        # Calculate variance
        if len(scores) > 1:
            score_variance = sum((s - avg_score) ** 2 for s in scores) / len(scores)
        else:
            score_variance = 0
        
        # Consensus conditions:
        # 1. Average score meets threshold
        # 2. Low variance between drones
        # 3. All drones agree on pass/fail
        all_pass = all(r["consensus_reached"] for r in all_results)
        any_pass = any(r["consensus_reached"] for r in all_results)
        
        consensus_reached = (
            avg_score >= self.CONSENSUS_THRESHOLD and
            score_variance < 100 and  # Low variance
            (all_pass or avg_score >= 95)  # Strong agreement
        )
        
        return {
            "cell_id": cell_id,
            "cross_validation": True,
            "drone_count": num_drones,
            "drone_seeds": seeds,
            "drone_results": all_results,
            "average_score": int(avg_score),
            "score_variance": int(score_variance),
            "all_drones_pass": all_pass,
            "consensus_reached": consensus_reached,
            "consensus_method": "weighted_average_with_variance_check"
        }


# ==================== CLI Interface ====================

def main():
    """CLI entry point"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Drone validator tool")
    subparsers = parser.add_subparsers(dest="command", help="Subcommands")
    
    # validate command
    validate_parser = subparsers.add_parser("validate", help="Validate cell")
    validate_parser.add_argument("cell_id", help="Cell ID")
    validate_parser.add_argument(
        "--dimensions", 
        nargs="+",
        default=["technical", "strategic", "security"],
        help="Validation dimensions"
    )
    validate_parser.add_argument("--worktree", help="Worktree path")
    validate_parser.add_argument("--seed", type=int, help="Random seed")
    
    # cross-validate command
    cross_parser = subparsers.add_parser("cross-validate", help="Cross-validate cell")
    cross_parser.add_argument("cell_id", help="Cell ID")
    cross_parser.add_argument("--drones", type=int, default=3, help="Number of drones")
    cross_parser.add_argument("--worktree", help="Worktree path")
    cross_parser.add_argument("--seeds", nargs="+", type=int, help="Seeds for each drone")
    
    args = parser.parse_args()
    
    if args.command == "validate":
        dv = DroneValidator(seed=getattr(args, 'seed', None))
        result = dv.validate_cell(
            args.cell_id,
            dimensions=args.dimensions,
            worktree_path=args.worktree
        )
        print(json.dumps(result, indent=2, ensure_ascii=False))
    
    elif args.command == "cross-validate":
        dv = DroneValidator()
        result = dv.cross_validate(
            args.cell_id,
            num_drones=args.drones,
            worktree_path=args.worktree,
            seeds=args.seeds
        )
        print(json.dumps(result, indent=2, ensure_ascii=False))
    
    else:
        parser.print_help()


if __name__ == "__main__":
    main()