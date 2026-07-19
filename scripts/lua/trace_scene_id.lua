-- trace_scene_id.lua : 어드벤처 씬 로드를 추적(씬표 $C6:9C57 읽기 후킹).
--   프리즈/버그 순간의 "마지막 로드된 씬 id"를 기록 → 범인 씬 특정(디버거 조작 불필요).
--   사용: Mesen으로 out/wgp2_kr.smc 로드 → 이 스크립트 실행 → 버그 재현 → 프리즈되면 알려주기.
--   출력: 아래 OUT (최근 40개 씬 로드 이력). ScriptWindow.AllowIoOsAccess=true 필요.
local OUT = "/Users/namyunho/Developer/mini-yonku-wgp2-kr/tmp/trace/scene_trace.txt"
local TBL = 0xC69C57        -- 씬표 CPU 주소 (3B/엔트리, 250씬)
local hist = {}
local lastsid = -1

local function flush()
  local f = io.open(OUT, "w")
  if not f then return end
  f:write("어드벤처 씬 로드 이력(오래된→최신, 마지막이 현재 씬):\n")
  for _, l in ipairs(hist) do f:write(l .. "\n") end
  f:close()
end

emu.addMemoryCallback(function(addr, value)
  local sid = (addr - TBL) // 3
  if sid < 0 or sid >= 250 then return end
  if sid == lastsid then return end          -- 같은 씬 연속 읽기 억제
  lastsid = sid
  local st = emu.getState()
  hist[#hist + 1] = string.format("f=%d  scene=0x%02X", st["frameCount"] or 0, sid)
  if #hist > 40 then table.remove(hist, 1) end
  flush()
end, emu.callbackType.read, TBL, TBL + 250 * 3 - 1, emu.cpuType.snes, emu.memType.snesMemory)

emu.displayMessage("trace", "scene-id tracer armed")
