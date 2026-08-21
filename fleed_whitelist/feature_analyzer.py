"""
FleedGuard Lua / Luau Feature Analyzer & AST Scanner
Deeply inspects Roblox Lua scripts to discover toggles, UI elements,
configuration tables, exploit routines, and automation features.
"""

import re
from typing import List, Dict, Any

class FeatureAnalyzer:
    # Well-known UI library patterns in Roblox scripting
    UI_TOGGLE_PATTERNS = [
        # Rayfield / Orion / Fluent / Solaris / LinoriaLib / WindUI / Venyx / Kavo / Maclib
        r'[:\.]\s*(?:AddToggle|CreateToggle|Toggle|NewToggle|add_toggle|create_toggle)\s*\(\s*["\']([^"\']+)["\']',
        r'[:\.]\s*(?:AddToggle|CreateToggle|Toggle|NewToggle)\s*\(\s*\{\s*(?:Name|Title|text)\s*=\s*["\']([^"\']+)["\']',
        r'[:\.]\s*(?:AddSlider|CreateSlider|Slider|NewSlider)\s*\(\s*["\']([^"\']+)["\']',
        r'[:\.]\s*(?:AddSlider|CreateSlider|Slider|NewSlider)\s*\(\s*\{\s*(?:Name|Title|text)\s*=\s*["\']([^"\']+)["\']',
        r'[:\.]\s*(?:AddDropdown|CreateDropdown|Dropdown|NewDropdown)\s*\(\s*["\']([^"\']+)["\']',
        r'[:\.]\s*(?:AddKeybind|CreateKeybind|Keybind|NewKeybind)\s*\(\s*["\']([^"\']+)["\']',
        r'[:\.]\s*(?:AddButton|CreateButton|Button)\s*\(\s*["\']([^"\']+)["\']',
    ]

    # Global and local settings table patterns
    CONFIG_TABLE_PATTERNS = [
        r'(?:getgenv\(\)|_G|_ENV)\.([A-Za-z0-9_]+)\s*=\s*\{([^}]+)\}',
        r'local\s+([A-Za-z0-9_]*(?:Settings|Config|Options|Features|Flags|Toggles)[A-Za-z0-9_]*)\s*=\s*\{([^}]+)\}',
    ]

    # Common individual feature variables
    FEATURE_VAR_PATTERNS = [
        r'(?:getgenv\(\)|_G)\.([A-Za-z0-9_]*(?:Aim|Aimbot|Esp|SilentAim|Speed|WalkSpeed|Fly|Auto|Dunk|Steal|Hitbox|Anti|God|Noclip|Teleport|Spam|Kill)[A-Za-z0-9_]*)\s*=\s*([^;\n\r]+)',
        r'local\s+([A-Za-z0-9_]*(?:Aim|Aimbot|Esp|SilentAim|Speed|WalkSpeed|Fly|Auto|Dunk|Steal|Hitbox|Anti|God|Noclip|Teleport|Spam|Kill)[A-Za-z0-9_]*)\s*=\s*(true|false|\d+(?:\.\d+)?|"[^"]*"|\'[^\']*\')',
    ]

    # Function declarations representing distinct features
    FUNCTION_PATTERNS = [
        r'(?:local\s+)?function\s+([A-Za-z0-9_]*(?:Auto[A-Z][a-zA-Z0-9_]*|SilentAim|Aimbot|HitboxExpander|BallPrediction|SpeedBoost|InfStamina|FlyHack|AntiBan|PlayerESP|BallESP)[a-zA-Z0-9_]*)\s*\(',
    ]

    # Explicit Fleed Flag queries
    EXPLICIT_FLAG_PATTERNS = [
        r'getgenv\(\)\.__FLEED_FLAGS\[["\']([^"\']+)["\']\]',
        r'GetFlag\(["\']([^"\']+)["\']',
        r'IsFlagEnabled\(["\']([^"\']+)["\']',
        r'FleedFlags\[["\']([^"\']+)["\']\]',
    ]

    @classmethod
    def categorize_feature(cls, name: str) -> str:
        lower = name.lower()
        if any(k in lower for k in ["aim", "silent", "hitbox", "target", "trigger", "shoot", "predict", "fov", "wallbang"]):
            return "Combat & Targeting"
        if any(k in lower for k in ["speed", "walkspeed", "jump", "fly", "noclip", "tp", "teleport", "dash", "infinite stamina", "stamina"]):
            return "Movement & Physics"
        if any(k in lower for k in ["esp", "chams", "tracer", "visual", "glow", "box", "highlight", "radar", "crosshair"]):
            return "Visuals & ESP"
        if any(k in lower for k in ["auto", "farm", "dunk", "steal", "guard", "bot", "loop", "afk", "catch", "block"]):
            return "Automation & Macro"
        if any(k in lower for k in ["anti", "bypass", "shield", "god", "invis", "invisible", "desync"]):
            return "Protection & Bypass"
        return "General Utilities"

    @classmethod
    def clean_flag_name(cls, raw: str) -> str:
        # Convert "Auto Steal Ball!" to "Auto_Steal_Ball"
        clean = re.sub(r'[^A-Za-z0-9_]+', '_', raw.strip()).strip('_')
        return clean or "Feature_Flag"

    @classmethod
    def scan_script(cls, lua_source: str) -> List[Dict[str, Any]]:
        """
        Scans a Lua script and returns a deduplicated list of discovered features.
        """
        if not lua_source or not isinstance(lua_source, str):
            return []

        features_dict: Dict[str, Dict[str, Any]] = {}

        lines = lua_source.splitlines()

        # 1. Scan UI Toggle, Slider, and Dropdown declarations
        for line_idx, line in enumerate(lines, start=1):
            for pattern in cls.UI_TOGGLE_PATTERNS:
                for match in re.finditer(pattern, line, re.IGNORECASE):
                    raw_title = match.group(1).strip()
                    if not raw_title or len(raw_title) > 60:
                        continue
                    flag_name = cls.clean_flag_name(raw_title)
                    is_slider = any(k in line.lower() for k in ["slider", "value", "speed", "fov"])
                    flag_type = "NUMBER" if is_slider else "BOOLEAN"
                    default_val = "16" if is_slider else "true"

                    if flag_name not in features_dict:
                        features_dict[flag_name] = {
                            "flag_name": flag_name,
                            "display_name": raw_title,
                            "flag_type": flag_type,
                            "default_value": default_val,
                            "category": cls.categorize_feature(raw_title),
                            "source_type": "UI Component",
                            "line_number": line_idx,
                            "context_snippet": line.strip()[:100]
                        }

        # 2. Scan Config / Settings Tables
        for line_idx, line in enumerate(lines, start=1):
            for pattern in cls.CONFIG_TABLE_PATTERNS:
                for match in re.finditer(pattern, line, re.IGNORECASE):
                    tbl_name = match.group(1)
                    body = match.group(2)
                    # Extract key-value pairs inside table
                    # e.g., SilentAim = true, WalkSpeed = 30, TargetPart = "Head"
                    kv_pattern = r'([A-Za-z0-9_]+)\s*=\s*(true|false|\d+(?:\.\d+)?|"[^"]*"|\'[^\']*\')'
                    for kv in re.finditer(kv_pattern, body):
                        key = kv.group(1).strip()
                        val = kv.group(2).strip()
                        if key.lower() in ["index", "id", "version", "key"]:
                            continue
                        flag_name = cls.clean_flag_name(f"{tbl_name}_{key}" if len(tbl_name) <= 12 else key)
                        
                        flag_type = "BOOLEAN"
                        if val in ("true", "false"):
                            flag_type = "BOOLEAN"
                        elif val.replace('.', '', 1).isdigit():
                            flag_type = "NUMBER"
                        elif (val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'")):
                            flag_type = "STRING"
                            val = val[1:-1]

                        if flag_name not in features_dict:
                            features_dict[flag_name] = {
                                "flag_name": flag_name,
                                "display_name": key,
                                "flag_type": flag_type,
                                "default_value": val,
                                "category": cls.categorize_feature(key),
                                "source_type": "Configuration Table",
                                "line_number": line_idx,
                                "context_snippet": f"{tbl_name}.{key} = {val}"
                            }

        # 3. Scan Feature Variables
        for line_idx, line in enumerate(lines, start=1):
            for pattern in cls.FEATURE_VAR_PATTERNS:
                for match in re.finditer(pattern, line, re.IGNORECASE):
                    var_name = match.group(1).strip()
                    val = match.group(2).strip()
                    flag_name = cls.clean_flag_name(var_name)
                    flag_type = "BOOLEAN"
                    if val in ("true", "false"):
                        flag_type = "BOOLEAN"
                    elif val.replace('.', '', 1).isdigit():
                        flag_type = "NUMBER"
                    elif (val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'")):
                        flag_type = "STRING"
                        val = val[1:-1]

                    if flag_name not in features_dict:
                        features_dict[flag_name] = {
                            "flag_name": flag_name,
                            "display_name": var_name,
                            "flag_type": flag_type,
                            "default_value": val,
                            "category": cls.categorize_feature(var_name),
                            "source_type": "Global / Setting Variable",
                            "line_number": line_idx,
                            "context_snippet": line.strip()[:100]
                        }

        # 4. Scan Function Declarations
        for line_idx, line in enumerate(lines, start=1):
            for pattern in cls.FUNCTION_PATTERNS:
                for match in re.finditer(pattern, line, re.IGNORECASE):
                    fn_name = match.group(1).strip()
                    flag_name = cls.clean_flag_name(fn_name)
                    if flag_name not in features_dict:
                        features_dict[flag_name] = {
                            "flag_name": flag_name,
                            "display_name": fn_name,
                            "flag_type": "BOOLEAN",
                            "default_value": "true",
                            "category": cls.categorize_feature(fn_name),
                            "source_type": "Feature Routine / Function",
                            "line_number": line_idx,
                            "context_snippet": line.strip()[:100]
                        }

        # 5. Scan Explicit Fleed Flags
        for line_idx, line in enumerate(lines, start=1):
            for pattern in cls.EXPLICIT_FLAG_PATTERNS:
                for match in re.finditer(pattern, line, re.IGNORECASE):
                    flag_name = cls.clean_flag_name(match.group(1).strip())
                    if flag_name not in features_dict:
                        features_dict[flag_name] = {
                            "flag_name": flag_name,
                            "display_name": flag_name,
                            "flag_type": "BOOLEAN",
                            "default_value": "true",
                            "category": cls.categorize_feature(flag_name),
                            "source_type": "Remote Feature Flag",
                            "line_number": line_idx,
                            "context_snippet": line.strip()[:100]
                        }

        # Return sorted list categorized logically
        results = list(features_dict.values())
        results.sort(key=lambda x: (x["category"], x["flag_name"]))
        return results

feature_analyzer = FeatureAnalyzer()
