"""
FleedGuard High-Capacity Lua / Luau Feature Analyzer & AST Scanner
Deeply inspects Roblox Lua scripts to discover toggles, UI elements,
configuration tables (e.g. CONFIG = { ... }), exploit routines, and automation features.
Capable of scanning scripts with 40,000+ lines and hundreds of feature modules.
"""

import re
from typing import List, Dict, Any

class FeatureAnalyzer:
    @classmethod
    def clean_flag_name(cls, raw: str) -> str:
        clean = re.sub(r'[^A-Za-z0-9_]+', '_', raw.strip()).strip('_')
        return clean or "Feature_Flag"

    @classmethod
    def categorize_feature(cls, name: str) -> str:
        lower = name.lower()
        if any(k in lower for k in ["aim", "silent", "shot", "release", "perfect", "trickshot", "turnaround", "fadeaway", "stepback", "smartshot", "arc", "power", "hitbox", "backboard", "nojump", "formula", "bank", "humanize", "timing", "spin"]):
            return "Combat & Shooting"
        if any(k in lower for k in ["guard", "defense", "steal", "block", "contest", "rebound", "intercept", "onball", "offball", "mirror"]):
            return "Defense & Guarding"
        if any(k in lower for k in ["speed", "walkspeed", "jump", "fly", "noclip", "tp", "teleport", "dash", "stamina", "getopen", "slide", "velocity", "mobility", "flight"]):
            return "Movement & Mobility"
        if any(k in lower for k in ["esp", "chams", "tracer", "visual", "glow", "box", "highlight", "radar", "crosshair", "ballskin", "balltrail", "cosmetic", "color", "font", "theme", "logo"]):
            return "Visuals & Cosmetics"
        if any(k in lower for k in ["auto", "farm", "dunk", "macro", "loop", "afk", "catch", "quickstop", "bot", "assist"]):
            return "Automation & Macro"
        if any(k in lower for k in ["anti", "bypass", "shield", "god", "invis", "invisible", "desync", "spoof", "safeguard", "safe"]):
            return "Protection & Bypass"
        return "General Utilities"

    @classmethod
    def format_display_name(cls, flag_name: str) -> str:
        s1 = re.sub('(.)([A-Z][a-z]+)', r'\1 \2', flag_name)
        s2 = re.sub('([a-z0-9])([A-Z])', r'\1 \2', s1)
        return s2.replace('_', ' ').strip()

    @classmethod
    def scan_script(cls, lua_source: str) -> List[Dict[str, Any]]:
        """
        Scans a Lua script and returns a comprehensive, deduplicated list of discovered features.
        """
        if not lua_source or not isinstance(lua_source, str):
            return []

        features_dict: Dict[str, Dict[str, Any]] = {}
        lines = lua_source.splitlines()

        # -------------------------------------------------------------
        # PASS 1: Comprehensive Balanced-Brace Table Parser (CONFIG/Settings/Options)
        # -------------------------------------------------------------
        table_matches = re.finditer(
            r'(?:local\s+)?([A-Za-z0-9_]*(?:CONFIG|Settings|Options|Toggles|Features|Config|Flags|Preferences|ClientSettings)[A-Za-z0-9_]*)\s*=\s*\{',
            lua_source,
            re.IGNORECASE
        )

        for tm in table_matches:
            tbl_name = tm.group(1)
            start_pos = tm.end() - 1  # at '{'
            
            # Find line number for the start of table
            table_start_line = lua_source[:start_pos].count('\n') + 1

            # Track balanced curly braces
            brace_count = 0
            end_pos = start_pos
            for pos in range(start_pos, len(lua_source)):
                ch = lua_source[pos]
                if ch == '{':
                    brace_count += 1
                elif ch == '}':
                    brace_count -= 1
                    if brace_count == 0:
                        end_pos = pos
                        break

            table_body = lua_source[start_pos + 1:end_pos]
            body_lines = table_body.splitlines()

            for offset_idx, line in enumerate(body_lines):
                line_str = line.strip()
                if not line_str or line_str.startswith('--'):
                    continue

                actual_line_no = table_start_line + offset_idx

                # Match Key = Value pairs: e.g. PerfectRelease = true,
                kv_match = re.match(r'^([A-Za-z0-9_]+)\s*=\s*([^,\n\r]+)', line_str)
                if not kv_match:
                    continue

                key = kv_match.group(1).strip()
                raw_val = kv_match.group(2).strip().rstrip(',')

                # Ignore pure internal syntax / index markers
                if key.lower() in ['index', 'id', 'version', '__index', 'self']:
                    continue

                flag_type = "STRING"
                val_clean = raw_val

                if raw_val in ("true", "false"):
                    flag_type = "BOOLEAN"
                elif raw_val.replace('.', '', 1).isdigit() or (raw_val.startswith('-') and raw_val[1:].replace('.', '', 1).isdigit()):
                    flag_type = "NUMBER"
                elif (raw_val.startswith('"') and raw_val.endswith('"')) or (raw_val.startswith("'") and raw_val.endswith("'")):
                    flag_type = "STRING"
                    val_clean = raw_val[1:-1]
                elif "Enum.KeyCode" in raw_val:
                    flag_type = "KEYBIND"
                    val_clean = raw_val.split('.')[-1]

                flag_name = cls.clean_flag_name(key)
                if flag_name not in features_dict:
                    features_dict[flag_name] = {
                        "flag_name": flag_name,
                        "display_name": cls.format_display_name(key),
                        "flag_type": flag_type,
                        "default_value": val_clean,
                        "category": cls.categorize_feature(key),
                        "source_type": f"Config ({tbl_name})",
                        "line_number": actual_line_no,
                        "context_snippet": line_str[:120]
                    }

        # -------------------------------------------------------------
        # PASS 2: UI Library Elements (AddToggle, CreateToggle, Sliders, Dropdowns)
        # -------------------------------------------------------------
        ui_patterns = [
            r'[:\.]\s*(?:AddToggle|CreateToggle|Toggle|NewToggle|add_toggle|create_toggle)\s*\(\s*["\']([^"\']+)["\']',
            r'[:\.]\s*(?:AddToggle|CreateToggle|Toggle|NewToggle)\s*\(\s*\{\s*(?:Name|Title|Text|text)\s*=\s*["\']([^"\']+)["\']',
            r'[:\.]\s*(?:AddSlider|CreateSlider|Slider|NewSlider)\s*\(\s*["\']([^"\']+)["\']',
            r'[:\.]\s*(?:AddSlider|CreateSlider|Slider|NewSlider)\s*\(\s*\{\s*(?:Name|Title|Text|text)\s*=\s*["\']([^"\']+)["\']',
            r'[:\.]\s*(?:AddDropdown|CreateDropdown|Dropdown|NewDropdown)\s*\(\s*["\']([^"\']+)["\']',
            r'[:\.]\s*(?:AddKeybind|CreateKeybind|Keybind|NewKeybind|AddKeyPicker)\s*\(\s*["\']([^"\']+)["\']',
            r'[:\.]\s*(?:AddButton|CreateButton|Button)\s*\(\s*["\']([^"\']+)["\']',
            r'Toggles\[["\']([^"\']+)["\']\]',
            r'Options\[["\']([^"\']+)["\']\]',
        ]

        for line_idx, line in enumerate(lines, start=1):
            for pat in ui_patterns:
                for match in re.finditer(pat, line, re.IGNORECASE):
                    raw_title = match.group(1).strip()
                    if not raw_title or len(raw_title) > 60:
                        continue
                    flag_name = cls.clean_flag_name(raw_title)
                    is_slider = any(k in line.lower() for k in ["slider", "value", "speed", "fov", "range"])
                    flag_type = "NUMBER" if is_slider else "BOOLEAN"
                    default_val = "16" if is_slider else "true"

                    if flag_name not in features_dict:
                        features_dict[flag_name] = {
                            "flag_name": flag_name,
                            "display_name": cls.format_display_name(raw_title),
                            "flag_type": flag_type,
                            "default_value": default_val,
                            "category": cls.categorize_feature(raw_title),
                            "source_type": "UI Component",
                            "line_number": line_idx,
                            "context_snippet": line.strip()[:120]
                        }

        # -------------------------------------------------------------
        # PASS 3: Exploit / Feature Function Routines
        # -------------------------------------------------------------
        func_pattern = r'(?:local\s+)?function\s+([A-Za-z0-9_]+)\s*\('
        for line_idx, line in enumerate(lines, start=1):
            for match in re.finditer(func_pattern, line):
                fn_name = match.group(1).strip()
                cat = cls.categorize_feature(fn_name)
                if cat != "General Utilities" and len(fn_name) >= 5:
                    flag_name = cls.clean_flag_name(fn_name)
                    if flag_name not in features_dict:
                        features_dict[flag_name] = {
                            "flag_name": flag_name,
                            "display_name": cls.format_display_name(fn_name),
                            "flag_type": "BOOLEAN",
                            "default_value": "true",
                            "category": cat,
                            "source_type": "Feature Function",
                            "line_number": line_idx,
                            "context_snippet": line.strip()[:120]
                        }

        results = list(features_dict.values())
        results.sort(key=lambda x: (x["category"], x["flag_name"]))
        return results

feature_analyzer = FeatureAnalyzer()
