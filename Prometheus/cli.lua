-- This Script is Part of the Prometheus Obfuscator by levno-710
--
-- cli.lua
--
-- This Script contains the Code for the Prometheus CLI

-- Configure package.path for requiring Prometheus
local function script_path()
	local info = debug.getinfo(1, "S") or debug.getinfo(2, "S")
	local str = (info and info.source) and info.source:sub(2) or ""
	return str:match("(.*[/%\\])") or "./"
end
local sp = script_path()
package.path = sp .. "?.lua;" .. sp .. "src/?.lua;" .. sp .. "src/prometheus/?.lua;" .. package.path
require("src.cli")