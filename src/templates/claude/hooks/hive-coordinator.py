#!/usr/bin/env python3
"""
蜂巢协调器 Hook (Hive Coordinator Hook)

在工蜂 Agent 执行前自动注入巢室上下文，实现信息素状态同步。
支持 PreToolUse 和 SubagentStop 两种触发点。
"""

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Dict, Any


class HiveCoordinator:
    """蜂巢协调器"""
    
    def __init__(self):
        self.hive_root = self._find_hive_root()
        self.pheromone_file = self.hive_root / "pheromone.json"
        self.cells_dir = self.hive_root / "cells"
        
    def _find_hive_root(self) -> Path:
        """查找蜂巢根目录"""
        current = Path.cwd()
        while current != current.parent:
            trellis_dir = current / ".trellis"
            if trellis_dir.exists():
                return trellis_dir
            current = current.parent
        return Path.cwd() / ".trellis"
    
    def _read_pheromone(self) -> Dict:
        """读取信息素文件"""
        if not self.pheromone_file.exists():
            return {"status": "inactive"}
        
        with open(self.pheromone_file, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    def _write_pheromone(self, data: Dict):
        """写入信息素文件"""
        self.hive_root.mkdir(parents=True, exist_ok=True)
        with open(self.pheromone_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    
    def is_hive_active(self) -> bool:
        """检查蜂巢是否激活"""
        data = self._read_pheromone()
        return data.get("status") == "active"
    
    def get_current_cell(self) -> Optional[str]:
        """获取当前巢室ID"""
        current_task_file = self.hive_root / ".current-task"
        if current_task_file.exists():
            return current_task_file.read_text().strip()
        return None
    
    def get_worker_id(self) -> str:
        """获取当前工蜂ID"""
        worker_id = os.environ.get("HIVE_WORKER_ID")
        if not worker_id:
            worker_id = f"worker-{os.getpid()}"
        return worker_id


class PreToolUseHandler:
    """PreToolUse Hook 处理器"""
    
    def __init__(self, coordinator: HiveCoordinator):
        self.coordinator = coordinator
    
    def handle(self, tool_input: Dict) -> Dict:
        if not self.coordinator.is_hive_active():
            return {}
        
        subagent_type = tool_input.get("subagent_type", "")
        
        if subagent_type not in ["implement", "check", "debug", "hive-queen", "hive-drone"]:
            return {}
        
        cell_id = self.coordinator.get_current_cell()
        worker_id = self.coordinator.get_worker_id()
        
        if not cell_id:
            return {}
        
        context = self._load_cell_context(cell_id)
        pheromone = self.coordinator._read_pheromone()
        self._update_worker_status(pheromone, worker_id, cell_id, subagent_type)
        injection = self._build_injection(cell_id, context, pheromone, subagent_type)
        
        return {
            "prompt_injection": injection,
            "context": {
                "cell_id": cell_id,
                "worker_id": worker_id,
                "pheromone_status": pheromone.get("status")
            }
        }
    
    def _load_cell_context(self, cell_id: str) -> list:
        context_file = self.coordinator.cells_dir / cell_id / "context.jsonl"
        if not context_file.exists():
            return []
        
        contexts = []
        with open(context_file, 'r', encoding='utf-8') as f:
            for line in f:
                if line.strip():
                    contexts.append(json.loads(line))
        return contexts
    
    def _update_worker_status(self, pheromone: Dict, worker_id: str, 
                              cell_id: str, subagent_type: str):
        now = datetime.now(timezone.utc).isoformat()
        workers = pheromone.get("workers", [])
        worker_found = False
        
        for worker in workers:
            if worker["id"] == worker_id:
                worker["status"] = "implementing" if subagent_type == "implement" else "validating"
                worker["last_update"] = now
                worker_found = True
                break
        
        if not worker_found:
            workers.append({
                "id": worker_id,
                "cell": cell_id,
                "status": "implementing" if subagent_type == "implement" else "validating",
                "progress": 0,
                "last_update": now
            })
        
        pheromone["workers"] = workers
        self.coordinator._write_pheromone(pheromone)
    
    def _build_injection(self, cell_id: str, context: list, 
                         pheromone: Dict, subagent_type: str) -> str:
        lines = [
            "# 🐝 蜂巢上下文注入",
            "",
            f"**巢室**: {cell_id}",
            f"**角色**: {subagent_type}",
            f"**蜂巢状态**: {pheromone.get('status', 'unknown')}",
            "",
            "## 巢室上下文",
            ""
        ]
        
        for ctx in context:
            file_path = ctx.get("file", "")
            reason = ctx.get("reason", "")
            lines.append(f"- `{file_path}`: {reason}")
        
        workers = pheromone.get("workers", [])
        if workers:
            lines.extend(["", "## 工蜂状态", ""])
            for w in workers[:5]:
                lines.append(f"- {w['id']}: {w['status']} ({w.get('progress', 0)}%)")
        
        blocked = [w for w in workers if w.get("status") == "blocked"]
        if blocked:
            lines.extend(["", "## ⚠️ 阻塞警告", ""])
            for w in blocked:
                lines.append(f"- {w['id']} 被阻塞: {w.get('block_reason', '未知原因')}")
        
        return "\n".join(lines)


class SubagentStopHandler:
    """SubagentStop Hook 处理器"""
    
    def __init__(self, coordinator: HiveCoordinator):
        self.coordinator = coordinator
    
    def handle(self, agent_output: str, subagent_type: str) -> Dict:
        if not self.coordinator.is_hive_active():
            return {"allow_stop": True}
        
        cell_id = self.coordinator.get_current_cell()
        worker_id = self.coordinator.get_worker_id()
        
        if self._check_completion_marker(agent_output, subagent_type):
            self._mark_completion(worker_id, cell_id, subagent_type)
            return {"allow_stop": True}
        
        if subagent_type == "hive-drone":
            return self._check_drone_consensus(agent_output)
        
        if subagent_type == "implement":
            return {"allow_stop": True, "need_validation": True}
        
        return {"allow_stop": True}
    
    def _check_completion_marker(self, output: str, subagent_type: str) -> bool:
        markers = {
            "implement": ["IMPLEMENT_COMPLETE", "CELL_COMPLETE"],
            "check": ["CHECK_COMPLETE", "ALL_CHECKS_FINISH"],
            "debug": ["DEBUG_COMPLETE", "FIX_APPLIED"],
            "hive-drone": ["DRONE_VALIDATION_COMPLETE"]
        }
        
        type_markers = markers.get(subagent_type, [])
        return any(marker in output for marker in type_markers)
    
    def _mark_completion(self, worker_id: str, cell_id: str, subagent_type: str):
        pheromone = self.coordinator._read_pheromone()
        now = datetime.now(timezone.utc).isoformat()
        
        for worker in pheromone.get("workers", []):
            if worker["id"] == worker_id:
                worker["status"] = "completed"
                worker["progress"] = 100
                worker["last_update"] = now
                break
        
        for cell in pheromone.get("cells", []):
            if cell["id"] == cell_id:
                if subagent_type == "implement":
                    cell["status"] = "implemented"
                elif subagent_type == "hive-drone":
                    cell["status"] = "validated"
                cell["updated_at"] = now
                break
        
        self.coordinator._write_pheromone(pheromone)
    
    def _check_drone_consensus(self, output: str) -> Dict:
        import re
        
        score_match = re.search(r"SCORE:\s*(\d+)", output)
        consensus_match = re.search(r"CONSENSUS:\s*(\w+)", output)
        
        if score_match:
            score = int(score_match.group(1))
            consensus = consensus_match.group(1) if consensus_match else "unknown"
            
            if consensus == "reached" or score >= 90:
                return {"allow_stop": True, "consensus": True, "score": score}
            else:
                return {
                    "allow_stop": False,
                    "consensus": False,
                    "score": score,
                    "message": f"共识分数 {score} < 90，需要修复后重新验证"
                }
        
        return {"allow_stop": True}


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="蜂巢协调器 Hook")
    parser.add_argument("--event", choices=["pre-tool-use", "subagent-stop"], 
                       required=True, help="事件类型")
    parser.add_argument("--input", help="JSON 输入（从 stdin 或文件）")
    
    args = parser.parse_args()
    
    if args.input:
        with open(args.input, 'r', encoding='utf-8') as f:
            input_data = json.load(f)
    else:
        input_data = json.load(sys.stdin)
    
    coordinator = HiveCoordinator()
    
    if args.event == "pre-tool-use":
        handler = PreToolUseHandler(coordinator)
        result = handler.handle(input_data)
    else:
        handler = SubagentStopHandler(coordinator)
        result = handler.handle(
            input_data.get("output", ""),
            input_data.get("subagent_type", "")
        )
    
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
