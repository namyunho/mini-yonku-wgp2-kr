-- probe_api.lua : Mesen2 Lua API 표면 확인 (enum/함수 이름 실측)
-- 산출: tmp/trace/api_probe.txt  →  이걸 읽고 dma_trace.lua 확정
local OUT = "C:/Users/namyunho/mini-yonku-wgp2-kr/tmp/trace/api_probe.txt"
local f = io.open(OUT, "w")

local function dumpTable(name, t)
  f:write("=== " .. name .. " ===\n")
  if type(t) ~= "table" then
    f:write("  (not a table: " .. tostring(t) .. ")\n\n")
    return
  end
  local keys = {}
  for k, v in pairs(t) do keys[#keys+1] = tostring(k) .. " = " .. tostring(v) end
  table.sort(keys)
  for _, s in ipairs(keys) do f:write("  " .. s .. "\n") end
  f:write("\n")
end

dumpTable("emu (functions/fields)", emu)
dumpTable("emu.memCallbackType", emu.memCallbackType)
dumpTable("emu.callbackType", emu.callbackType)
dumpTable("emu.eventType", emu.eventType)
dumpTable("emu.memType", emu.memType)
dumpTable("emu.cpuType", emu.cpuType)

-- getState 구조 확인
local ok, st = pcall(function() return emu.getState() end)
if ok and type(st) == "table" then
  f:write("=== getState() top-level keys ===\n")
  local keys = {}
  for k, v in pairs(st) do keys[#keys+1] = tostring(k) .. " (" .. type(v) .. ")" end
  table.sort(keys)
  for _, s in ipairs(keys) do f:write("  " .. s .. "\n") end
  f:write("\n")
  -- cpu 서브테이블 후보
  for _, sub in ipairs({"cpu", "proc", "ppu"}) do
    if type(st[sub]) == "table" then
      f:write("--- getState()." .. sub .. " keys ---\n")
      local kk = {}
      for k, v in pairs(st[sub]) do kk[#kk+1] = tostring(k) .. " = " .. tostring(v) end
      table.sort(kk)
      for _, s in ipairs(kk) do f:write("  " .. s .. "\n") end
      f:write("\n")
    end
  end
else
  f:write("getState() failed: " .. tostring(st) .. "\n")
end

f:flush()
f:close()

-- 몇 프레임 뒤 종료: eventType 이름 후보를 모두 시도
local stopped = false
local function doStop()
  if stopped then return end
  stopped = true
  if emu.stop then pcall(function() emu.stop(0) end) end
end

local registered = false
if emu.addEventCallback and emu.eventType then
  for _, name in ipairs({"endFrame", "startFrame", "nmi"}) do
    if emu.eventType[name] ~= nil then
      pcall(function() emu.addEventCallback(doStop, emu.eventType[name]) end)
      registered = true
      break
    end
  end
end
-- 콜백 등록 실패 시 즉시 종료
if not registered then doStop() end
